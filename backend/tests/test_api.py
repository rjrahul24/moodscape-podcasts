import io
import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydub import AudioSegment

from app.config import Settings, get_settings
from app.core.stitcher import numpy_to_segment
from app.main import create_app
from app.providers import registry
from app.providers.bootstrap import bootstrap_providers

from .conftest import FakeProvider

ffmpeg_missing = shutil.which("ffmpeg") is None
needs_ffmpeg = pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")


@pytest.fixture
def client(tmp_path):
    app = create_app()
    settings = Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_wav=False,
        inter_turn_gap_ms=100,
        assets_dir=tmp_path / "assets",
        elevenlabs_api_key=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    registry.clear()
    bootstrap_providers(settings)
    registry.register(FakeProvider())
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    registry.clear()


def _wav_bytes(ms: int = 400, rate: int = 24000) -> bytes:
    n = int(rate * ms / 1000)
    t = np.arange(n) / rate
    seg = numpy_to_segment(0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32), rate)
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


def test_health_ok(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "fake" in body["providers"]


def test_voices_grouped_and_resilient(client):
    response = client.get("/api/voices")
    assert response.status_code == 200
    groups = {g["provider"]: g for g in response.json()}

    # The fake provider's voice is present.
    assert any(v["id"] == "fake-v1" for v in groups["fake"]["voices"])
    # Kokoro lists its static voices without any model load.
    assert groups["kokoro"]["voices"], "expected static Kokoro voices"
    # ElevenLabs has no key in tests -> it reports an error but does NOT break
    # the rest of the response.
    assert groups["elevenlabs"]["error"] is not None
    assert groups["elevenlabs"]["voices"] == []


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


@needs_ffmpeg
def test_upload_reference_voice_with_transcript(client, tmp_path):
    response = client.post(
        "/api/voices/reference",
        data={"name": "Calm River", "transcript": "the exact words spoken"},
        files={"audio": ("clip.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "calm_river"
    assert "f5" in body["providers"]
    assert body["transcript"] == "the exact words spoken"

    # Persisted into the shared registry layout, so any cloning provider
    # configured with this assets_dir lists it on its next scan.
    from app.providers import reference_voice_registry as rvr

    assert "calm_river" in rvr.scan(tmp_path / "assets")


@needs_ffmpeg
def test_upload_reference_voice_without_transcript_or_whisper_422(client, monkeypatch):
    # No transcript + no Whisper backend available -> clear 422.
    import sys

    monkeypatch.setitem(sys.modules, "mlx_whisper", None)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    response = client.post(
        "/api/voices/reference",
        data={"name": "No Transcript"},
        files={"audio": ("clip.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 422
    assert "transcript" in response.json()["detail"].lower()
