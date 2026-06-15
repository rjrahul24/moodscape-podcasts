import shutil
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.providers import registry

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
        also_export_mp3=False,
        inter_turn_gap_ms=50,
        ambient_dir=tmp_path / "ambient",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    registry.register(FakeProvider())
    registry.register(FakeProvider(name="kokoro"))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    registry.clear()


def _wait_for_terminal(client, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["progress"]["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.1)
    raise AssertionError("job did not finish in time")


@needs_ffmpeg
def test_podcast_job_roundtrip(client):
    resp = client.post(
        "/api/jobs",
        json={
            "kind": "podcast",
            "script_text": "[Speaker 1]: hello\n[Speaker 2]: hi there",
            "speakers": {
                "Speaker 1": {"provider": "fake", "voice_id": "a"},
                "Speaker 2": {"provider": "fake", "voice_id": "b"},
            },
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    body = _wait_for_terminal(client, job_id)
    assert body["progress"]["status"] == "succeeded", body
    assert body["result"]["files"], "expected output files"

    download = client.get(body["result"]["files"][0]["download_url"])
    assert download.status_code == 200
    assert download.content[:4] == b"RIFF"


@needs_ffmpeg
def test_sleep_job_roundtrip(client):
    resp = client.post(
        "/api/jobs",
        json={
            "kind": "sleep_story",
            "prose_text": "The forest was still. A gentle breeze drifted by. All was calm.",
            "provider": "kokoro",
            "voice_id": "af_heart",
            "speed": 0.85,
            "pause_ms": 100,
        },
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    body = _wait_for_terminal(client, job_id)
    assert body["progress"]["status"] == "succeeded", body
    assert body["result"]["segments"][0]["speaker"] == "narrator"


def test_job_not_found_returns_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


@needs_ffmpeg
def test_sse_stream_emits_done(client):
    resp = client.post(
        "/api/jobs",
        json={
            "kind": "podcast",
            "script_text": "[Speaker 1]: hello there",
            "speakers": {"Speaker 1": {"provider": "fake", "voice_id": "a"}},
        },
    )
    job_id = resp.json()["job_id"]
    # Drain the SSE stream; it should terminate with a 'done' event.
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        text = "".join(chunk for chunk in stream.iter_text())
    assert "event: done" in text


def test_ambient_endpoint_empty_by_default(client):
    assert client.get("/api/ambient").json() == []
