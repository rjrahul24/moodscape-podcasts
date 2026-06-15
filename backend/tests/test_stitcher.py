from io import BytesIO

import numpy as np
import pytest
from pydub import AudioSegment

from app.core.stitcher import (
    audio_container,
    bytes_to_segment,
    export_master,
    numpy_to_segment,
    stitch,
)


def _encode(segment: AudioSegment, fmt: str) -> bytes:
    buffer = BytesIO()
    segment.export(buffer, format=fmt)
    return buffer.getvalue()


def test_audio_container_mapping():
    assert audio_container("mp3_44100_128") == "mp3"
    assert audio_container("wav_44100") == "wav"
    assert audio_container("opus_48000_128") == "ogg"


def test_audio_container_rejects_raw_pcm():
    with pytest.raises(ValueError):
        audio_container("pcm_44100")


def test_bytes_to_segment_roundtrip_wav():
    original = AudioSegment.silent(duration=500)
    decoded = bytes_to_segment(_encode(original, "wav"), "wav_44100")
    assert abs(len(decoded) - 500) < 50


def test_numpy_to_segment_roundtrip_24k():
    # 0.5 s of a quiet sine wave at 24 kHz
    sr = 24000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    seg = numpy_to_segment(samples, sr)
    assert seg.frame_rate == 24000
    assert seg.channels == 1
    assert abs(len(seg) - 500) < 20


def test_stitch_inserts_gaps_between_segments():
    a = AudioSegment.silent(duration=500)
    b = AudioSegment.silent(duration=500)
    episode = stitch([a, b], gap_ms=200)
    # 500 + 200 + 500
    assert abs(len(episode) - 1200) < 50


def test_stitch_normalizes_mixed_sample_rates_to_target():
    # Mix a 24 kHz segment (local model) with a 44.1 kHz one (cloud).
    local = AudioSegment.silent(duration=400, frame_rate=24000)
    cloud = AudioSegment.silent(duration=400, frame_rate=44100)
    episode = stitch([local, cloud], gap_ms=100, target_sample_rate=48000)
    assert episode.frame_rate == 48000
    assert episode.channels == 1
    # 400 + 100 + 400
    assert abs(len(episode) - 900) < 50


def test_stitch_empty_returns_zero_length():
    assert len(stitch([], gap_ms=200)) == 0


def test_export_master_writes_wav_and_mp3(tmp_path):
    episode = AudioSegment.silent(duration=300)
    written = export_master(
        episode, tmp_path, "episode", final_format="wav", also_export_mp3=True
    )
    names = sorted(p.name for p in written)
    assert names == ["episode.mp3", "episode.wav"]
    assert all(p.is_file() and p.stat().st_size > 0 for p in written)
