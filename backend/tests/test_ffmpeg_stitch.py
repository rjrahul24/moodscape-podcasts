import shutil
import wave

import pytest
from pydub import AudioSegment

from app.core import ffmpeg_stitch
from app.core.errors import AudioProcessingError

ffmpeg_missing = shutil.which("ffmpeg") is None
needs_ffmpeg = pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")


def test_build_concat_list_quotes_paths(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    list_file = tmp_path / "list.txt"
    ffmpeg_stitch.build_concat_list([a, b], list_file)
    content = list_file.read_text()
    assert f"file '{a.resolve()}'" in content
    assert f"file '{b.resolve()}'" in content


def test_run_ffmpeg_raises_on_bad_args(tmp_path):
    if ffmpeg_missing:
        pytest.skip("ffmpeg not on PATH")
    with pytest.raises(AudioProcessingError):
        ffmpeg_stitch.run_ffmpeg(["-i", str(tmp_path / "does-not-exist.wav"), str(tmp_path / "o.wav")])


@needs_ffmpeg
def test_segment_to_wav_file_normalizes(tmp_path):
    seg = AudioSegment.silent(duration=200, frame_rate=24000)
    out = ffmpeg_stitch.segment_to_wav_file(
        seg, tmp_path / "x.wav", sample_rate=44100, channels=2
    )
    with wave.open(str(out)) as w:
        assert w.getframerate() == 44100
        assert w.getnchannels() == 2


@needs_ffmpeg
def test_concat_roundtrip_sums_durations(tmp_path):
    a = ffmpeg_stitch.silence_wav(tmp_path / "a.wav", duration_ms=300, sample_rate=44100)
    b = ffmpeg_stitch.silence_wav(tmp_path / "b.wav", duration_ms=500, sample_rate=44100)
    lst = ffmpeg_stitch.build_concat_list([a, b], tmp_path / "list.txt")
    out = ffmpeg_stitch.concat(lst, tmp_path / "out.wav")
    combined = AudioSegment.from_file(out)
    assert abs(len(combined) - 800) < 60  # ~800ms within tolerance


@needs_ffmpeg
def test_normalize_loudness_returns_wav(tmp_path):
    # A tone (not pure silence) so loudnorm has something to measure.
    src = (AudioSegment.silent(duration=600, frame_rate=44100)
           .overlay(AudioSegment.silent(duration=600, frame_rate=44100)))
    src_path = tmp_path / "src.wav"
    src.export(src_path, format="wav")
    out = ffmpeg_stitch.normalize_loudness(
        src_path, tmp_path / "norm.wav", target_lufs=-21.0, sample_rate=44100
    )
    assert out.exists()
    with wave.open(str(out)) as w:
        assert w.getframerate() == 44100
        # Duration is preserved by a single loudnorm pass (within tolerance).
        assert abs(w.getnframes() / 44100 * 1000 - 600) < 80


@needs_ffmpeg
def test_transcode_mp3(tmp_path):
    wav = ffmpeg_stitch.silence_wav(tmp_path / "a.wav", duration_ms=300, sample_rate=44100)
    mp3 = ffmpeg_stitch.transcode_mp3(wav, tmp_path / "a.mp3")
    assert mp3.exists() and mp3.stat().st_size > 0


@needs_ffmpeg
def test_transcode_m4a(tmp_path):
    wav = ffmpeg_stitch.silence_wav(tmp_path / "a.wav", duration_ms=300, sample_rate=44100)
    m4a = ffmpeg_stitch.transcode_m4a(wav, tmp_path / "a.m4a")
    assert m4a.exists() and m4a.stat().st_size > 0
