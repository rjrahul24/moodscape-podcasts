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
from app.storage import ambient_registry, files, series_registry

from . import ambient, chunker, ffmpeg_stitch, podcast_music, qc, sleep_post, sleep_text, text_processor
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
_CLONE_PROVIDERS = {"f5", "cosyvoice"}

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
        "cosyvoice": settings.cosyvoice_chunk_chars,
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


def _sleep_voice_settings(
    provider, request: SleepStoryRequest, speed: float, settings: Settings,
    *, prev_text: str = "", next_text: str = "",
) -> dict | None:
    """Sleep-story voice_settings, tailored to the provider's capabilities.

    Instruct-capable models (``accepts_instruct``, i.e. CosyVoice3) get a
    natural-language delivery directive — the calm/hypnotic pace rides this, not
    a numeric rate, so it holds regardless of the cloned clip's energy. The
    directive defaults to ``cosyvoice_sleep_instruct`` and is overridable per
    story via ``style_prompt``. ElevenLabs (``has_native_speed``) gets a calm
    content-type profile + native (per-chunk ramped) speed + optional model
    override, plus cross-chunk continuity context and an optional ``seed``. Plain
    local models (``consumes_local_speed``) get the slow ``speed`` as a rate
    multiplier. Returns ``None`` when nothing applies.

    ``speed`` is the effective per-chunk speed (already ramped by the caller).
    """
    if provider.has_native_speed:
        vs: dict = {"content_type": "sleep", "speed": speed}
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
    if provider.accepts_instruct:
        instruct = request.style_prompt or settings.cosyvoice_sleep_instruct
        return {"instruct": instruct} if instruct else None
    if provider.consumes_local_speed:
        return {"speed": speed}
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
    also_export_mp3: bool,
) -> list[Path]:
    """Move/transcode the concat master into ``out_dir`` as episode.<fmt> (+mp3)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{files.EPISODE_BASENAME}.{final_format}"
    if final_format == "wav":
        master_wav.replace(master_path)
    else:
        ffmpeg_stitch.transcode(master_wav, master_path, final_format=final_format)
    written.append(master_path)

    if also_export_mp3 and final_format != "mp3":
        mp3_path = out_dir / f"{files.EPISODE_BASENAME}.mp3"
        ffmpeg_stitch.transcode_mp3(master_path, mp3_path)
        written.append(mp3_path)

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
            vs = _podcast_voice_settings(provider, op, rng, settings, seed=request.seed)
            fmt = _segment_format_for(op.provider, settings, request_override=req_format)
            seg = provider.synthesize(
                op.text, op.voice_id, output_format=fmt, voice_settings=vs
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
            fmt = _segment_format_for(provider_name, settings, request_override=req_format)
            seg = provider.synthesize(chunk.text, voice_id, output_format=fmt)
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
        also_export_mp3=settings.also_export_mp3,
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
    base_speed = request.speed if request.speed is not None else settings.sleep_default_speed
    base_pause_ms = (
        request.pause_ms if request.pause_ms is not None else settings.sleep_default_pause_ms
    )
    rate = settings.sleep_sample_rate
    provider_name = request.provider
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
    plan = chunker.chunk_prose(prose, provider_name, overrides=overrides)
    total = len(plan)

    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_paths: list[Path] = []
    narration_ms = 0
    gap_counter = 0

    for i, chunk in enumerate(plan):
        # Progressive ramp-down: per-chunk speed/pause ease toward sleep onset.
        speed, pause_ms = _sleep_ramp(
            request, base_speed, base_pause_ms, i, total, settings
        )
        if i > 0 and pause_ms > 0:
            gap_path = work_dir / f"pause_{gap_counter:05d}.wav"
            ffmpeg_stitch.silence_wav(gap_path, duration_ms=pause_ms, sample_rate=rate)
            concat_paths.append(gap_path)
            narration_ms += pause_ms
            gap_counter += 1

        prev_text = _continuity_text(plan[i - 1].text, tail=True) if i > 0 else ""
        next_text = (
            _continuity_text(plan[i + 1].text, tail=False) if i < total - 1 else ""
        )
        voice_settings = _sleep_voice_settings(
            provider, request, speed, settings,
            prev_text=prev_text, next_text=next_text,
        )
        seg = provider.synthesize(
            chunk.text,
            request.voice_id,
            output_format=_segment_format_for(provider_name, settings),
            voice_settings=voice_settings,
        )
        chunk_path = work_dir / f"chunk_{i:05d}.wav"
        ffmpeg_stitch.segment_to_wav_file(
            seg, chunk_path, sample_rate=rate, channels=1,
            edge_fade_ms=settings.chunk_edge_fade_ms,
        )
        concat_paths.append(chunk_path)
        narration_ms += len(seg)
        report(step=f"Synthesizing {i + 1}/{total}", chunks_done=i + 1, chunks_total=total)

    report(step="Stitching", chunks_done=total, chunks_total=total)
    list_file = ffmpeg_stitch.build_concat_list(concat_paths, work_dir / "list.txt")
    narration = ffmpeg_stitch.concat(list_file, work_dir / "narration.wav")

    report(step="Mastering", chunks_done=total, chunks_total=total)
    processed = sleep_post.process(
        narration, work_dir / "processed.wav", settings=settings, total_ms=narration_ms
    )

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
        )
    else:
        final_wav = processed

    written = _finalize(final_wav, out_dir, final_format="wav", also_export_mp3=True)
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
