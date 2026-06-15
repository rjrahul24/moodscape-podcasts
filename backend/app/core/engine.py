"""Legacy synchronous entry point.

The real generation logic now lives in :mod:`app.core.orchestrator` (async-job
aware, chunked, disk-stitched). ``generate`` is kept as a thin adapter so the
existing ``POST /api/generate`` endpoint and its tests keep working: it maps the
legacy ``GenerateRequest`` onto a ``PodcastRequest`` and runs the orchestrator
synchronously with no progress reporting.
"""

from __future__ import annotations

from app.config import Settings

from . import orchestrator
from .models import GenerateRequest, GenerateResult, PodcastRequest


def generate(request: GenerateRequest, settings: Settings) -> GenerateResult:
    """Render ``request`` into a stitched episode and return its metadata."""
    podcast = PodcastRequest(
        script_text=request.script_text,
        speakers=request.speakers,
        output_format=request.output_format,
        gap_ms=request.gap_ms,
    )
    return orchestrator.run(podcast, settings)
