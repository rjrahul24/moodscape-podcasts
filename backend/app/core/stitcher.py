"""Decode provider audio, concatenate turns, and export the episode.

Uses pydub (backed by ffmpeg). Local models hand us raw numpy samples which
are converted to an ``AudioSegment`` and normalized to a common sample rate
before stitching.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydub import AudioSegment


def numpy_to_segment(samples: np.ndarray, sample_rate: int) -> AudioSegment:
    """Convert float32 mono samples in [-1, 1] to a 16-bit PCM AudioSegment.

    Local models (Kokoro, F5) return numpy waveforms; this is how they enter the
    pydub world.
    """
    arr = np.asarray(samples, dtype=np.float32).squeeze()
    if arr.ndim > 1:
        arr = arr.mean(axis=1)  # mix down to mono
    arr = np.clip(arr, -1.0, 1.0)
    pcm16 = (arr * 32767.0).astype("<i2")
    return AudioSegment(
        data=pcm16.tobytes(),
        sample_width=2,
        frame_rate=int(sample_rate),
        channels=1,
    )


def normalize_segment(segment: AudioSegment, sample_rate: int) -> AudioSegment:
    """Force a segment to mono at ``sample_rate`` so segments can concatenate."""
    return segment.set_frame_rate(int(sample_rate)).set_channels(1)


def stitch(
    segments: list[AudioSegment],
    gap_ms: int,
    *,
    target_sample_rate: int = 44100,
) -> AudioSegment:
    """Concatenate ``segments`` in order with ``gap_ms`` of silence between them.

    Every segment (and the gap) is normalized to ``target_sample_rate`` mono
    first, so providers with different native rates mix cleanly.
    """
    if not segments:
        return AudioSegment.silent(duration=0, frame_rate=target_sample_rate)

    normalized = [normalize_segment(s, target_sample_rate) for s in segments]
    gap = AudioSegment.silent(duration=max(gap_ms, 0), frame_rate=target_sample_rate)

    episode = normalized[0]
    for segment in normalized[1:]:
        episode += gap + segment
    return episode


def export_master(
    episode: AudioSegment,
    out_dir: Path,
    base_name: str,
    *,
    final_format: str = "m4a",
    also_export_wav: bool = True,
) -> list[Path]:
    """Write the episode to ``out_dir`` and return the created file paths.

    Always writes ``<base_name>.<final_format>``; additionally writes a WAV
    when ``also_export_wav`` is set and the master is not already WAV.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{base_name}.{final_format}"
    # pydub/ffmpeg needs "ipod" as the container format for .m4a files;
    # the literal string "m4a" is not a recognised ffmpeg muxer.
    pydub_fmt = "ipod" if final_format == "m4a" else final_format
    episode.export(master_path, format=pydub_fmt)
    written.append(master_path)

    if also_export_wav and final_format != "wav":
        wav_path = out_dir / f"{base_name}.wav"
        episode.export(wav_path, format="wav")
        written.append(wav_path)

    return written
