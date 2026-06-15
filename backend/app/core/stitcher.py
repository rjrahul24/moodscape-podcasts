"""Decode provider audio, concatenate turns, and export the episode.

Uses pydub (backed by ffmpeg). Cloud providers hand us encoded bytes (mp3/wav);
local models hand us raw numpy samples. Both are converted to an
``AudioSegment`` and normalized to a common sample rate before stitching, so a
single episode can freely mix providers with different native rates.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from pydub import AudioSegment


def audio_container(output_format: str) -> str:
    """Map a provider ``output_format`` string to a pydub/ffmpeg container.

    e.g. ``"mp3_44100_128" -> "mp3"``, ``"wav_44100" -> "wav"``.
    """
    codec = output_format.split("_", 1)[0].lower()
    if codec == "opus":
        return "ogg"  # opus is carried in an ogg container
    if codec == "pcm":
        # Raw PCM has no header; we don't request it (see SEGMENT_OUTPUT_FORMAT),
        # but fail loudly rather than silently mis-decode if someone does.
        raise ValueError(
            "Raw 'pcm_*' output is not supported for stitching; use 'wav_*' or "
            "'mp3_*' instead."
        )
    return codec


def bytes_to_segment(data: bytes, output_format: str) -> AudioSegment:
    """Decode encoded audio ``data`` (in ``output_format``) into an AudioSegment."""
    return AudioSegment.from_file(BytesIO(data), format=audio_container(output_format))


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
    final_format: str = "wav",
    also_export_mp3: bool = True,
) -> list[Path]:
    """Write the episode to ``out_dir`` and return the created file paths.

    Always writes ``<base_name>.<final_format>``; additionally writes an MP3
    when ``also_export_mp3`` is set and the master is not already MP3.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{base_name}.{final_format}"
    episode.export(master_path, format=final_format)
    written.append(master_path)

    if also_export_mp3 and final_format != "mp3":
        mp3_path = out_dir / f"{base_name}.mp3"
        episode.export(mp3_path, format="mp3", bitrate="320k")
        written.append(mp3_path)

    return written
