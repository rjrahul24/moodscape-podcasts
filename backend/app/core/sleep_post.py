"""Sleep-story post-processing (ffmpeg filtergraph).

This is the **sanctioned exception** to Moodscape's "no meditation processing"
rule: it applies ONLY to the sleep-story content type, never to podcasts. The
chain follows the research's sleep-audio spec — narrow dynamic range, gentle
high-frequency roll-off, EBU R128 loudness normalization, and slow fades — to
keep the autonomic nervous system calm.

Implemented as an ffmpeg filtergraph (not pydub) so it composes with the
disk-based stitch/ambient steps and uses constant memory.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings

from .ffmpeg_stitch import run_ffmpeg


def build_filtergraph(
    *,
    total_s: float,
    fade_in_s: float,
    fade_out_s: float,
    lowpass_hz: int,
    target_lufs: float,
    sample_rate: int,
    channels: int,
) -> str:
    """Build the ``-af`` filter string for the sleep master.

    Order: gentle compression to narrow dynamics → low-pass roll-off → EBU R128
    loudness normalization → fade in/out → fix output format (rate + channels).
    """
    fade_out_start = max(total_s - fade_out_s, 0.0)
    filters = [
        # Gentle, slow compressor — tames peaks without pumping.
        "acompressor=threshold=-18dB:ratio=2:attack=20:release=250",
        f"lowpass=f={int(lowpass_hz)}",
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        f"afade=t=in:st=0:d={fade_in_s}",
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_s}",
        f"aformat=sample_rates={int(sample_rate)}:channel_layouts={'stereo' if channels == 2 else 'mono'}",
    ]
    return ",".join(filters)


def process(in_wav: Path, out_wav: Path, *, settings: Settings, total_ms: int) -> Path:
    """Apply the sleep filter chain to ``in_wav`` → ``out_wav`` (stereo master)."""
    af = build_filtergraph(
        total_s=total_ms / 1000.0,
        fade_in_s=settings.sleep_fade_in_s,
        fade_out_s=settings.sleep_fade_out_s,
        lowpass_hz=settings.sleep_lowpass_hz,
        target_lufs=settings.sleep_target_lufs,
        sample_rate=settings.sleep_sample_rate,
        channels=settings.sleep_channels,
    )
    run_ffmpeg(
        [
            "-i", str(in_wav.resolve()),
            "-af", af,
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav
