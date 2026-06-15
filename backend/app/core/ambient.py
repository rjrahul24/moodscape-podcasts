"""Mix an ambient soundscape bed under sleep-story narration (ffmpeg).

The bed is looped/trimmed to the narration length, pulled well below the voice,
faded in and out, and mixed under the narration. Sleep-stories only.
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_stitch import run_ffmpeg


def build_filter_complex(
    *,
    story_ms: int,
    bed_gain_db: float,
    fade_s: float,
    sample_rate: int,
) -> str:
    """Build the ``-filter_complex`` graph mixing bed [1] under narration [0].

    The bed is infinitely looped (``-stream_loop`` on the input), trimmed to the
    story length, gain-reduced and faded, then ``amix``ed with the narration.
    ``duration=first`` keeps the output exactly as long as the narration.
    """
    story_s = story_ms / 1000.0
    fade_out_start = max(story_s - fade_s, 0.0)
    bed_chain = (
        f"[1:a]atrim=0:{story_s:.3f},asetpts=PTS-STARTPTS,"
        f"volume={bed_gain_db}dB,"
        f"afade=t=in:st=0:d={fade_s},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_s},"
        f"aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo[bed]"
    )
    voice_chain = (
        f"[0:a]aformat=sample_rates={int(sample_rate)}:channel_layouts=stereo[voice]"
    )
    mix = "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[out]"
    return ";".join([voice_chain, bed_chain, mix])


def mix(
    narration_wav: Path,
    bed_path: Path,
    out_wav: Path,
    *,
    story_ms: int,
    bed_gain_db: float,
    fade_s: float,
    sample_rate: int,
) -> Path:
    """Mix ``bed_path`` under ``narration_wav`` → ``out_wav``."""
    graph = build_filter_complex(
        story_ms=story_ms,
        bed_gain_db=bed_gain_db,
        fade_s=fade_s,
        sample_rate=sample_rate,
    )
    run_ffmpeg(
        [
            "-i", str(narration_wav.resolve()),
            "-stream_loop", "-1", "-i", str(bed_path.resolve()),
            "-filter_complex", graph,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav
