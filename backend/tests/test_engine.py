import pytest

from app.config import Settings
from app.core import engine
from app.core.errors import VoiceAssignmentError
from app.core.models import GenerateRequest, SpeakerVoice

from .conftest import FakeProvider


def _settings(tmp_path) -> Settings:
    return Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_mp3=False,
        inter_turn_gap_ms=100,
    )


def test_generates_stitched_episode(tmp_path, clean_registry):
    clean_registry.register(FakeProvider(duration_ms=300))
    request = GenerateRequest(
        script_text="[Speaker 1]: hello\n[Speaker 2]: hi",
        speakers={
            "Speaker 1": SpeakerVoice(provider="fake", voice_id="a"),
            "Speaker 2": SpeakerVoice(provider="fake", voice_id="b"),
        },
    )

    result = engine.generate(request, _settings(tmp_path))

    # 300 + 100 gap + 300
    assert abs(result.duration_ms - 700) < 60
    assert [s.speaker for s in result.segments] == ["Speaker 1", "Speaker 2"]
    assert len(result.files) == 1
    written = tmp_path / result.job_id / "episode.wav"
    assert written.is_file()
    assert result.files[0].download_url == f"/api/download/{result.job_id}/episode.wav"


def test_missing_voice_assignment_raises(tmp_path, clean_registry):
    clean_registry.register(FakeProvider())
    request = GenerateRequest(
        script_text="[Speaker 1]: hi\n[Speaker 2]: yo",
        speakers={"Speaker 1": SpeakerVoice(provider="fake", voice_id="a")},
    )
    with pytest.raises(VoiceAssignmentError):
        engine.generate(request, _settings(tmp_path))


def test_mixes_providers_across_speakers(tmp_path, clean_registry):
    """Extensibility check: two providers, one per speaker, no engine changes."""
    fake_a = FakeProvider(name="fake_a", duration_ms=200)
    fake_b = FakeProvider(name="fake_b", duration_ms=200)
    clean_registry.register(fake_a)
    clean_registry.register(fake_b)

    request = GenerateRequest(
        script_text="[Host]: intro\n[Guest]: reply",
        speakers={
            "Host": SpeakerVoice(provider="fake_a", voice_id="h"),
            "Guest": SpeakerVoice(provider="fake_b", voice_id="g"),
        },
    )

    result = engine.generate(request, _settings(tmp_path))
    assert fake_a.calls == [("h", "intro")]
    assert fake_b.calls == [("g", "reply")]
    assert {s.provider for s in result.segments} == {"fake_a", "fake_b"}
