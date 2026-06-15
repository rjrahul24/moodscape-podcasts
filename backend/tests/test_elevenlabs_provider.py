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
