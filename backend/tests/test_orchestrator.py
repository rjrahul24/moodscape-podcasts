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
def test_breath_tag_routes_by_provider_capability(settings, clean_registry):
    """A non-inline provider turns [deep_breath] into a silence; an inline-SFX
    provider keeps it in the synthesized text."""
    script = "[Speaker 1]: Settle in. [deep_breath] And rest."

    # Default (no inline SFX): tag becomes a pause, never spoken.
    plain = FakeProvider(name="kokoro", consumes_local_speed=True)
    registry.register(plain)
    orchestrator.run(
        PodcastRequest(
            script_text=script,
            speakers={"Speaker 1": {"provider": "kokoro", "voice_id": "a"}},
        ),
        settings,
        job_id="jobsfx1",
    )
    assert all("[deep_breath]" not in c["text"] for c in plain.synth_calls)

    # Inline-SFX provider: the tag stays in the text for the model to perform.
    registry.clear()
    performer = FakeProvider(name="perf", accepts_inline_sfx=True)
    registry.register(performer)
    orchestrator.run(
        PodcastRequest(
            script_text=script,
            speakers={"Speaker 1": {"provider": "perf", "voice_id": "a"}},
        ),
        settings,
        job_id="jobsfx2",
    )
    assert any("[deep_breath]" in c["text"] for c in performer.synth_calls)


@needs_ffmpeg
def test_qc_runs_only_when_enabled(settings, fake, monkeypatch):
    """enable_qc gates the post-step; when on, run_qc gets the master + source."""
    from app.core import qc as qc_mod
    from app.core.models import QCReport

    captured = {}

    def fake_run_qc(audio_path, *, source_text, settings, reference_audio=None):
        captured.update(
            audio_path=audio_path, source_text=source_text, reference_audio=reference_audio
        )
        return QCReport(wer=0.0, notes=["faked"])

    monkeypatch.setattr(qc_mod, "run_qc", fake_run_qc)
    req = PodcastRequest(
        script_text="[Speaker 1]: hello there friend",
        speakers={"Speaker 1": {"provider": "fake", "voice_id": "a"}},
    )

    # Off by default: no QC.
    result = orchestrator.run(req, settings, job_id="jobqcoff")
    assert result.qc is None
    assert not captured

    # On: QC attached, fed the master path and the (markup-aware) source text.
    qc_settings = settings.model_copy(update={"enable_qc": True})
    result = orchestrator.run(req, qc_settings, job_id="jobqcon")
    assert result.qc is not None and result.qc.wer == 0.0
    assert captured["audio_path"].endswith("episode.wav")
    assert "hello there friend" in captured["source_text"]
    assert captured["reference_audio"] is None  # fake provider isn't a cloner


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
def test_sleep_run_injects_instruct_for_cosyvoice(settings, clean_registry):
    cosy = FakeProvider(name="cosyvoice", accepts_instruct=True)
    registry.register(cosy)
    req = SleepStoryRequest(
        prose_text="The night was calm. Sleep came softly.",
        provider="cosyvoice",
        voice_id="david",
    )
    orchestrator.run(req, settings, job_id="jobcosy")
    assert cosy.synth_calls
    # The configured sleep directive is injected (delivery, not numeric speed).
    for c in cosy.synth_calls:
        assert c["voice_settings"]["instruct"] == settings.cosyvoice_sleep_instruct


@needs_ffmpeg
def test_sleep_run_style_prompt_overrides_instruct(settings, clean_registry):
    cosy = FakeProvider(name="cosyvoice", accepts_instruct=True)
    registry.register(cosy)
    req = SleepStoryRequest(
        prose_text="A quiet story.",
        provider="cosyvoice",
        voice_id="david",
        style_prompt="Whisper very slowly.",
    )
    orchestrator.run(req, settings, job_id="jobcosy2")
    assert cosy.synth_calls
    for c in cosy.synth_calls:
        assert c["voice_settings"] == {"instruct": "Whisper very slowly."}


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
        assert vs["speed"] == 1.0  # fixed base speed for cloud providers (no jitter)
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


# ── continuity + sleep ramp-down ────────────────────────────────────────────────


@needs_ffmpeg
def test_continuity_injected_for_capable_provider(settings, clean_registry):
    """A continuity-capable provider receives prev/next context across chunks."""
    el = FakeProvider(name="elevenlabs", has_native_speed=True, accepts_continuity=True)
    registry.register(el)
    req = PodcastRequest(
        script_text="[Speaker 1]: One. Two. Three.",
        speakers={"Speaker 1": {"provider": "elevenlabs", "voice_id": "rachel"}},
        seed=7,
    )
    orchestrator.run(req, settings, job_id="jobcont")
    calls = el.synth_calls
    assert len(calls) == 3
    # First has no previous context but looks ahead; middle has both; last only back.
    assert "previous_text" not in calls[0]["voice_settings"]
    assert calls[0]["voice_settings"]["next_text"]
    assert calls[1]["voice_settings"]["previous_text"]
    assert calls[1]["voice_settings"]["next_text"]
    assert calls[2]["voice_settings"]["previous_text"]
    assert "next_text" not in calls[2]["voice_settings"]
    # The seed rides along for capable providers.
    assert all(c["voice_settings"]["seed"] == 7 for c in calls)


@needs_ffmpeg
def test_continuity_skipped_without_capability(settings, clean_registry):
    """has_native_speed alone (no accepts_continuity) gets no prev/next/seed."""
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = PodcastRequest(
        script_text="[Speaker 1]: One. Two. Three.",
        speakers={"Speaker 1": {"provider": "elevenlabs", "voice_id": "rachel"}},
        seed=7,
    )
    orchestrator.run(req, settings, job_id="jobnocont")
    for c in el.synth_calls:
        assert "previous_text" not in c["voice_settings"]
        assert "next_text" not in c["voice_settings"]
        assert "seed" not in c["voice_settings"]


def test_sleep_ramp_decelerates_and_lengthens_pauses(settings):
    """With ramp on, per-chunk speed eases down and pauses grow, monotonically."""
    req = SleepStoryRequest(prose_text="x", provider="elevenlabs", voice_id="v", ramp=True)
    total = 5
    results = [
        orchestrator._sleep_ramp(req, 0.90, 800, i, total, settings)
        for i in range(total)
    ]
    speeds = [s for s, _ in results]
    pauses = [p for _, p in results]
    assert speeds[0] == 0.90  # first chunk at full baseline
    assert speeds == sorted(speeds, reverse=True) and speeds[0] > speeds[-1]
    assert pauses[0] == 800
    assert pauses == sorted(pauses) and pauses[-1] > pauses[0]


def test_sleep_ramp_off_holds_fixed_values(settings):
    req = SleepStoryRequest(prose_text="x", provider="elevenlabs", voice_id="v", ramp=False)
    for i in range(4):
        assert orchestrator._sleep_ramp(req, 0.85, 900, i, 4, settings) == (0.85, 900)


@needs_ffmpeg
def test_sleep_numbers_are_spelled_before_synthesis(settings, fake):
    req = SleepStoryRequest(
        prose_text="Count 3 breaths.",
        provider="fake",
        voice_id="narrator",
        pause_ms=0,
    )
    orchestrator.run(req, settings, job_id="jobnum")
    assert any("three" in c["text"] for c in fake.synth_calls)
    assert all("3" not in c["text"] for c in fake.synth_calls)
