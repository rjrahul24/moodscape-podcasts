import json
from io import BytesIO

import httpx
import pytest
import respx
from pydub import AudioSegment

from app.core.emotion import EMOTIONS
from app.core.errors import ProviderError
from app.providers.elevenlabs_provider import (
    EMOTION_PROFILES,
    V3_AUDIO_TAGS,
    ElevenLabsProvider,
)

BASE = "https://api.elevenlabs.io"


def _silent_wav_bytes(duration_ms: int = 200) -> bytes:
    buffer = BytesIO()
    AudioSegment.silent(duration=duration_ms, frame_rate=44100).export(
        buffer, format="wav"
    )
    return buffer.getvalue()


@respx.mock
def test_list_voices_maps_payload():
    respx.get(f"{BASE}/v1/voices").mock(
        return_value=httpx.Response(
            200,
            json={
                "voices": [
                    {"voice_id": "v1", "name": "Rachel", "category": "premade"},
                    {"voice_id": "v2", "name": "Domi"},
                ]
            },
        )
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    voices = provider.list_voices()

    assert [(v.id, v.name, v.provider) for v in voices] == [
        ("v1", "Rachel", "elevenlabs"),
        ("v2", "Domi", "elevenlabs"),
    ]
    assert voices[0].category == "premade"


@respx.mock
def test_synthesize_bytes_sends_format_and_key():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)

    audio = provider.synthesize_bytes("hello", "v1", output_format="wav_44100")

    assert audio == b"FAKEAUDIO"
    request = route.calls.last.request
    assert request.url.params["output_format"] == "wav_44100"
    assert request.headers["xi-api-key"] == "test-key"


@respx.mock
def test_v2_emotion_tag_maps_to_numeric_profile():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "hi", "v1", output_format="wav_44100",
        voice_settings={"emotion": "excited", "speed": 1.02, "content_type": "podcast"},
    )
    body = json.loads(route.calls.last.request.content)
    # v2 (default model): emotion -> numeric profile, native speed clamped & kept,
    # the "emotion"/"content_type" hint keys are consumed (not sent as settings).
    assert body["model_id"] == "eleven_multilingual_v2"
    assert body["voice_settings"] == {
        "stability": 0.30,
        "similarity_boost": 0.85,
        "style": 0.80,
        "speed": 1.02,
        "use_speaker_boost": True,
    }
    assert "emotion" not in body["voice_settings"]
    assert "content_type" not in body["voice_settings"]
    # Server-side normalization is requested by default.
    assert body["apply_text_normalization"] == "auto"


@respx.mock
def test_v2_native_speed_is_clamped():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "hi", "v1", output_format="wav_44100",
        voice_settings={"content_type": "sleep", "speed": 0.4},
    )
    body = json.loads(route.calls.last.request.content)
    # Sleep base profile (research sweet spot) + native speed clamped to 0.7 floor.
    assert body["voice_settings"]["stability"] == 0.70
    assert body["voice_settings"]["speed"] == 0.7


@respx.mock
def test_v3_injects_inline_audio_tag_and_discrete_stability():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "Right?! The data surprised me.", "v1", output_format="wav_44100",
        voice_settings={"emotion": "excited", "content_type": "podcast", "model_id": "eleven_v3"},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["model_id"] == "eleven_v3"
    # v3 performs the tag inline (prepended), not as a numeric profile.
    assert body["text"] == "[excited] Right?! The data surprised me."
    assert body["voice_settings"]["stability"] == 0.0  # Creative for excited


@respx.mock
def test_v3_sleep_is_robust_and_untagged():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "The night was calm.", "v1", output_format="wav_44100",
        voice_settings={"content_type": "sleep", "model_id": "eleven_v3", "speed": 0.85},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["text"] == "The night was calm."  # no tag without an emotion
    assert body["voice_settings"]["stability"] == 1.0  # Robust for sleep
    assert body["voice_settings"]["speed"] == 0.85


