import shutil

import pytest

from app.config import Settings
from app.core import orchestrator
from app.core.errors import AmbientBedError, VoiceAssignmentError
from app.core.models import PodcastRequest, SleepStoryRequest
from app.providers import registry

from .conftest import FakeProvider

ffmpeg_missing = shutil.which("ffmpeg") is None
needs_ffmpeg = pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")


@pytest.fixture
def settings(tmp_path):
    return Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_mp3=False,
        inter_turn_gap_ms=100,
        ambient_dir=tmp_path / "ambient",
    )


@pytest.fixture
def fake(clean_registry):
    provider = FakeProvider()
    registry.register(provider)
    return provider


@needs_ffmpeg
def test_podcast_run_produces_master_and_progress(settings, fake):
    events = []
    req = PodcastRequest(
        script_text="[Speaker 1]: hello there friend\n[Speaker 2]: hi back to you",
        speakers={
            "Speaker 1": {"provider": "fake", "voice_id": "a"},
            "Speaker 2": {"provider": "fake", "voice_id": "b"},
        },
    )
    result = orchestrator.run(
        req,
        settings,
        lambda **kw: events.append(kw),
        job_id="jobpod",
    )
    assert len(result.segments) == 2
    assert result.files and result.files[0].filename == "episode.wav"
    assert (tmp := settings.output_dir) and (events[-1]["chunks_done"] == events[-1]["chunks_total"])
    # working dir cleaned up
    from pathlib import Path

    assert not (Path(settings.output_dir) / "jobpod" / "_chunks").exists()


def test_podcast_missing_voice_raises(settings, fake):
    req = PodcastRequest(
        script_text="[Speaker 1]: hi\n[Speaker 2]: yo",
        speakers={"Speaker 1": {"provider": "fake", "voice_id": "a"}},
    )
    with pytest.raises(VoiceAssignmentError):
        orchestrator.run(req, settings, job_id="x")


@needs_ffmpeg
def test_sleep_run_threads_speed_to_provider(settings, fake):
    req = SleepStoryRequest(
        prose_text="Once upon a time. The night was calm. Sleep came softly.",
        provider="fake",
        voice_id="narrator-voice",
        speed=0.85,
        pause_ms=200,
    )
    result = orchestrator.run(req, settings, job_id="jobsleep")
    assert result.segments[0].speaker == "narrator"
    # fake is not in the speed-aware set, so no speed injected...
    assert all(c["voice_settings"] is None for c in fake.synth_calls)


@needs_ffmpeg
def test_sleep_run_injects_speed_for_local_providers(settings, clean_registry):
    local = FakeProvider(name="kokoro")
    registry.register(local)
    req = SleepStoryRequest(
        prose_text="Breathe in. Breathe out.",
        provider="kokoro",
        voice_id="af_heart",
        speed=0.8,
        pause_ms=100,
    )
    orchestrator.run(req, settings, job_id="jobk")
    assert local.synth_calls
    assert all(c["voice_settings"] == {"speed": 0.8} for c in local.synth_calls)


def test_sleep_unknown_ambient_bed_raises(settings, fake):
    req = SleepStoryRequest(
        prose_text="A quiet story.",
        provider="fake",
        voice_id="v",
        ambient_bed="does-not-exist",
    )
    with pytest.raises(AmbientBedError):
        orchestrator.run(req, settings, job_id="x")
