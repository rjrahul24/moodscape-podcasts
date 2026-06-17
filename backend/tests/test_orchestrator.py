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


@needs_ffmpeg
def test_podcast_pacing_passes_emotion_and_jittered_speed(settings, clean_registry):
    local = FakeProvider(name="kokoro", consumes_local_speed=True)
    registry.register(local)
    req = PodcastRequest(
        script_text="[Speaker 1]: [excited] This is great. I really love it.",
        speakers={"Speaker 1": {"provider": "kokoro", "voice_id": "af_heart"}},
    )
    result = orchestrator.run(req, settings, job_id="jobpace")
    # Two sentences -> two speech chunks, both carrying the tone tag.
    assert len(local.synth_calls) == 2
    for c in local.synth_calls:
        assert c["voice_settings"]["emotion"] == "excited"
        assert 0.9 < c["voice_settings"]["speed"] < 1.1  # jittered around 1.0
        assert "[excited]" not in c["text"]  # tag stripped before synthesis
    # An inter-sentence micro-pause was inserted, so the master is longer than
    # the raw speech alone (2 x 300 ms fake segments).
    assert result.duration_ms > 600


@needs_ffmpeg
def test_podcast_pacing_is_deterministic(settings, clean_registry):
    script = "[Speaker 1]: One. Two. Three.\n[Speaker 2]: Four. Five."
    speakers = {
        "Speaker 1": {"provider": "kokoro", "voice_id": "a"},
        "Speaker 2": {"provider": "kokoro", "voice_id": "b"},
    }

    def run_once():
        registry.clear()
        p = FakeProvider(name="kokoro", consumes_local_speed=True)
        registry.register(p)
        orchestrator.run(
            PodcastRequest(script_text=script, speakers=speakers), settings, job_id="seed1"
        )
        return [c["voice_settings"]["speed"] for c in p.synth_calls]

    assert run_once() == run_once()


@needs_ffmpeg
def test_podcast_pacing_off_reproduces_legacy_flat(settings, fake):
    req = PodcastRequest(
        script_text="[Speaker 1]: hello there friend. nice to meet you.",
        speakers={"Speaker 1": {"provider": "fake", "voice_id": "a"}},
        pacing=False,
    )
    orchestrator.run(req, settings, job_id="joblegacy")
    # Legacy path: one block per turn, no per-chunk voice_settings, no splitting.
    assert len(fake.synth_calls) == 1
    assert all(c["voice_settings"] is None for c in fake.synth_calls)


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
    local = FakeProvider(name="kokoro", consumes_local_speed=True)
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


@needs_ffmpeg
def test_sleep_run_builds_calm_settings_for_elevenlabs(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = SleepStoryRequest(
        prose_text="The night was calm. Sleep came softly.",
        provider="elevenlabs",
        voice_id="rachel",
        model_id="eleven_v3",
        speed=0.85,
        pause_ms=100,
    )
    orchestrator.run(req, settings, job_id="jobels")
    assert el.synth_calls
    for c in el.synth_calls:
        assert c["voice_settings"] == {
            "content_type": "sleep",
            "speed": 0.85,
            "model_id": "eleven_v3",
        }


@needs_ffmpeg
def test_podcast_passes_content_type_and_model_to_elevenlabs(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = PodcastRequest(
        script_text="[Speaker 1]: [calm] Welcome in. Settle for a moment.",
        speakers={"Speaker 1": {"provider": "elevenlabs", "voice_id": "rachel", "model_id": "eleven_v3"}},
    )
    orchestrator.run(req, settings, job_id="jobelp")
    assert el.synth_calls
    for c in el.synth_calls:
        vs = c["voice_settings"]
        assert vs["content_type"] == "podcast"
        assert vs["model_id"] == "eleven_v3"
        assert vs["emotion"] == "calm"
        assert 0.9 < vs["speed"] < 1.1  # native speed, jittered around 1.0
        assert "[calm]" not in c["text"]  # tag stripped by the planner


def test_sleep_unknown_ambient_bed_raises(settings, fake):
    req = SleepStoryRequest(
        prose_text="A quiet story.",
        provider="fake",
        voice_id="v",
        ambient_bed="does-not-exist",
    )
    with pytest.raises(AmbientBedError):
        orchestrator.run(req, settings, job_id="x")
