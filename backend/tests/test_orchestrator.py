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
            # Untagged prose gets the default calm tone injected (v3 -> [calm]).
            "emotion": "soothing",
        }


@needs_ffmpeg
def test_sleep_v3_splices_pause_marker_into_silence(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = SleepStoryRequest(
        prose_text="The lake is still. [pause:1000] Sleep now.",
        provider="elevenlabs",
        voice_id="rachel",
        model_id="eleven_v3",
        ramp=False,
    )
    orchestrator.run(req, settings, job_id="jobv3pause")
    texts = [c["text"] for c in el.synth_calls]
    # v3 has no native break: the marker is split out (never sent to the model) and
    # the breath becomes real silence between two synthesized segments.
    assert all("pause" not in t for t in texts)
    assert any("The lake is still." in t for t in texts)
    assert any("Sleep now." in t for t in texts)


@needs_ffmpeg
def test_sleep_v3_splices_bare_pause_into_silence(settings, clean_registry):
    """A bare [pause] (no duration) should also splice silence for v3."""
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = SleepStoryRequest(
        prose_text="The lake is still. [pause] Sleep now.",
        provider="elevenlabs",
        voice_id="rachel",
        model_id="eleven_v3",
        ramp=False,
    )
    orchestrator.run(req, settings, job_id="jobv3bare")
    texts = [c["text"] for c in el.synth_calls]
    assert all("pause" not in t.lower() for t in texts)
    assert any("The lake is still." in t for t in texts)
    assert any("Sleep now." in t for t in texts)


@needs_ffmpeg
def test_sleep_leading_tone_tag_becomes_emotion_and_is_stripped(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = SleepStoryRequest(
        prose_text="[warm] The fire has already been lit.",
        provider="elevenlabs",
        voice_id="rachel",
        model_id="eleven_multilingual_v2",
        ramp=False,
    )
    orchestrator.run(req, settings, job_id="jobtone")
    assert len(el.synth_calls) == 1
    call = el.synth_calls[0]
    # The author's [warm] drives the emotion (v2 maps it to a warmer profile) and is
    # removed from the text so it's never spoken or double-tagged.
    assert call["voice_settings"]["emotion"] == "warm"
    assert call["text"] == "The fire has already been lit."


@needs_ffmpeg
def test_sleep_v2_keeps_pause_marker_for_native_break(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    registry.register(el)
    req = SleepStoryRequest(
        prose_text="The lake is still. [pause:1000] Sleep now.",
        provider="elevenlabs",
        voice_id="rachel",
        model_id="eleven_multilingual_v2",
        ramp=False,
    )
    orchestrator.run(req, settings, job_id="jobv2pause")
    # v2 renders the breath natively: the orchestrator leaves the marker inline in a
    # single synth call (the provider translates it to a <break>).
    assert len(el.synth_calls) == 1
    assert "[pause:1000]" in el.synth_calls[0]["text"]


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


@needs_ffmpeg
def test_sleep_preroll_prepends_silence_when_ambient_bed_set(tmp_path, clean_registry):
    """With an ambient bed selected, a pre-roll silence is prepended so the bed
    plays alone before the narration starts."""
    import wave

    fake = FakeProvider(name="fake")
    clean_registry.register(fake)

    ambient_dir = tmp_path / "ambient"
    ambient_dir.mkdir()
    from pydub import AudioSegment

    AudioSegment.silent(duration=5000, frame_rate=44100).export(
        ambient_dir / "rain.wav", format="wav"
    )

    settings = Settings(
        output_dir=str(tmp_path / "out"),
        also_export_mp3=False,
        ambient_dir=ambient_dir,
        sleep_preroll_s=3.0,
    )
    req = SleepStoryRequest(
        prose_text="The night is calm.",
        provider="fake",
        voice_id="v",
        ambient_bed="rain",
        pause_ms=0,
    )
    result = orchestrator.run(req, settings, job_id="jobpreroll")
    # Duration should include the 3-second pre-roll (3000 ms).
    assert result.duration_ms >= 3000


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


@needs_ffmpeg
def test_sleep_ellipsis_injected_for_elevenlabs_when_enabled(tmp_path, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    clean_registry.register(el)
    settings = Settings(
        output_dir=str(tmp_path), also_export_mp3=False,
        sleep_sentence_ellipsis=True,
    )
    req = SleepStoryRequest(
        prose_text="The night was calm. Sleep came softly.",
        provider="elevenlabs", voice_id="rachel", model_id="eleven_v3", pause_ms=0,
    )
    orchestrator.run(req, settings, job_id="jobell")
    assert any("…" in c["text"] for c in el.synth_calls)


@needs_ffmpeg
def test_sleep_ellipsis_off_by_default(settings, clean_registry):
    el = FakeProvider(name="elevenlabs", has_native_speed=True)
    clean_registry.register(el)
    req = SleepStoryRequest(
        prose_text="The night was calm. Sleep came softly.",
        provider="elevenlabs", voice_id="rachel", model_id="eleven_v3", pause_ms=0,
    )
    orchestrator.run(req, settings, job_id="jobnoell")
    assert all("…" not in c["text"] for c in el.synth_calls)


@needs_ffmpeg
def test_sleep_per_chunk_normalization_runs_for_long_chunks(tmp_path, clean_registry, monkeypatch):
    # Chunk longer than the guard so normalization fires; spy on the helper.
    el = FakeProvider(name="elevenlabs", duration_ms=500, has_native_speed=True)
    clean_registry.register(el)
    calls: list[tuple] = []
    real = orchestrator.ffmpeg_stitch.normalize_loudness

    def spy(in_wav, out_wav, **kw):
        calls.append((in_wav, out_wav, kw))
        return real(in_wav, out_wav, **kw)

    monkeypatch.setattr(orchestrator.ffmpeg_stitch, "normalize_loudness", spy)
    settings = Settings(output_dir=str(tmp_path), also_export_mp3=False)
    req = SleepStoryRequest(
        prose_text="The lake is still.", provider="elevenlabs",
        voice_id="rachel", model_id="eleven_v3", pause_ms=0,
    )
    orchestrator.run(req, settings, job_id="jobnorm")
    assert calls, "normalize_loudness should run for >=400ms chunks"
    assert all(kw["target_lufs"] == settings.sleep_chunk_norm_lufs for _, _, kw in calls)


@needs_ffmpeg
def test_sleep_per_chunk_normalization_skips_short_chunks(tmp_path, clean_registry, monkeypatch):
    el = FakeProvider(name="elevenlabs", duration_ms=200, has_native_speed=True)
    clean_registry.register(el)
    calls: list = []
    monkeypatch.setattr(
        orchestrator.ffmpeg_stitch, "normalize_loudness",
        lambda *a, **k: calls.append(a) or a[1],
    )
    settings = Settings(output_dir=str(tmp_path), also_export_mp3=False)
    req = SleepStoryRequest(
        prose_text="The lake is still.", provider="elevenlabs",
        voice_id="rachel", model_id="eleven_v3", pause_ms=0,
    )
    orchestrator.run(req, settings, job_id="jobshort")
    assert not calls, "chunks under the min-ms guard must skip normalization"


# ── F5 text normalization + sleep settings ─────────────────────────────────────


@needs_ffmpeg
def test_sleep_f5_text_normalized(clean_registry, tmp_path):
    """F5 sleep stories should have text normalized (colons->commas, etc.)."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(output_dir=str(tmp_path / "out"))
    request = SleepStoryRequest(
        prose_text="Rest now: find well-being... BREATHE deeply.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-norm")

    # Check that the text passed to synthesize was normalized
    texts = [c["text"] for c in fake.synth_calls]
    combined = " ".join(texts)
    assert ":" not in combined  # colons removed
    assert "..." not in combined  # ellipses removed
    assert "BREATHE" not in combined  # ALL_CAPS lowered


@needs_ffmpeg
def test_sleep_f5_voice_settings_has_nfe_and_content_type(clean_registry, tmp_path):
    """F5 sleep stories should pass nfe_step and content_type in voice_settings."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(
        output_dir=str(tmp_path / "out"),
        f5_sleep_nfe_step=32,
    )
    request = SleepStoryRequest(
        prose_text="The night is calm.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-vs")

    vs = fake.synth_calls[0]["voice_settings"]
    assert vs["nfe_step"] == 32
    assert vs["content_type"] == "sleep"


@needs_ffmpeg
def test_sleep_f5_uses_sleep_speed(clean_registry, tmp_path):
    """F5 sleep should use f5_sleep_speed as the base, not sleep_default_speed."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(
        output_dir=str(tmp_path / "out"),
        f5_sleep_speed=0.88,
        sleep_default_speed=0.78,  # this should NOT be used for F5
    )
    request = SleepStoryRequest(
        prose_text="The night is calm and still.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-speed")

    vs = fake.synth_calls[0]["voice_settings"]
    assert vs["speed"] == pytest.approx(0.88, abs=0.05)
