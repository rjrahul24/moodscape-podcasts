import json
from io import BytesIO

import httpx
import pytest
import respx
from pydub import AudioSegment

from app.core.errors import ProviderError
from app.providers.elevenlabs_provider import ElevenLabsProvider

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
    }
    assert "emotion" not in body["voice_settings"]
    assert "content_type" not in body["voice_settings"]


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
    # Sleep base profile (calm) + native speed clamped up to the 0.7 floor.
    assert body["voice_settings"]["stability"] == 0.88
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
    # No hints -> v2 podcast base profile (expressive default).
    assert body["voice_settings"] == {
        "stability": 0.45,
        "similarity_boost": 0.80,
        "style": 0.45,
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
