"""Mix an ambient soundscape bed under sleep-story narration (ffmpeg).

The bed is made "light and slow": looped to the narration length with a
crossfaded seam (no click), band-limited so it sits softly *behind* the voice,
pulled well below it, faded in and out, and — when ducking is on — gently dipped
while the narrator speaks and allowed to breathe back up in the gaps. The whole
thing is disk-based ffmpeg so it composes with the constant-memory stitch.
Sleep-stories only.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from .ffmpeg_stitch import run_ffmpeg


def _probe_duration_s(path: Path) -> float:
    """Return the duration of ``path`` in seconds via ffprobe (0.0 on failure)."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path.resolve()),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return 0.0


def build_looped_bed(
    bed_path: Path,
    out_wav: Path,
    *,
    story_ms: int,
    crossfade_s: float,
    sample_rate: int,
) -> Path:
    """Build a seamlessly-looped copy of ``bed_path`` at least as long as the story.

    The bed is fed as ``n`` inputs that are crossfaded pairwise with
    ``acrossfade`` so each loop seam is a smooth blend rather than a hard cut
    (which clicks). When the bed already covers the story — or is too short to
    crossfade — it is simply copied/looped without the seam treatment.
    """
    story_s = story_ms / 1000.0
    bed_s = _probe_duration_s(bed_path)

    # Bed already covers the story, or we can't measure/crossfade it: fall back to
    # a plain stream-loop (downstream trims to length).
    if bed_s <= 0 or bed_s <= crossfade_s or bed_s >= story_s:
        run_ffmpeg([
            "-stream_loop", "-1", "-i", str(bed_path.resolve()),
            "-t", f"{story_s:.3f}",
            "-c:a", "pcm_s16le", "-ar", str(int(sample_rate)),
            str(out_wav.resolve()),
        ])
        return out_wav

    # Each crossfade overlaps the copies by ``crossfade_s``, so every extra copy
    # advances the timeline by (bed_s - crossfade_s). Add one copy of headroom.
    advance = bed_s - crossfade_s
    n = int(math.ceil((story_s - crossfade_s) / advance)) + 1
    n = max(n, 2)

    inputs: list[str] = []
    for _ in range(n):
        inputs += ["-i", str(bed_path.resolve())]

    # Chain acrossfade: [0][1]->a1, [a1][2]->a2, … then trim to the story length.
    steps: list[str] = []
    prev = "[0:a]"
    for k in range(1, n):
        label = "[out]" if k == n - 1 else f"[a{k}]"
        steps.append(f"{prev}[{k}:a]acrossfade=d={crossfade_s:.3f}:c1=tri:c2=tri{label}")
        prev = label
    graph = ";".join(steps)

    run_ffmpeg([
        *inputs,
        "-filter_complex", graph,
        "-map", "[out]",
        "-t", f"{story_s:.3f}",
        "-c:a", "pcm_s16le", "-ar", str(int(sample_rate)),
        str(out_wav.resolve()),
    ])
    return out_wav


def build_filter_complex(
    *,
    story_ms: int,
    bed_gain_db: float,
    fade_s: float,
    sample_rate: int,
    lowpass_hz: int,
    highpass_hz: int,
    duck: bool,
    duck_ratio: float,
    duck_threshold_db: float,
    duck_release_ms: int,
    bed_target_lufs: float = -24.0,
) -> str:
    """Build the ``-filter_complex`` graph mixing the bed [1] under narration [0].

    The (already loop-extended) bed is trimmed to the story length, loudness-
    normalized to a consistent level (so different ambient files sit at the same
    perceived volume), band-limited (high-pass to clear low mud, low-pass for a
    dark, unobtrusive top), gain-reduced and faded. With ``duck`` on, the voice
    is split off as a sidechain key so the bed compresses (dips) under speech and
    recovers in the gaps. Finally ``amix`` with ``duration=first`` keeps the
    output exactly the narration length.
    """
    story_s = story_ms / 1000.0
    fade_out_start = max(story_s - fade_s, 0.0)
    bed_shape = (
        f"[1:a]atrim=0:{story_s:.3f},asetpts=PTS-STARTPTS,"
        f"loudnorm=I={bed_target_lufs}:TP=-2:LRA=11,"
        f"highpass=f={int(highpass_hz)},lowpass=f={int(lowpass_hz)},"
        f"volume={bed_gain_db}dB,"
        f"afade=t=in:st=0:d={fade_s},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_s},"
        f"aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo"
    )

    if duck:
        # threshold is linear amplitude for sidechaincompress; convert from dB.
        threshold_lin = 10 ** (duck_threshold_db / 20.0)
        release = max(int(duck_release_ms), 1)
        chains = [
            "[0:a]asplit=2[v0][vkey]",
            f"[v0]aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo[voice]",
            f"[vkey]aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo[vk]",
            f"{bed_shape}[bedf]",
            f"[bedf][vk]sidechaincompress=threshold={threshold_lin:.6f}:"
            f"ratio={duck_ratio}:attack=20:release={release}[bed]",
            "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[out]",
        ]
        return ";".join(chains)

    chains = [
        f"[0:a]aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo[voice]",
        f"{bed_shape}[bed]",
        "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[out]",
    ]
    return ";".join(chains)


def mix(
    narration_wav: Path,
    bed_path: Path,
    out_wav: Path,
    *,
    story_ms: int,
    bed_gain_db: float,
    fade_s: float,
    sample_rate: int,
    lowpass_hz: int = 3000,
    highpass_hz: int = 90,
    loop_crossfade_s: float = 2.0,
    duck: bool = True,
    duck_ratio: float = 4.0,
    duck_threshold_db: float = -30.0,
    duck_release_ms: int = 600,
    bed_target_lufs: float = -24.0,
) -> Path:
    """Mix ``bed_path`` softly under ``narration_wav`` → ``out_wav``."""
    looped = build_looped_bed(
        bed_path,
        out_wav.with_name(out_wav.stem + "_bedloop.wav"),
        story_ms=story_ms,
        crossfade_s=loop_crossfade_s,
        sample_rate=sample_rate,
    )
    graph = build_filter_complex(
        story_ms=story_ms,
        bed_gain_db=bed_gain_db,
        fade_s=fade_s,
        sample_rate=sample_rate,
        lowpass_hz=lowpass_hz,
        highpass_hz=highpass_hz,
        duck=duck,
        duck_ratio=duck_ratio,
        duck_threshold_db=duck_threshold_db,
        duck_release_ms=duck_release_ms,
        bed_target_lufs=bed_target_lufs,
    )
    run_ffmpeg(
        [
            "-i", str(narration_wav.resolve()),
            "-i", str(looped.resolve()),
            "-filter_complex", graph,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav
