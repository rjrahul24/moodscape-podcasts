"""The generation engine for both content types.

Replaces the old in-memory ``engine.generate`` body. For every job it:

1. chunks the input so no provider call exceeds its safe input size,
2. synthesizes each chunk and writes it straight to disk (constant memory),
3. concatenates the chunk WAVs with the ffmpeg concat demuxer,
4. (sleep stories only) applies the calming post-process + optional ambient bed,
5. exports a WAV master (+ MP3) and returns metadata.

Progress is reported through a ``ProgressReporter`` callable so this module never
depends on the job store or the API — it can be driven straight from a test.
"""

from __future__ import annotations

import logging
import random
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from app.config import Settings
from app.providers import reference_voice_registry, registry
from app.providers.elevenlabs_provider import V2_MODEL
from app.storage import ambient_registry, files, series_registry

from . import ambient, chunker, f5_text, ffmpeg_stitch, podcast_music, qc, sleep_post, sleep_text, text_processor
from . import emotion as emotion_mod
from .errors import AmbientBedError, SeriesMusicError, VoiceAssignmentError
from .models import (
    GeneratedFile,
    GenerateResult,
    PodcastRequest,
    QCReport,
    SegmentInfo,
    SeriesConfig,
    SleepStoryRequest,
)
from .script_parser import distinct_speakers, parse_script

logger = logging.getLogger("moodscape")


def _wav_duration_ms(wav_path: Path) -> int:
    """Return the duration of a WAV file in milliseconds via ffprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path),
        ],
        capture_output=True, text=True,
    )
    return int(float(result.stdout.strip()) * 1000)


# Providers that clone from a reference clip — the only ones speaker-similarity QC
# can score (it needs the reference timbre to compare against).
_CLONE_PROVIDERS = {"f5"}

# Cross-chunk continuity context: how many trailing/leading characters of an
# adjacent chunk we hand the model as previous_text/next_text. ElevenLabs uses it
# to match pitch/tone across a hard chunk boundary.
_CONTINUITY_CHARS = 200
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")


def _continuity_text(text: str, *, tail: bool) -> str:
    """Trailing (``tail``) or leading slice of ``text`` for continuity context.

    Bracket tags are stripped so a performed cue ([warmly]) never leaks into the
    next chunk's context window and gets double-performed.
    """
    cleaned = re.sub(r"\s{2,}", " ", _BRACKET_TAG_RE.sub("", text)).strip()
    if not cleaned:
        return ""
    return cleaned[-_CONTINUITY_CHARS:] if tail else cleaned[:_CONTINUITY_CHARS]


def _noop(*, step: str, chunks_done: int, chunks_total: int) -> None:
    pass


def _chunk_overrides(settings: Settings) -> dict[str, int]:
    return {
        "kokoro": settings.kokoro_chunk_chars,
        "f5": settings.f5_chunk_chars,
        "elevenlabs": settings.elevenlabs_chunk_chars,
    }


def _segment_format_for(
    provider_name: str, settings: Settings, *, request_override: str | None = None,
) -> str:
    if request_override:
        return request_override
    if provider_name == "elevenlabs" and settings.elevenlabs_segment_format:
        return settings.elevenlabs_segment_format
    return settings.segment_output_format


# ── podcast pacing plan ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Speech:
    """One synthesis op plus the micro-pause that should follow it.

    ``prev_text`` / ``next_text`` are the continuity context drawn from the
    neighbouring speech ops (populated in a post-pass once the full op list is
    known); they are forwarded only to continuity-capable providers.
    """

    text: str
    provider: str
    voice_id: str
    model_id: str | None
    speaker: str
    turn_index: int
    emotion: str | None
    gap_after_ms: int
    section: str = "body"
    prev_text: str = ""
    next_text: str = ""


@dataclass(frozen=True)
class _Silence:
    """A silence op (variable inter-turn gap or explicit author pause).

    ``section`` tracks which script section this silence belongs to, so the
    orchestrator can group rendered files by section for music mixing.
    """

    ms: int
    section: str = "body"


def _draw_turn_gap(rng: random.Random, base_gap_ms: int, jitter: float) -> int:
    """Randomize the inter-turn gap around ``base_gap_ms`` by ±``jitter``."""
    if base_gap_ms <= 0:
        return 0
    lo = max(0, round(base_gap_ms * (1.0 - jitter)))
    hi = round(base_gap_ms * (1.0 + jitter))
    return rng.randint(lo, hi) if hi > lo else lo


def _draw_speed(rng: random.Random, settings: Settings) -> float:
    jitter = settings.podcast_speed_jitter
    return settings.podcast_default_speed * rng.uniform(1.0 - jitter, 1.0 + jitter)


def _podcast_voice_settings(
    provider, op: "_Speech", rng: random.Random, settings: Settings,
    *, seed: int | None,
) -> dict | None:
    """Per-chunk voice_settings, tailored to the provider's declared capabilities.

    Speed-aware local models (``consumes_local_speed``) get a jittered rate
    multiplier. Native-speed cloud providers (``has_native_speed``, i.e.
    ElevenLabs) additionally get a content-type hint + optional model override so
    the provider can pick the right v2/v3 profile, plus cross-chunk continuity
    context and an optional deterministic ``seed`` when the provider advertises
    those. Returns ``None`` when nothing applies so providers fall back to their
    defaults (pre-feature behaviour).
    """
    vs: dict = {}
    if op.emotion:
        vs["emotion"] = op.emotion
    if provider.has_native_speed:
        vs["content_type"] = "podcast"
        if op.model_id:
            vs["model_id"] = op.model_id
        vs["speed"] = settings.podcast_default_speed
    elif provider.consumes_local_speed:
        vs["speed"] = _draw_speed(rng, settings)
    if getattr(provider, "accepts_continuity", False):
        if op.prev_text:
            vs["previous_text"] = op.prev_text
        if op.next_text:
            vs["next_text"] = op.next_text
        if seed is not None:
            vs["seed"] = seed
    return vs or None


_LEADING_TAG_RE = re.compile(r"^\s*\[([A-Za-z_]+)\]\s*")


def _sleep_tone(text: str, settings: Settings) -> tuple[str | None, str]:
    """Resolve ``(emotion, text)`` for a sleep segment.

    A leading author tone tag that names a known emotion (``[calm] …``,
    ``[warm] …``) becomes the segment's emotion and is *removed* from the text, so
    both engines honor it through one canonical path: v3 performs the mapped inline
    tag, v2 maps it to a warmer numeric profile (it can't perform tags). A leading
    non-emotion cue (``[sighs] …``) is left inline for v3 to perform and no default
    is imposed. Otherwise the configured ``sleep_default_tone`` is injected so even
    untagged prose lands in a calm register.
    """
    match = _LEADING_TAG_RE.match(text)
    if match:
        label = match.group(1).lower()
        if label in emotion_mod.EMOTIONS:
            return label, text[match.end():]
        return None, text  # an inline cue like [sighs] — leave it for the model
    return (settings.sleep_default_tone or None), text


def _supports_native_breaks(provider_name: str, model_id: str, settings: Settings) -> bool:
    """True when ``[pause:N]`` should ride as a native ElevenLabs ``<break>`` tag.

    Only ElevenLabs Multilingual v2 honours ``<break>``; v3 and the local engines
    splice real silence instead. Gated by ``elevenlabs_v2_native_breaks``.
    """
    return (
        provider_name == "elevenlabs"
        and model_id == V2_MODEL
        and settings.elevenlabs_v2_native_breaks
    )


def _sleep_voice_settings(
    provider, request: SleepStoryRequest, speed: float, settings: Settings,
    *, prev_text: str = "", next_text: str = "", emotion: str | None = None,
) -> dict | None:
    """Sleep-story voice_settings, tailored to the provider's capabilities.

    ElevenLabs (``has_native_speed``) gets a calm content-type profile + native
    (per-chunk ramped) speed + optional model override, plus cross-chunk
    continuity context and an optional ``seed``. Plain local models
    (``consumes_local_speed``) get the slow ``speed`` as a rate multiplier.
    Returns ``None`` when nothing applies.

    ``speed`` is the effective per-chunk speed (already ramped by the caller).
    """
    if provider.has_native_speed:
        vs: dict = {"content_type": "sleep", "speed": speed}
        if emotion:
            vs["emotion"] = emotion
        if request.model_id:
            vs["model_id"] = request.model_id
        if getattr(provider, "accepts_continuity", False):
            if prev_text:
                vs["previous_text"] = prev_text
            if next_text:
                vs["next_text"] = next_text
            if request.seed is not None:
                vs["seed"] = request.seed
        return vs
    if provider.consumes_local_speed:
        vs_local: dict = {"speed": speed}
        if provider.name == "f5":
            vs_local["nfe_step"] = settings.f5_sleep_nfe_step
            vs_local["content_type"] = "sleep"
        return vs_local
    return None


def _lerp(start: float, end: float, frac: float) -> float:
    return start + (end - start) * frac


def _sleep_ramp(
    request: SleepStoryRequest, base_speed: float, base_pause_ms: int,
    index: int, total: int, settings: Settings,
) -> tuple[float, int]:
    """Effective (speed, pause_ms) for chunk ``index`` of a sleep story.

    With ``ramp`` on (default), speed eases from the baseline toward
    ``baseline * sleep_ramp_speed_end_factor`` and the inter-sentence pause grows
    toward ``base_pause_ms * sleep_ramp_pause_scale`` — both linearly over the
    story so the narration gently decelerates toward sleep onset. Pure function of
    ``index`` (deterministic, no RNG). With ``ramp`` off, returns the fixed values.
    """
    if not request.ramp or total <= 1:
        return base_speed, base_pause_ms
    frac = index / (total - 1)
    speed = base_speed * _lerp(1.0, settings.sleep_ramp_speed_end_factor, frac)
    pause = round(base_pause_ms * _lerp(1.0, settings.sleep_ramp_pause_scale, frac))
    return speed, pause


def _build_podcast_ops(
    turns,
    speakers: dict,
    settings: Settings,
    gap_ms: int,
    overrides: dict[str, int],
    rng: random.Random,
) -> list:
    """Flatten parsed turns into an ordered list of ``_Speech``/``_Silence`` ops."""
    ops: list = []
    prev_turn_index: int | None = None
    for turn in turns:
        assignment = speakers[turn.speaker]
        section = getattr(turn, "section", "body")
        if prev_turn_index is not None:
            gap = _draw_turn_gap(rng, gap_ms, settings.podcast_turn_gap_jitter)
            if gap > 0:
                ops.append(_Silence(gap, section=section))
        max_chars = chunker.budget_for(assignment.provider, overrides=overrides)
        items = text_processor.plan_turn(
            turn.text,
            provider=assignment.provider,
            max_chars=max_chars,
            rng=rng,
            gap_min_ms=settings.podcast_intra_sentence_gap_ms_min,
            gap_max_ms=settings.podcast_intra_sentence_gap_ms_max,
            inline_sfx=registry.get(assignment.provider).accepts_inline_sfx,
        )
        for item in items:
            if isinstance(item, text_processor.Pause):
                if item.ms > 0:
                    ops.append(_Silence(item.ms, section=section))
            else:
                ops.append(
                    _Speech(
                        text=item.text,
                        provider=assignment.provider,
                        voice_id=assignment.voice_id,
                        model_id=assignment.model_id,
                        speaker=turn.speaker,
                        turn_index=turn.index,
                        emotion=item.emotion,
                        gap_after_ms=item.gap_after_ms,
                        section=section,
                    )
                )
        prev_turn_index = turn.index
    return _link_continuity(ops)


def _link_continuity(ops: list) -> list:
    """Populate each ``_Speech``'s prev/next continuity context from its neighbours.

    Context flows across the whole rendered sequence (including speaker changes),
    matching how the research stitches turns; intervening ``_Silence`` ops are
    skipped. Bracket tags are stripped by ``_continuity_text``.
    """
    speech_idx = [i for i, op in enumerate(ops) if isinstance(op, _Speech)]
    for pos, i in enumerate(speech_idx):
        prev_text = ""
        next_text = ""
        if pos > 0:
            prev_text = _continuity_text(ops[speech_idx[pos - 1]].text, tail=True)
        if pos < len(speech_idx) - 1:
            next_text = _continuity_text(ops[speech_idx[pos + 1]].text, tail=False)
        ops[i] = replace(ops[i], prev_text=prev_text, next_text=next_text)
    return ops


def _generated_files(written: list[Path], job_id: str) -> list[GeneratedFile]:
    return [
        GeneratedFile(
            filename=path.name,
            format=path.suffix.lstrip("."),
            download_url=f"/api/download/{job_id}/{path.name}",
            size_bytes=path.stat().st_size,
        )
        for path in written
    ]


def _finalize(
    master_wav: Path,
    out_dir: Path,
    *,
    final_format: str,
    also_export_wav: bool,
) -> list[Path]:
    """Move/transcode the concat master into ``out_dir`` as episode.<fmt> (+wav)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{files.EPISODE_BASENAME}.{final_format}"
    if final_format == "wav":
        master_wav.replace(master_path)
    else:
        ffmpeg_stitch.transcode(master_wav, master_path, final_format=final_format)
    written.append(master_path)

    if also_export_wav and final_format != "wav":
        wav_path = out_dir / f"{files.EPISODE_BASENAME}.wav"
        master_wav.replace(wav_path)
        written.append(wav_path)

    return written


def run(
    request: PodcastRequest | SleepStoryRequest,
    settings: Settings,
    reporter=None,
    *,
    job_id: str | None = None,
) -> GenerateResult:
    """Render ``request`` to disk and return its metadata. Dispatches on kind."""
    report = reporter or _noop
    job_id = job_id or files.new_job_id()
    if isinstance(request, SleepStoryRequest):
        result = _run_sleep(request, settings, report, job_id)
    else:
        result = _run_podcast(request, settings, report, job_id)

    if settings.enable_qc:
        _attach_qc(result, request, settings, report, job_id)
    return result


# ── quality control (opt-in, non-fatal) ────────────────────────────────────────
def _clone_reference(provider: str, voice_id: str, settings: Settings) -> str | None:
    """Path to the reference clip for a cloned voice, or None if not applicable."""
    if provider not in _CLONE_PROVIDERS:
        return None
    entry = reference_voice_registry.scan(settings.assets_dir).get(voice_id)
    return str(entry["audio"]) if entry else None


def _qc_inputs(
    request: PodcastRequest | SleepStoryRequest, settings: Settings
) -> tuple[str, str | None]:
    """Return (source_text, reference_clip) for QC.

    The reference clip is supplied only when exactly one cloned voice is in play
    (sleep stories are single-voice; a podcast with one distinct cloned voice
    qualifies) — that's the only case speaker-similarity can score.
    """
    if isinstance(request, SleepStoryRequest):
        return request.prose_text, _clone_reference(
            request.provider, request.voice_id, settings
        )
    source = " ".join(t.text for t in parse_script(request.script_text))
    cloned = {
        (sv.provider, sv.voice_id)
        for sv in request.speakers.values()
        if sv.provider in _CLONE_PROVIDERS
    }
    ref = None
    if len(cloned) == 1:
        provider, voice_id = next(iter(cloned))
        ref = _clone_reference(provider, voice_id, settings)
    return source, ref


def _master_path(result: GenerateResult, settings: Settings, job_id: str) -> Path | None:
    """Resolve the rendered master on disk — prefer a WAV, else the first file."""
    out_dir = files.job_dir(settings.output_dir, job_id)
    wavs = [f for f in result.files if f.format == "wav"]
    chosen = (wavs or result.files or [None])[0]
    return out_dir / chosen.filename if chosen else None


def _attach_qc(
    result: GenerateResult,
    request: PodcastRequest | SleepStoryRequest,
    settings: Settings,
    report,
    job_id: str,
) -> None:
    """Run QC on the finished master and attach the report. Never fatal."""
    try:
        master = _master_path(result, settings, job_id)
        if master is None or not master.is_file():
            return
        source, reference = _qc_inputs(request, settings)
        report(step="Quality check", chunks_done=0, chunks_total=0)
        result.qc = qc.run_qc(
            str(master),
            source_text=source,
            settings=settings,
            reference_audio=reference,
        )
    except Exception as exc:  # noqa: BLE001 - QC must never fail a good render
        logger.warning("QC step failed: %s", exc)
        result.qc = QCReport(notes=[f"QC failed: {exc}"])


# ── podcast ──────────────────────────────────────────────────────────────────

def _load_series(
    request: PodcastRequest, settings: Settings,
) -> SeriesConfig | None:
    """Load and validate the series config if ``request.series`` is set."""
    if not request.series:
        return None
    config = series_registry.get(request.series, settings.series_dir)
    for attr in ("intro_music", "outro_music"):
        music_file = settings.podcast_music_dir / getattr(config, attr)
        if not music_file.is_file():
            raise SeriesMusicError(
                f"Music file {getattr(config, attr)!r} not found "
                f"in {settings.podcast_music_dir}."
            )
    return config


def _stitch_section(
    paths: list[Path], work_dir: Path, name: str,
) -> Path:
    """Stitch a list of chunk WAVs into a single section WAV."""
    list_file = ffmpeg_stitch.build_concat_list(paths, work_dir / f"{name}_list.txt")
    return ffmpeg_stitch.concat(list_file, work_dir / f"{name}.wav")


def _stitch_with_music(
    tagged_paths: list[tuple[Path, str]],
    work_dir: Path,
    settings: Settings,
    series_config: SeriesConfig | None,
    report,
    total: int,
    silence_ms_by_section: dict[str, int],
) -> tuple[Path, int]:
    """Stitch rendered chunks, mixing music under intro/outro if a series is set.

    Returns ``(master_wav, total_silence_ms)``.
    """
    has_sections = series_config is not None and any(
        s != "body" for _, s in tagged_paths
    )

    if not has_sections:
        # No series or no section markers — flat stitch (original behaviour).
        report(step="Stitching", chunks_done=total, chunks_total=total)
        paths = [p for p, _ in tagged_paths]
        list_file = ffmpeg_stitch.build_concat_list(paths, work_dir / "list.txt")
        master = ffmpeg_stitch.concat(list_file, work_dir / "master.wav")
        return master, sum(silence_ms_by_section.values())

    # Group paths by section, preserving order.
    sections: dict[str, list[Path]] = {}
    for path, section in tagged_paths:
        sections.setdefault(section, []).append(path)

    section_wavs: list[Path] = []
    total_silence = 0
    rate = settings.target_sample_rate

    for section_name in ("intro", "body", "outro"):
        paths = sections.get(section_name)
        if not paths:
            continue
        report(step=f"Stitching {section_name}", chunks_done=total, chunks_total=total)
        section_wav = _stitch_section(paths, work_dir, section_name)
        total_silence += silence_ms_by_section.get(section_name, 0)

        if section_name == "intro" and series_config is not None:
            music_path = settings.podcast_music_dir / series_config.intro_music
            report(step="Mixing intro music", chunks_done=total, chunks_total=total)
            speech_ms = _wav_duration_ms(section_wav)
            mixed = podcast_music.mix_intro(
                section_wav,
                music_path,
                work_dir / "intro_mixed.wav",
                speech_ms=speech_ms,
                preroll_s=series_config.intro_preroll_s,
                fade_start_s=series_config.intro_fade_start_s,
                full_gain_db=series_config.music_full_gain_db,
                bg_gain_db=series_config.music_bg_gain_db,
                crossfade_s=series_config.music_crossfade_s,
                sample_rate=rate,
            )
            section_wavs.append(mixed)
        elif section_name == "outro" and series_config is not None:
            music_path = settings.podcast_music_dir / series_config.outro_music
            report(step="Mixing outro music", chunks_done=total, chunks_total=total)
            speech_ms = _wav_duration_ms(section_wav)
            mixed = podcast_music.mix_outro(
                section_wav,
                music_path,
                work_dir / "outro_mixed.wav",
                speech_ms=speech_ms,
                postroll_s=series_config.outro_postroll_s,
                full_gain_db=series_config.music_full_gain_db,
                bg_gain_db=series_config.music_bg_gain_db,
                crossfade_s=series_config.music_crossfade_s,
                sample_rate=rate,
            )
            section_wavs.append(mixed)
        else:
            section_wavs.append(section_wav)

    if len(section_wavs) == 1:
        return section_wavs[0], total_silence

    report(step="Stitching final", chunks_done=total, chunks_total=total)
    final_list = ffmpeg_stitch.build_concat_list(
        section_wavs, work_dir / "final_list.txt"
    )
    master = ffmpeg_stitch.concat(final_list, work_dir / "master.wav")
    return master, total_silence


def _run_podcast(
    request: PodcastRequest, settings: Settings, report, job_id: str
) -> GenerateResult:
    turns = parse_script(request.script_text)

    missing = [s for s in distinct_speakers(turns) if s not in request.speakers]
    if missing:
        raise VoiceAssignmentError("No voice assigned for: " + ", ".join(missing) + ".")

    series_config = _load_series(request, settings)

    req_format = request.output_format
    gap_ms = request.gap_ms if request.gap_ms is not None else settings.inter_turn_gap_ms
    rate = settings.target_sample_rate
    overrides = _chunk_overrides(settings)

    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Each entry is (path, section) so the stitcher can group by section.
    tagged_paths: list[tuple[Path, str]] = []
    turn_durations: dict[int, int] = {}
    turn_meta: dict[int, tuple[str, str, str]] = {}
    silence_ms_by_section: dict[str, int] = {}
    chunk_counter = 0
    gap_counter = 0

    if request.pacing:
        rng = random.Random(job_id)
        ops = _build_podcast_ops(turns, request.speakers, settings, gap_ms, overrides, rng)
        total = sum(1 for op in ops if isinstance(op, _Speech))
        done = 0
        for op in ops:
            if isinstance(op, _Silence):
                gap_path = work_dir / f"gap_{gap_counter:05d}.wav"
                ffmpeg_stitch.silence_wav(gap_path, duration_ms=op.ms, sample_rate=rate)
                tagged_paths.append((gap_path, op.section))
                silence_ms_by_section[op.section] = (
                    silence_ms_by_section.get(op.section, 0) + op.ms
                )
                gap_counter += 1
                continue

            if not op.text.strip():
                logger.warning("Skipping empty speech op (turn %d)", op.turn_index)
                done += 1
                continue

            provider = registry.get(op.provider)
            synth_text = op.text
            if op.provider == "f5":
                synth_text = f5_text.normalize_for_f5(synth_text)
            vs = _podcast_voice_settings(provider, op, rng, settings, seed=request.seed)
            fmt = _segment_format_for(op.provider, settings, request_override=req_format)
            seg = provider.synthesize(
                synth_text, op.voice_id, output_format=fmt, voice_settings=vs
            )
            chunk_path = work_dir / f"chunk_{chunk_counter:05d}.wav"
            ffmpeg_stitch.segment_to_wav_file(
                seg, chunk_path, sample_rate=rate, channels=1,
                edge_fade_ms=settings.chunk_edge_fade_ms,
            )
            tagged_paths.append((chunk_path, op.section))
            chunk_counter += 1

            turn_durations[op.turn_index] = turn_durations.get(op.turn_index, 0) + len(seg)
            turn_meta[op.turn_index] = (op.speaker, op.voice_id, op.provider)

            done += 1
            report(step=f"Synthesizing {done}/{total}", chunks_done=done, chunks_total=total)

            if op.gap_after_ms > 0:
                gap_path = work_dir / f"gap_{gap_counter:05d}.wav"
                ffmpeg_stitch.silence_wav(
                    gap_path, duration_ms=op.gap_after_ms, sample_rate=rate
                )
                tagged_paths.append((gap_path, op.section))
                silence_ms_by_section[op.section] = (
                    silence_ms_by_section.get(op.section, 0) + op.gap_after_ms
                )
                gap_counter += 1
    else:
        plan: list[tuple[chunker.TextChunk, str, str]] = []
        idx = 0
        for turn in turns:
            assignment = request.speakers[turn.speaker]
            for chunk in chunker.chunk_turn(
                turn, assignment.provider, start_index=idx, overrides=overrides
            ):
                plan.append((chunk, assignment.provider, assignment.voice_id))
                idx += 1

        total = len(plan)
        prev_turn_index: int | None = None
        for i, (chunk, provider_name, voice_id) in enumerate(plan):
            if prev_turn_index is not None and chunk.turn_index != prev_turn_index and gap_ms > 0:
                gap_path = work_dir / f"gap_{gap_counter:05d}.wav"
                ffmpeg_stitch.silence_wav(gap_path, duration_ms=gap_ms, sample_rate=rate)
                tagged_paths.append((gap_path, "body"))
                silence_ms_by_section["body"] = (
                    silence_ms_by_section.get("body", 0) + gap_ms
                )
                gap_counter += 1

            provider = registry.get(provider_name)
            synth_text = chunk.text
            if provider_name == "f5":
                synth_text = f5_text.normalize_for_f5(synth_text)
            fmt = _segment_format_for(provider_name, settings, request_override=req_format)
            seg = provider.synthesize(synth_text, voice_id, output_format=fmt)
            chunk_path = work_dir / f"chunk_{i:05d}.wav"
            ffmpeg_stitch.segment_to_wav_file(
                seg, chunk_path, sample_rate=rate, channels=1,
                edge_fade_ms=settings.chunk_edge_fade_ms,
            )
            tagged_paths.append((chunk_path, "body"))

            turn_durations[chunk.turn_index] = turn_durations.get(chunk.turn_index, 0) + len(seg)
            turn_meta[chunk.turn_index] = (chunk.speaker, voice_id, provider_name)
            prev_turn_index = chunk.turn_index

            report(step=f"Synthesizing {i + 1}/{total}", chunks_done=i + 1, chunks_total=total)

    master, total_silence = _stitch_with_music(
        tagged_paths, work_dir, settings, series_config, report, total,
        silence_ms_by_section,
    )

    written = _finalize(
        master,
        out_dir,
        final_format=settings.final_format,
        also_export_wav=settings.also_export_wav,
    )
    shutil.rmtree(work_dir, ignore_errors=True)

    segment_infos = [
        SegmentInfo(
            index=ti,
            speaker=turn_meta[ti][0],
            voice_id=turn_meta[ti][1],
            provider=turn_meta[ti][2],
            duration_ms=turn_durations[ti],
        )
        for ti in sorted(turn_durations)
    ]
    duration_ms = sum(turn_durations.values()) + total_silence

    return GenerateResult(
        job_id=job_id,
        duration_ms=duration_ms,
        segments=segment_infos,
        files=_generated_files(written, job_id),
    )


# ── sleep story ──────────────────────────────────────────────────────────────
def _run_sleep(
    request: SleepStoryRequest, settings: Settings, report, job_id: str
) -> GenerateResult:
    provider_name = request.provider
    base_speed = request.speed if request.speed is not None else settings.sleep_default_speed
    if provider_name == "f5" and request.speed is None:
        base_speed = settings.f5_sleep_speed
    base_pause_ms = (
        request.pause_ms if request.pause_ms is not None else settings.sleep_default_pause_ms
    )
    rate = settings.sleep_sample_rate
    overrides = _chunk_overrides(settings)

    provider = registry.get(provider_name)

    # Validate the ambient bed up front so we fail fast (before synthesis).
    bed_path: Path | None = None
    if request.ambient_bed:
        beds = ambient_registry.scan(settings.ambient_dir)
        bed_path = beds.get(request.ambient_bed)
        if bed_path is None:
            raise AmbientBedError(
                f"Ambient bed {request.ambient_bed!r} not found in {settings.ambient_dir}."
            )

    # Spell out standalone numbers so the narrator never reads bare digits in a
    # clipped, transactional tone (the provider's apply_text_normalization handles
    # the rest server-side).
    prose = sleep_text.spell_numbers(request.prose_text)
    # Soft breathing pause at each sentence break (ElevenLabs honours "…" on both
    # v2 and v3). Opt-in; applied before chunking so it rides into every chunk.
    if provider_name == "elevenlabs" and settings.sleep_sentence_ellipsis:
        prose = sleep_text.inject_sentence_pauses(prose)
    if provider_name == "kokoro":
        prose = sleep_text.punctuation_to_pauses(
            prose,
            comma_ms=settings.kokoro_pause_comma_ms,
            ellipsis_ms=settings.kokoro_pause_ellipsis_ms,
            semicolon_ms=settings.kokoro_pause_semicolon_ms,
            dash_ms=settings.kokoro_pause_dash_ms,
            paragraph_ms=settings.kokoro_pause_paragraph_ms,
        )
    if provider_name == "f5":
        prose = f5_text.normalize_for_f5(prose)
    plan = chunker.chunk_prose(prose, provider_name, overrides=overrides)
    total = len(plan)

    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Engine resolution: only ElevenLabs v2 renders [pause:N] as a native <break>;
    # every other engine splits the chunk here and splices real silence.
    el_model = request.model_id or settings.elevenlabs_sleep_model
    native_breaks = _supports_native_breaks(provider_name, el_model, settings)

    concat_paths: list[Path] = []
    narration_ms = 0
    gap_counter = 0
    seg_counter = 0

    def _splice_silence(duration_ms: int) -> None:
        nonlocal narration_ms, gap_counter
        if duration_ms <= 0:
            return
        gap_path = work_dir / f"pause_{gap_counter:05d}.wav"
        ffmpeg_stitch.silence_wav(gap_path, duration_ms=duration_ms, sample_rate=rate)
        concat_paths.append(gap_path)
        narration_ms += duration_ms
        gap_counter += 1

    for i, chunk in enumerate(plan):
        # Progressive ramp-down: per-chunk speed/pause ease toward sleep onset.
        speed, pause_ms = _sleep_ramp(
            request, base_speed, base_pause_ms, i, total, settings
        )
        if i > 0:
            _splice_silence(pause_ms)  # inter-sentence pause between chunks

        prev_text = _continuity_text(plan[i - 1].text, tail=True) if i > 0 else ""
        next_text = (
            _continuity_text(plan[i + 1].text, tail=False) if i < total - 1 else ""
        )

        # Author-placed [pause:N] breaths. v2 keeps the marker inline (translated to
        # a native <break> by the provider); other engines split into sub-segments
        # separated by spliced silence so the breath is honored everywhere.
        if native_breaks:
            pieces = [(chunk.text, 0)]
        else:
            pieces = sleep_text.split_pauses(
                chunk.text,
                max_ms=settings.sleep_pause_marker_max_ms,
                default_ms=settings.sleep_pause_default_ms,
            )

        for j, (piece_text, pause_after_ms) in enumerate(pieces):
            tone, piece_text = _sleep_tone(piece_text, settings)
            if piece_text.strip():
                voice_settings = _sleep_voice_settings(
                    provider, request, speed, settings,
                    prev_text=prev_text if j == 0 else "",
                    next_text=next_text if j == len(pieces) - 1 else "",
                    emotion=tone,
                )
                seg = provider.synthesize(
                    piece_text,
                    request.voice_id,
                    output_format=_segment_format_for(provider_name, settings),
                    voice_settings=voice_settings,
                )
                chunk_path = work_dir / f"chunk_{seg_counter:05d}.wav"
                ffmpeg_stitch.segment_to_wav_file(
                    seg, chunk_path, sample_rate=rate, channels=1,
                    edge_fade_ms=settings.chunk_edge_fade_ms,
                )
                # Even out the engine's chunk-to-chunk loudness drift before the
                # stitch (the final master only sets the absolute level). Skip
                # very short chunks so near-silent fragments aren't amplified.
                if (
                    settings.sleep_chunk_normalize
                    and len(seg) >= settings.sleep_chunk_norm_min_ms
                ):
                    norm_path = work_dir / f"chunk_{seg_counter:05d}.norm.wav"
                    ffmpeg_stitch.normalize_loudness(
                        chunk_path, norm_path,
                        target_lufs=settings.sleep_chunk_norm_lufs,
                        sample_rate=rate,
                    )
                    concat_paths.append(norm_path)
                else:
                    concat_paths.append(chunk_path)
                narration_ms += len(seg)
                seg_counter += 1
            _splice_silence(pause_after_ms)  # the author's deliberate breath

        report(step=f"Synthesizing {i + 1}/{total}", chunks_done=i + 1, chunks_total=total)

    report(step="Stitching", chunks_done=total, chunks_total=total)
    list_file = ffmpeg_stitch.build_concat_list(concat_paths, work_dir / "list.txt")
    narration = ffmpeg_stitch.concat(list_file, work_dir / "narration.wav")

    report(step="Mastering", chunks_done=total, chunks_total=total)
    processed = sleep_post.process(
        narration, work_dir / "processed.wav", settings=settings, total_ms=narration_ms
    )

    # Prepend a silent pre-roll so the ambient bed plays alone before the
    # narration starts — gives listeners a gentle entry instead of an abrupt
    # first word. Only when an ambient bed is selected.
    if bed_path is not None and settings.sleep_preroll_s > 0:
        preroll_ms = int(settings.sleep_preroll_s * 1000)
        preroll_path = work_dir / "preroll.wav"
        ffmpeg_stitch.silence_wav(
            preroll_path, duration_ms=preroll_ms,
            sample_rate=rate, channels=settings.sleep_channels,
        )
        preroll_list = ffmpeg_stitch.build_concat_list(
            [preroll_path, processed], work_dir / "preroll_list.txt",
        )
        processed = ffmpeg_stitch.concat(preroll_list, work_dir / "with_preroll.wav")
        narration_ms += preroll_ms

    if bed_path is not None:
        report(step="Mixing ambient bed", chunks_done=total, chunks_total=total)
        final_wav = ambient.mix(
            processed,
            bed_path,
            work_dir / "final.wav",
            story_ms=narration_ms,
            bed_gain_db=settings.ambient_bed_gain_db,
            fade_s=settings.sleep_fade_out_s,
            sample_rate=rate,
            lowpass_hz=settings.ambient_bed_lowpass_hz,
            highpass_hz=settings.ambient_bed_highpass_hz,
            loop_crossfade_s=settings.ambient_loop_crossfade_s,
            duck=settings.ambient_duck,
            duck_ratio=settings.ambient_duck_ratio,
            duck_threshold_db=settings.ambient_duck_threshold_db,
            duck_release_ms=settings.ambient_duck_release_ms,
            bed_target_lufs=settings.ambient_bed_target_lufs,
        )
    else:
        final_wav = processed

    written = _finalize(final_wav, out_dir, final_format=settings.final_format, also_export_wav=settings.also_export_wav)
    shutil.rmtree(work_dir, ignore_errors=True)

    segment_infos = [
        SegmentInfo(
            index=0,
            speaker="narrator",
            voice_id=request.voice_id,
            provider=provider_name,
            duration_ms=narration_ms,
        )
    ]

    return GenerateResult(
        job_id=job_id,
        duration_ms=narration_ms,
        segments=segment_infos,
        files=_generated_files(written, job_id),
    )
