import httpx
import pytest
import respx

from app.core.errors import ProviderError
from app.providers.elevenlabs_provider import ElevenLabsProvider

BASE = "https://api.elevenlabs.io"


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
def test_synthesize_returns_audio_bytes_and_sends_format():
    route = respx.post(f"{BASE}/v1/text-to-speech/v1").mock(
        return_value=httpx.Response(200, content=b"FAKEAUDIO")
    )
    provider = ElevenLabsProvider("test-key", base_url=BASE)

    audio = provider.synthesize("hello", "v1", output_format="wav_44100")

    assert audio == b"FAKEAUDIO"
    request = route.calls.last.request
    assert request.url.params["output_format"] == "wav_44100"
    assert request.headers["xi-api-key"] == "test-key"


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
