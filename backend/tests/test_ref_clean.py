"""Reference-clip hygiene + registry-save tests.

The hygiene helpers take an in-memory ``AudioSegment`` so they need no ffmpeg; the
optional denoiser is faked. Registry save/slugify is plain filesystem work.
"""

import sys
import types

import numpy as np
import pytest

from app.config import Settings
from app.core import ref_clean
from app.core.stitcher import numpy_to_segment
from app.providers import reference_voice_registry as rvr


def _tone(ms: int, rate: int = 24000, freq: float = 220.0):
    n = int(rate * ms / 1000)
    t = np.arange(n) / rate
    return numpy_to_segment(0.5 * np.sin(2 * np.pi * freq * t).astype(np.float32), rate)


# ── hygiene helpers ──────────────────────────────────────────────────────────
def test_cap_length_trims_overlong_clip():
    from pydub import AudioSegment

    seg, note = ref_clean._cap_length(AudioSegment.silent(duration=3000), 1.0)
    assert len(seg) == 1000
    assert note and "30s" not in note  # message reflects the 1s cap we passed


def test_trim_silence_removes_head_and_tail():
    from pydub import AudioSegment

    clip = AudioSegment.silent(duration=200) + _tone(300) + AudioSegment.silent(duration=200)
    trimmed, note = ref_clean._trim_silence(clip)
    assert note and "trimmed" in note
    assert len(trimmed) < len(clip)
    assert 250 <= len(trimmed) <= 360  # ~the 300ms tone survives


def test_denoise_degrades_without_noisereduce(monkeypatch):
    monkeypatch.setitem(sys.modules, "noisereduce", None)
    seg = _tone(200)
    out, note = ref_clean._denoise(seg, 24000)
    assert out is seg  # unchanged
    assert note and "uv sync --extra clean" in note


def test_denoise_applies_when_available(monkeypatch):
    captured = {}

    def reduce_noise(*, y, sr):
        captured["sr"] = sr
        return y  # passthrough is enough to exercise the round-trip

    mod = types.ModuleType("noisereduce")
    mod.reduce_noise = reduce_noise
    monkeypatch.setitem(sys.modules, "noisereduce", mod)

    out, note = ref_clean._denoise(_tone(200, rate=16000), 16000)
    assert captured["sr"] == 16000
    assert note == "denoised (noisereduce)"
    assert out.frame_rate == 16000


# ── registry save / slugify ──────────────────────────────────────────────────
def test_slugify():
    assert rvr.slugify("  Calm Brittney! ") == "calm_brittney"
    assert rvr.slugify("Voice #2 (warm)") == "voice_2_warm"


def test_save_then_scan_roundtrip(tmp_path):
    src = tmp_path / "clip.wav"
    _tone(300).export(src, format="wav")

    paths = rvr.save(tmp_path, "calm_river", src, "  the exact words  ")
    assert paths["audio"].is_file()
    assert paths["transcript"].read_text(encoding="utf-8") == "the exact words"

    found = rvr.scan(tmp_path)
    assert "calm_river" in found


def test_clean_clip_writes_mono_resampled_wav(tmp_path):
    from pydub import AudioSegment

    src = tmp_path / "in.wav"
    _tone(500).set_channels(2).export(src, format="wav")
    dst = tmp_path / "out.wav"
    settings = Settings(reference_clip_sample_rate=16000, reference_clip_max_seconds=2.0)

    notes = ref_clean.clean_clip(str(src), str(dst), settings=settings)
    out = AudioSegment.from_file(dst, format="wav")
    assert out.channels == 1
    assert out.frame_rate == 16000
    assert isinstance(notes, list)
