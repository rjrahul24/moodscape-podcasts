"""Disk-based audio stitching via the ffmpeg concat demuxer.

The original in-memory pydub path (``stitcher.stitch``) loads the entire episode
into RAM and reallocates on every concatenation — fine for short podcasts, but a
40+ min stereo master is hundreds of MB per copy and risks ``MemoryError``.

Here each chunk is written to its own WAV on disk, then concatenated with
``ffmpeg -f concat`` which streams the inputs and uses constant memory regardless
of episode length. We still use ``stitcher.numpy_to_segment`` to turn provider
output into an ``AudioSegment``, but write it straight to disk instead of holding
the whole episode in memory.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydub import AudioSegment

from .errors import AudioProcessingError


def run_ffmpeg(args: list[str]) -> None:
    """Run ``ffmpeg`` with ``args`` (auto-prefixed), raising on a non-zero exit."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:  # ffmpeg not on PATH
        raise AudioProcessingError("ffmpeg not found on PATH") from exc
    if proc.returncode != 0:
        raise AudioProcessingError(
            f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()[:500]}"
        )


def segment_to_wav_file(
    segment: AudioSegment,
    path: Path,
    *,
    sample_rate: int,
    channels: int = 1,
    edge_fade_ms: int = 0,
) -> Path:
    """Normalize ``segment`` to ``sample_rate``/``channels`` and write a WAV.

    Normalizing every chunk to the same rate + channel count before concat is
    what lets a single master freely mix providers with different native rates
    (local models output at 24 kHz, target is typically 44.1 kHz).

    ``edge_fade_ms`` applies a short fade to each end of the chunk before export.
    The ffmpeg concat demuxer joins chunks with a hard cut; a hard cut across a
    non-zero sample produces an audible click. A few-ms edge fade lands both ends
    on silence so boundaries are clean — the memory-safe stand-in for an
    overlapping crossfade. 0 disables it (legacy behaviour).
    """
    seg = segment.set_frame_rate(int(sample_rate)).set_channels(int(channels))
    if edge_fade_ms > 0:
        fade = min(int(edge_fade_ms), len(seg) // 2)
        if fade > 0:
            seg = seg.fade_in(fade).fade_out(fade)
    seg.export(path, format="wav")
    return path


def normalize_loudness(
    in_wav: Path,
    out_wav: Path,
    *,
    target_lufs: float,
    sample_rate: int,
    true_peak_db: float = -1.5,
) -> Path:
    """Loudness-normalize ``in_wav`` → ``out_wav`` (single-pass EBU R128).

    Used to even out a TTS engine's chunk-to-chunk loudness drift *before* the
    chunks are stitched, so the inter-chunk level is consistent and a later
    master pass (``sleep_post``) only has to set the absolute target. A single
    ``loudnorm`` pass is enough here — the goal is relative consistency across
    chunks, not a precise final number.

    ``loudnorm`` internally upsamples to 192 kHz, so the output is re-pinned to
    ``sample_rate`` (via ``-ar``) to keep every chunk's stream params identical
    for the concat demuxer.
    """
    af = f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11"
    run_ffmpeg(
        [
            "-i", str(in_wav.resolve()),
            "-af", af,
            "-ar", str(int(sample_rate)),
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav


def silence_wav(
    path: Path,
    *,
    duration_ms: int,
    sample_rate: int,
    channels: int = 1,
) -> Path:
    """Write a silent WAV of ``duration_ms`` (used for gaps / inter-sentence pauses)."""
    seg = AudioSegment.silent(duration=max(duration_ms, 0), frame_rate=int(sample_rate))
    return segment_to_wav_file(seg, path, sample_rate=sample_rate, channels=channels)


def build_concat_list(paths: list[Path], list_file: Path) -> Path:
    """Write an ffmpeg concat-demuxer manifest listing ``paths`` in order."""
    lines = []
    for p in paths:
        # ffmpeg concat: single-quote the path and escape embedded quotes.
        safe = str(p.resolve()).replace("'", r"'\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_file


def concat(list_file: Path, out_wav: Path) -> Path:
    """Concatenate the WAVs in ``list_file`` into ``out_wav`` (re-encoded PCM).

    We re-encode rather than ``-c copy`` so mixed inputs are guaranteed to share
    a stream layout; inputs are already normalized by ``segment_to_wav_file``.
    """
    run_ffmpeg(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file.resolve()),
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav


def transcode_mp3(in_wav: Path, out_mp3: Path, *, bitrate: str = "320k") -> Path:
    """Transcode a WAV master to MP3."""
    run_ffmpeg(["-i", str(in_wav.resolve()), "-b:a", bitrate, str(out_mp3.resolve())])
    return out_mp3


def transcode_m4a(in_wav: Path, out_m4a: Path, *, bitrate: str = "256k") -> Path:
    """Transcode a WAV master to M4A (AAC-LC).

    ``-movflags +faststart`` relocates the moov atom so iPhone apps can begin
    playback immediately without buffering the entire file.
    """
    run_ffmpeg([
        "-i", str(in_wav.resolve()),
        "-c:a", "aac",
        "-b:a", bitrate,
        "-movflags", "+faststart",
        str(out_m4a.resolve()),
    ])
    return out_m4a


def transcode(in_path: Path, out_path: Path, *, final_format: str) -> Path:
    """Transcode ``in_path`` to ``out_path`` in ``final_format`` (wav/mp3/m4a/...)."""
    if final_format == "mp3":
        return transcode_mp3(in_path, out_path)
    if final_format == "m4a":
        return transcode_m4a(in_path, out_path)
    run_ffmpeg(["-i", str(in_path.resolve()), str(out_path.resolve())])
    return out_path
