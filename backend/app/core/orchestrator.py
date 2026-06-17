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

import random
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.providers import registry
from app.storage import ambient_registry, files

from . import ambient, chunker, ffmpeg_stitch, sleep_post, text_processor
from .errors import AmbientBedError, VoiceAssignmentError
from .models import (
    GeneratedFile,
    GenerateResult,
    PodcastRequest,
    SegmentInfo,
    SleepStoryRequest,
)
from .script_parser import distinct_speakers, parse_script


def _noop(*, step: str, chunks_done: int, chunks_total: int) -> None:
    pass


def _chunk_overrides(settings: Settings) -> dict[str, int]:
    return {
        "kokoro": settings.kokoro_chunk_chars,
        "f5": settings.f5_chunk_chars,
        "elevenlabs": settings.elevenlabs_chunk_chars,
    }


# ── podcast pacing plan ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Speech:
    """One synthesis op plus the micro-pause that should follow it."""

    text: str
    provider: str
    voice_id: str
    model_id: str | None
    speaker: str
    turn_index: int
    emotion: str | None
    gap_after_ms: int


@dataclass(frozen=True)
class _Silence:
    """A silence op (variable inter-turn gap or explicit author pause)."""

    ms: int


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
    provider, emotion: str | None, model_id: str | None,
    rng: random.Random, settings: Settings,
) -> dict | None:
    """Per-chunk voice_settings, tailored to the provider's declared capabilities.

    Speed-aware local models (``consumes_local_speed``) get a jittered rate
    multiplier. Native-speed cloud providers (``has_native_speed``, i.e.
    ElevenLabs) additionally get a content-type hint + optional model override so
    the provider can pick the right v2/v3 profile. Returns ``None`` when nothing
    applies so providers fall back to their defaults (pre-feature behaviour).
    """
    vs: dict = {}
    if emotion:
        vs["emotion"] = emotion
    if provider.has_native_speed:
        vs["content_type"] = "podcast"
        if model_id:
            vs["model_id"] = model_id
        vs["speed"] = _draw_speed(rng, settings)
    elif provider.consumes_local_speed:
        vs["speed"] = _draw_speed(rng, settings)
    return vs or None


def _sleep_voice_settings(provider, request: SleepStoryRequest, speed: float) -> dict | None:
    """Sleep-story voice_settings, tailored to the provider's capabilities.

    Local models get the slow ``speed`` as a rate multiplier. ElevenLabs
    (``has_native_speed``) gets a calm content-type profile + native slow speed
    + optional model override, so the *voice itself* narrates gently before the
    sleep mastering chain runs. Returns ``None`` when nothing applies.
    """
    if provider.has_native_speed:
        vs: dict = {"content_type": "sleep", "speed": speed}
        if request.model_id:
            vs["model_id"] = request.model_id
        return vs
    if provider.consumes_local_speed:
        return {"speed": speed}
    return None


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
        if prev_turn_index is not None:
            gap = _draw_turn_gap(rng, gap_ms, settings.podcast_turn_gap_jitter)
            if gap > 0:
                ops.append(_Silence(gap))
        max_chars = chunker.budget_for(assignment.provider, overrides=overrides)
        items = text_processor.plan_turn(
            turn.text,
            provider=assignment.provider,
            max_chars=max_chars,
            rng=rng,
            gap_min_ms=settings.podcast_intra_sentence_gap_ms_min,
            gap_max_ms=settings.podcast_intra_sentence_gap_ms_max,
        )
        for item in items:
            if isinstance(item, text_processor.Pause):
                if item.ms > 0:
                    ops.append(_Silence(item.ms))
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
                    )
                )
        prev_turn_index = turn.index
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
        return _run_sleep(request, settings, report, job_id)
    return _run_podcast(request, settings, report, job_id)


