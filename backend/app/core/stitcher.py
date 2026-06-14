"""Decode provider audio bytes, concatenate turns, and export the episode.

Uses pydub (backed by ffmpeg). Provider output formats are container formats
(mp3 / wav / opus) so they decode directly without needing raw-PCM parameters.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

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


def stitch(segments: list[AudioSegment], gap_ms: int) -> AudioSegment:
    """Concatenate ``segments`` in order with ``gap_ms`` of silence between them."""
    if not segments:
        return AudioSegment.silent(duration=0)

    gap = AudioSegment.silent(duration=max(gap_ms, 0))
    episode = segments[0]
    for segment in segments[1:]:
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
