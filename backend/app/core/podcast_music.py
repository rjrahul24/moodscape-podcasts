"""Mix signature music under podcast intro/outro segments (ffmpeg).

Each function builds an ffmpeg filter graph with a multi-stage volume envelope
on the music track so the music is prominent when solo and pulls back under
speech. Podcasts are mono.

**Intro timeline** (for a 30 s clip, 10 s pre-roll, ~20 s of speech):

    0 s          8 s     10 s                              end
    |-- music ---|--fade--|-- speech over quiet music --|--fade out--|
    full gain     ramp     background gain                 → 0

**Outro timeline** (for ~15 s of speech, 15 s post-roll):

    0 s               speech_end    +crossfade            end
    |-- speech + bg --|---swell-----|-- music solo --|--fade out--|
    bg gain            ramp to full   full gain        → 0
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_stitch import run_ffmpeg


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _intro_volume_expr(
    *,
    fade_start_s: float,
    preroll_s: float,
    total_s: float,
    full_linear: float,
    bg_linear: float,
    crossfade_s: float,
) -> str:
    """Piecewise volume expression for intro music (eval=frame)."""
    fade_out_start = max(total_s - crossfade_s, preroll_s)
    ramp_dur = max(preroll_s - fade_start_s, 0.001)
    fo_dur = max(total_s - fade_out_start, 0.001)
    return (
        f"if(lt(t,{fade_start_s:.3f}),"
        f"{full_linear:.6f},"
        f"if(lt(t,{preroll_s:.3f}),"
        f"{full_linear:.6f}+({bg_linear:.6f}-{full_linear:.6f})"
        f"*(t-{fade_start_s:.3f})/{ramp_dur:.3f},"
        f"if(lt(t,{fade_out_start:.3f}),"
        f"{bg_linear:.6f},"
        f"{bg_linear:.6f}*(1-(t-{fade_out_start:.3f})/{fo_dur:.3f})"
        f")))"
    )


def _outro_volume_expr(
    *,
    speech_s: float,
    total_s: float,
    full_linear: float,
    bg_linear: float,
    crossfade_s: float,
) -> str:
    """Piecewise volume expression for outro music (eval=frame)."""
    fade_in_end = min(crossfade_s, speech_s)
    swell_end = min(speech_s + crossfade_s, total_s)
    fade_out_start = max(total_s - crossfade_s * 1.5, swell_end)
    fo_dur = max(total_s - fade_out_start, 0.001)
    return (
        f"if(lt(t,{fade_in_end:.3f}),"
        f"{bg_linear:.6f}*t/{fade_in_end:.3f},"
        f"if(lt(t,{speech_s:.3f}),"
        f"{bg_linear:.6f},"
        f"if(lt(t,{swell_end:.3f}),"
        f"{bg_linear:.6f}+({full_linear:.6f}-{bg_linear:.6f})"
        f"*(t-{speech_s:.3f})/{max(swell_end - speech_s, 0.001):.3f},"
        f"if(lt(t,{fade_out_start:.3f}),"
        f"{full_linear:.6f},"
        f"{full_linear:.6f}*(1-(t-{fade_out_start:.3f})/{fo_dur:.3f})"
        f"))))"
    )


def build_intro_filter(
    *,
    speech_ms: int,
    preroll_s: float,
    fade_start_s: float,
    full_gain_db: float,
    bg_gain_db: float,
    crossfade_s: float,
    sample_rate: int,
) -> tuple[str, float]:
    """Return ``(filter_complex, total_seconds)`` for the intro mix."""
    speech_s = speech_ms / 1000.0
    total_s = preroll_s + speech_s
    preroll_ms = int(preroll_s * 1000)

    full_lin = _db_to_linear(full_gain_db)
    bg_lin = _db_to_linear(bg_gain_db)
    vol_expr = _intro_volume_expr(
        fade_start_s=fade_start_s,
        preroll_s=preroll_s,
        total_s=total_s,
        full_linear=full_lin,
        bg_linear=bg_lin,
        crossfade_s=crossfade_s,
    )

    voice = (
        f"[0:a]adelay={preroll_ms}|{preroll_ms},"
        f"apad=whole_dur={total_s:.3f},"
        f"aformat=sample_rates={sample_rate}:channel_layouts=mono[voice]"
    )
    music = (
        f"[1:a]atrim=0:{total_s:.3f},asetpts=PTS-STARTPTS,"
        f"volume='{vol_expr}':eval=frame,"
        f"aformat=sample_rates={sample_rate}:channel_layouts=mono[music]"
    )
    mix = "[voice][music]amix=inputs=2:duration=first:dropout_transition=0[out]"
    return ";".join([voice, music, mix]), total_s


def build_outro_filter(
    *,
    speech_ms: int,
    postroll_s: float,
    full_gain_db: float,
    bg_gain_db: float,
    crossfade_s: float,
    sample_rate: int,
) -> tuple[str, float]:
    """Return ``(filter_complex, total_seconds)`` for the outro mix."""
    speech_s = speech_ms / 1000.0
    total_s = speech_s + postroll_s

    full_lin = _db_to_linear(full_gain_db)
    bg_lin = _db_to_linear(bg_gain_db)
    vol_expr = _outro_volume_expr(
        speech_s=speech_s,
        total_s=total_s,
        full_linear=full_lin,
        bg_linear=bg_lin,
        crossfade_s=crossfade_s,
    )

    voice = (
        f"[0:a]apad=whole_dur={total_s:.3f},"
        f"aformat=sample_rates={sample_rate}:channel_layouts=mono[voice]"
    )
    music = (
        f"[1:a]atrim=0:{total_s:.3f},asetpts=PTS-STARTPTS,"
        f"volume='{vol_expr}':eval=frame,"
        f"aformat=sample_rates={sample_rate}:channel_layouts=mono[music]"
    )
    mix = "[voice][music]amix=inputs=2:duration=first:dropout_transition=0[out]"
    return ";".join([voice, music, mix]), total_s


def _run_mix(
    speech_wav: Path, music_path: Path, out_wav: Path, graph: str,
) -> Path:
    run_ffmpeg(
        [
            "-i", str(speech_wav.resolve()),
            "-stream_loop", "-1", "-i", str(music_path.resolve()),
            "-filter_complex", graph,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )
    return out_wav


def mix_intro(
    speech_wav: Path,
    music_path: Path,
    out_wav: Path,
    *,
    speech_ms: int,
    preroll_s: float = 10.0,
    fade_start_s: float = 8.0,
    full_gain_db: float = -12.0,
    bg_gain_db: float = -22.0,
    crossfade_s: float = 2.0,
    sample_rate: int = 44100,
) -> Path:
    """Mix intro music under speech with a pre-roll of music-only."""
    graph, _ = build_intro_filter(
        speech_ms=speech_ms,
        preroll_s=preroll_s,
        fade_start_s=fade_start_s,
        full_gain_db=full_gain_db,
        bg_gain_db=bg_gain_db,
        crossfade_s=crossfade_s,
        sample_rate=sample_rate,
    )
    return _run_mix(speech_wav, music_path, out_wav, graph)


def mix_outro(
    speech_wav: Path,
    music_path: Path,
    out_wav: Path,
    *,
    speech_ms: int,
    postroll_s: float = 15.0,
    full_gain_db: float = -12.0,
    bg_gain_db: float = -22.0,
    crossfade_s: float = 2.0,
    sample_rate: int = 44100,
) -> Path:
    """Mix outro music under speech with a post-roll music-only tail."""
    graph, _ = build_outro_filter(
        speech_ms=speech_ms,
        postroll_s=postroll_s,
        full_gain_db=full_gain_db,
        bg_gain_db=bg_gain_db,
        crossfade_s=crossfade_s,
        sample_rate=sample_rate,
    )
    return _run_mix(speech_wav, music_path, out_wav, graph)