# ── podcast ──────────────────────────────────────────────────────────────────
def _run_podcast(
    request: PodcastRequest, settings: Settings, report, job_id: str
) -> GenerateResult:
    turns = parse_script(request.script_text)

    missing = [s for s in distinct_speakers(turns) if s not in request.speakers]
    if missing:
        raise VoiceAssignmentError("No voice assigned for: " + ", ".join(missing) + ".")

    output_format = request.output_format or settings.segment_output_format
    gap_ms = request.gap_ms if request.gap_ms is not None else settings.inter_turn_gap_ms
    rate = settings.target_sample_rate
    overrides = _chunk_overrides(settings)

    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_paths: list[Path] = []
    # Aggregate render time per turn for SegmentInfo.
    turn_durations: dict[int, int] = {}
    turn_meta: dict[int, tuple[str, str, str]] = {}  # turn_index -> (speaker, voice, provider)
    silence_ms = 0
    chunk_counter = 0
    gap_counter = 0

    if request.pacing:
        # Conversational render: sentence micro-pauses, variable turn gaps,
        # per-chunk speed jitter, and inline tone/pause tags. Seed the RNG from
        # the job id so pacing is deterministic and reproducible.
        rng = random.Random(job_id)
        ops = _build_podcast_ops(turns, request.speakers, settings, gap_ms, overrides, rng)
        total = sum(1 for op in ops if isinstance(op, _Speech))
        done = 0
        for op in ops:
            if isinstance(op, _Silence):
                gap_path = work_dir / f"gap_{gap_counter:05d}.wav"
                ffmpeg_stitch.silence_wav(gap_path, duration_ms=op.ms, sample_rate=rate)
                concat_paths.append(gap_path)
                silence_ms += op.ms
                gap_counter += 1
                continue

            provider = registry.get(op.provider)
            vs = _podcast_voice_settings(provider, op.emotion, op.model_id, rng, settings)
            seg = provider.synthesize(
                op.text, op.voice_id, output_format=output_format, voice_settings=vs
            )
            chunk_path = work_dir / f"chunk_{chunk_counter:05d}.wav"
            ffmpeg_stitch.segment_to_wav_file(seg, chunk_path, sample_rate=rate, channels=1)
            concat_paths.append(chunk_path)
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
                concat_paths.append(gap_path)
                silence_ms += op.gap_after_ms
                gap_counter += 1
    else:
        # Legacy flat render: one block per turn, fixed inter-turn gap, no emotion.
        plan: list[tuple[chunker.TextChunk, str, str]] = []  # (chunk, provider, voice_id)
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
                concat_paths.append(gap_path)
                silence_ms += gap_ms
                gap_counter += 1

            provider = registry.get(provider_name)
            seg = provider.synthesize(chunk.text, voice_id, output_format=output_format)
            chunk_path = work_dir / f"chunk_{i:05d}.wav"
            ffmpeg_stitch.segment_to_wav_file(seg, chunk_path, sample_rate=rate, channels=1)
            concat_paths.append(chunk_path)

            turn_durations[chunk.turn_index] = turn_durations.get(chunk.turn_index, 0) + len(seg)
            turn_meta[chunk.turn_index] = (chunk.speaker, voice_id, provider_name)
            prev_turn_index = chunk.turn_index

            report(step=f"Synthesizing {i + 1}/{total}", chunks_done=i + 1, chunks_total=total)

    report(step="Stitching", chunks_done=total, chunks_total=total)
    list_file = ffmpeg_stitch.build_concat_list(concat_paths, work_dir / "list.txt")
    master = ffmpeg_stitch.concat(list_file, work_dir / "master.wav")

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
    duration_ms = sum(turn_durations.values()) + silence_ms

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
    speed = request.speed if request.speed is not None else settings.sleep_default_speed
    pause_ms = (
        request.pause_ms if request.pause_ms is not None else settings.sleep_default_pause_ms
    )
    rate = settings.sleep_sample_rate
    provider_name = request.provider
    overrides = _chunk_overrides(settings)

    provider = registry.get(provider_name)
    voice_settings = _sleep_voice_settings(provider, request, speed)

    # Validate the ambient bed up front so we fail fast (before synthesis).
    bed_path: Path | None = None
    if request.ambient_bed:
        beds = ambient_registry.scan(settings.ambient_dir)
        bed_path = beds.get(request.ambient_bed)
        if bed_path is None:
            raise AmbientBedError(
                f"Ambient bed {request.ambient_bed!r} not found in {settings.ambient_dir}."
            )

    plan = chunker.chunk_prose(request.prose_text, provider_name, overrides=overrides)
    total = len(plan)

    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_paths: list[Path] = []
    narration_ms = 0
    gap_counter = 0

    for i, chunk in enumerate(plan):
        if i > 0 and pause_ms > 0:
            gap_path = work_dir / f"pause_{gap_counter:05d}.wav"
            ffmpeg_stitch.silence_wav(gap_path, duration_ms=pause_ms, sample_rate=rate)
            concat_paths.append(gap_path)
            narration_ms += pause_ms
            gap_counter += 1

        seg = provider.synthesize(
            chunk.text,
            request.voice_id,
            output_format=settings.segment_output_format,
            voice_settings=voice_settings,
        )
        chunk_path = work_dir / f"chunk_{i:05d}.wav"
        ffmpeg_stitch.segment_to_wav_file(seg, chunk_path, sample_rate=rate, channels=1)
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
