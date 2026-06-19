import shutil

import pytest

from app.config import Settings
from app.core import sleep_post

ffmpeg_missing = shutil.which("ffmpeg") is None


def test_build_filtergraph_contains_expected_filters():
    af = sleep_post.build_filtergraph(
        total_s=60.0,
        fade_in_s=2.0,
        fade_out_s=5.0,
        lowpass_hz=8000,
        target_lufs=-18.0,
        true_peak_db=-2.0,
        sample_rate=44100,
        channels=2,
    )
    assert "acompressor" in af
    assert "lowpass=f=8000" in af
    assert "loudnorm=I=-18.0:TP=-2.0" in af
    assert "afade=t=in:st=0:d=2.0" in af
    assert "afade=t=out:st=55.000:d=5.0" in af
    assert "channel_layouts=stereo" in af


def test_build_filtergraph_clamps_fade_out_for_short_audio():
    af = sleep_post.build_filtergraph(
        total_s=3.0,
        fade_in_s=2.0,
        fade_out_s=5.0,
        lowpass_hz=8000,
        target_lufs=-18.0,
        true_peak_db=-2.0,
        sample_rate=44100,
        channels=2,
    )
    assert "afade=t=out:st=0.000:d=5.0" in af


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not on PATH")
def test_process_produces_stereo_master(tmp_path):
    from app.core import ffmpeg_stitch

    src = ffmpeg_stitch.silence_wav(
        tmp_path / "in.wav", duration_ms=1500, sample_rate=24000
    )
    settings = Settings(output_dir=str(tmp_path))
    out = sleep_post.process(
        src, tmp_path / "out.wav", settings=settings, total_ms=1500
    )
    import wave

    with wave.open(str(out)) as w:
        assert w.getframerate() == settings.sleep_sample_rate
        assert w.getnchannels() == settings.sleep_channels