@respx.mock
def test_no_voice_settings_uses_podcast_base_profile():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes("hi", "v1", output_format="wav_44100")
    body = json.loads(route.calls.last.request.content)
    # No hints -> v2 podcast base profile (expressive but unforced: style 0.0).
    assert body["voice_settings"] == {
        "stability": 0.50,
        "similarity_boost": 0.80,
        "style": 0.0,
        "use_speaker_boost": True,
    }


@respx.mock
def test_synthesize_returns_decoded_segment():
    respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=_silent_wav_bytes(200))
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)

    segment = provider.synthesize("hello", "v1", output_format="wav_44100")

    assert isinstance(segment, AudioSegment)
    assert abs(len(segment) - 200) < 50


@respx.mock
def test_http_error_becomes_provider_error():
    respx.get(f"{BASE}/v1/voices").mock(
        return_value=httpx.Response(401, json={"detail": "invalid key"})
    )
    provider = ElevenLabsProvider("bad-key", base_url=BASE)
    with pytest.raises(ProviderError) as exc:
        provider.list_voices()
    assert exc.value.status_code == 401


def test_missing_key_raises_before_request():
    provider = ElevenLabsProvider(None, base_url=BASE)
    with pytest.raises(ProviderError) as exc:
        provider.list_voices()
    assert exc.value.status_code == 401


# ── new behaviour: tags, continuity, speaker_boost, normalization, seed ─────────


def test_every_emotion_has_v2_profile_and_v3_tag():
    """The shared tone vocabulary and the provider maps must not drift apart."""
    for label in EMOTIONS:
        assert label in EMOTION_PROFILES, f"missing v2 profile for {label!r}"
        assert label in V3_AUDIO_TAGS, f"missing v3 tag entry for {label!r}"


@respx.mock
def test_v2_strips_bracket_tags_from_text():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "[warmly] Breathe in [exhales softly] and out.", "v1",
        output_format="wav_44100",
        voice_settings={"content_type": "podcast"},  # v2 default model
    )
    body = json.loads(route.calls.last.request.content)
    # v2 cannot perform inline tags, so they are removed (never spoken).
    assert body["text"] == "Breathe in and out."


@respx.mock
def test_v3_keeps_inline_tags_in_text():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "Breathe in [exhales softly] and out.", "v1",
        output_format="wav_44100",
        voice_settings={"content_type": "podcast", "model_id": "eleven_v3"},
    )
    body = json.loads(route.calls.last.request.content)
    # v3 performs the cue, so the tag stays in the text verbatim.
    assert body["text"] == "Breathe in [exhales softly] and out."


@respx.mock
def test_continuity_and_seed_are_top_level_fields():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "the present moment.", "v1", output_format="wav_44100",
        voice_settings={
            "content_type": "sleep",
            "previous_text": "settle into",
            "next_text": "you are safe",
            "seed": 42,
        },
    )
    body = json.loads(route.calls.last.request.content)
    # Continuity + seed are request-level fields, not voice_settings keys.
    assert body["previous_text"] == "settle into"
    assert body["next_text"] == "you are safe"
    assert body["seed"] == 42
    assert "previous_text" not in body["voice_settings"]
    assert "seed" not in body["voice_settings"]


@respx.mock
def test_speaker_boost_and_normalization_are_configurable():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider(
        "test-key", base_url=BASE, use_speaker_boost=False, text_normalization="off"
    )
    provider.synthesize_bytes("hi", "v1", output_format="wav_44100")
    body = json.loads(route.calls.last.request.content)
    assert body["voice_settings"]["use_speaker_boost"] is False
    assert body["apply_text_normalization"] == "off"


@respx.mock
def test_expanded_emotion_maps_to_profile():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)
    provider.synthesize_bytes(
        "rest now.", "v1", output_format="wav_44100",
        voice_settings={"emotion": "soothing", "content_type": "podcast"},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["voice_settings"]["stability"] == EMOTION_PROFILES["soothing"]["stability"]
