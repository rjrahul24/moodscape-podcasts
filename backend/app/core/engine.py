"""Orchestrates a generation job: parse -> synthesize per turn -> stitch -> export.

Pure-ish: depends only on settings + the provider registry, so it can be driven
from the API or from a test with a fake provider.
"""

from __future__ import annotations

from app.config import Settings
from app.providers import registry
from app.storage import files

from .errors import VoiceAssignmentError
from .models import (
    GeneratedFile,
    GenerateRequest,
    GenerateResult,
    SegmentInfo,
)
from .script_parser import distinct_speakers, parse_script
from .stitcher import bytes_to_segment, export_master, stitch


def generate(request: GenerateRequest, settings: Settings) -> GenerateResult:
    """Render ``request`` into a stitched episode and return its metadata."""
    turns = parse_script(request.script_text)

    # Every speaker used in the script must have a voice assigned.
    missing = [s for s in distinct_speakers(turns) if s not in request.speakers]
    if missing:
        raise VoiceAssignmentError(
            "No voice assigned for: " + ", ".join(missing) + "."
        )

    output_format = request.output_format or settings.segment_output_format
    gap_ms = request.gap_ms if request.gap_ms is not None else settings.inter_turn_gap_ms

    segments = []
    segment_infos: list[SegmentInfo] = []
    for turn in turns:
        assignment = request.speakers[turn.speaker]
        provider = registry.get(assignment.provider)
        audio_bytes = provider.synthesize(
            turn.text, assignment.voice_id, output_format=output_format
        )
        segment = bytes_to_segment(audio_bytes, output_format)
        segments.append(segment)
        segment_infos.append(
            SegmentInfo(
                index=turn.index,
                speaker=turn.speaker,
                voice_id=assignment.voice_id,
                provider=assignment.provider,
                duration_ms=len(segment),
            )
        )

    episode = stitch(segments, gap_ms)

    job_id = files.new_job_id()
    out_dir = files.job_dir(settings.output_dir, job_id)
    written = export_master(
        episode,
        out_dir,
        files.EPISODE_BASENAME,
        final_format=settings.final_format,
        also_export_mp3=settings.also_export_mp3,
    )

    generated_files = [
        GeneratedFile(
            filename=path.name,
            format=path.suffix.lstrip("."),
            download_url=f"/api/download/{job_id}/{path.name}",
            size_bytes=path.stat().st_size,
        )
        for path in written
    ]

    return GenerateResult(
        job_id=job_id,
        duration_ms=len(episode),
        segments=segment_infos,
        files=generated_files,
    )
