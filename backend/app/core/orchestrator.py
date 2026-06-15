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

import shutil
from pathlib import Path

from app.config import Settings
from app.providers import registry
from app.storage import ambient_registry, files

from . import ambient, chunker, ffmpeg_stitch, sleep_post
from .errors import AmbientBedError, VoiceAssignmentError
from .models import (
    GeneratedFile,
    GenerateResult,
    PodcastRequest,
    SegmentInfo,
    SleepStoryRequest,
)
from .script_parser import distinct_speakers, parse_script

# Providers that accept a numeric per-call ``speed`` via voice_settings.
_SPEED_AWARE = {"kokoro", "f5"}


def _noop(*, step: str, chunks_done: int, chunks_total: int) -> None:
    pass


def _chunk_overrides(settings: Settings) -> dict[str, int]:
    return {
        "kokoro": settings.kokoro_chunk_chars,
        "f5": settings.f5_chunk_chars,
        "elevenlabs": settings.elevenlabs_chunk_chars,
    }


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

    # Flatten every turn into bounded chunks, tagged with their speaker assignment.
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
    out_dir = files.job_dir(settings.output_dir, job_id)
    work_dir = out_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_paths: list[Path] = []
    # Aggregate render time per turn for SegmentInfo.
    turn_durations: dict[int, int] = {}
    turn_meta: dict[int, tuple[str, str, str]] = {}  # turn_index -> (speaker, voice, provider)
    prev_turn_index: int | None = None
    gap_counter = 0

    for i, (chunk, provider_name, voice_id) in enumerate(plan):
        if prev_turn_index is not None and chunk.turn_index != prev_turn_index and gap_ms > 0:
            gap_path = work_dir / f"gap_{gap_counter:05d}.wav"
            ffmpeg_stitch.silence_wav(gap_path, duration_ms=gap_ms, sample_rate=rate)
            concat_paths.append(gap_path)
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
    duration_ms = sum(turn_durations.values()) + gap_ms * max(gap_counter, 0)

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

    voice_settings = {"speed": speed} if provider_name in _SPEED_AWARE else None

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

    provider = registry.get(provider_name)
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
