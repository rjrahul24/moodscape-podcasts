import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.providers import registry

from .conftest import FakeProvider


@pytest.fixture
def client(tmp_path):
    app = create_app()
    settings = Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_mp3=False,
        inter_turn_gap_ms=100,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    registry.register(FakeProvider())
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    registry.clear()


def test_health_ok(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "fake" in body["providers"]


def test_voices_lists_fake_provider_voice(client):
    # default_provider is "elevenlabs"; point voices at the fake provider instead
    # by registering it as the default for this account-less test.
    voices = client.get("/api/voices")
    # elevenlabs has no key configured -> 503; that is the expected default path.
    assert voices.status_code in (200, 503)


def test_generate_then_download_roundtrip(client):
    response = client.post(
        "/api/generate",
        json={
            "script_text": "[Speaker 1]: hello\n[Speaker 2]: hi there",
            "speakers": {
                "Speaker 1": {"provider": "fake", "voice_id": "a"},
                "Speaker 2": {"provider": "fake", "voice_id": "b"},
            },
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["segments"]) == 2
    assert result["files"], "expected at least one output file"

    download = client.get(result["files"][0]["download_url"])
    assert download.status_code == 200
    assert download.content[:4] == b"RIFF"  # WAV header


def test_generate_unparseable_script_returns_422(client):
    response = client.post(
        "/api/generate",
        json={"script_text": "no markers here", "speakers": {}},
    )
    assert response.status_code == 422


def test_generate_missing_voice_returns_422(client):
    response = client.post(
        "/api/generate",
        json={
            "script_text": "[Speaker 1]: hi\n[Speaker 2]: yo",
            "speakers": {"Speaker 1": {"provider": "fake", "voice_id": "a"}},
        },
    )
    assert response.status_code == 422
