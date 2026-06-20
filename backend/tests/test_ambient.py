"""Unit tests for the ambient-bed filtergraph (string-level, no ffmpeg needed)."""

from app.core import ambient


def _graph(**overrides):
    kwargs = dict(
        story_ms=60_000,
        bed_gain_db=-22.0,
        fade_s=5.0,
        sample_rate=44100,
        lowpass_hz=3000,
        highpass_hz=90,
        duck=True,
        duck_ratio=4.0,
        duck_threshold_db=-30.0,
        duck_release_ms=600,
    )
    kwargs.update(overrides)
    return ambient.build_filter_complex(**kwargs)


def test_bed_is_band_limited_and_softened():
    g = _graph()
    assert "highpass=f=90" in g
    assert "lowpass=f=3000" in g
    assert "volume=-22.0dB" in g
    # Output stays exactly the narration length.
    assert "amix=inputs=2:duration=first:dropout_transition=0[out]" in g


def test_ducking_adds_sidechain_and_splits_voice():
    g = _graph(duck=True)
    assert "asplit=2[v0][vkey]" in g
    assert "sidechaincompress=threshold=" in g
    assert "ratio=4.0" in g
    # -30 dB threshold -> ~0.0316 linear amplitude.
    assert "threshold=0.031623" in g


def test_ducking_off_has_no_sidechain():
    g = _graph(duck=False)
    assert "sidechaincompress" not in g
    assert "asplit" not in g
    assert "amix=inputs=2:duration=first" in g


def test_bed_loudness_normalized():
    g = _graph()
    assert "loudnorm=I=-24.0:TP=-2:LRA=11" in g


def test_bed_loudness_custom_target():
    g = _graph(bed_target_lufs=-20.0)
    assert "loudnorm=I=-20.0:TP=-2:LRA=11" in g
