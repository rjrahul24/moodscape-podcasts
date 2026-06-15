"""Domain models shared across the backend (and mirrored in the frontend).

These are deliberately provider-agnostic: a ``SpeakerVoice`` carries the
provider name so the engine can mix providers across speakers without any
special-casing.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Voice(BaseModel):
    """A selectable voice, as surfaced to the UI dropdown."""

    id: str
    name: str
    provider: str
    category: str | None = None


class ProviderVoices(BaseModel):
    """The voices offered by one provider, plus an optional load error.

    Grouping keeps the ``/api/voices`` response resilient: if one provider fails
    (no API key, missing assets, library not installed) the others still return.
    """

    provider: str
    voices: list[Voice] = Field(default_factory=list)
    error: str | None = None


class ScriptTurn(BaseModel):
    """A single spoken turn parsed from the script."""

    index: int
    speaker: str
    text: str


class SpeakerVoice(BaseModel):
    """The provider + voice assigned to one speaker label."""

    provider: str = "elevenlabs"
    voice_id: str


class GenerateRequest(BaseModel):
    """Payload for ``POST /api/generate``.

    ``speakers`` maps a speaker label (exactly as written in the script, e.g.
    ``"Speaker 1"``) to the provider + voice that should render its turns.
    """

    script_text: str
    speakers: dict[str, SpeakerVoice]
    output_format: str | None = None  # overrides Settings.segment_output_format
    gap_ms: int | None = None  # overrides Settings.inter_turn_gap_ms


class PodcastRequest(BaseModel):
    """Async-job payload for a multi-speaker podcast (``POST /api/jobs``).

    Same fields as :class:`GenerateRequest` plus a ``kind`` discriminator.
    """

    kind: Literal["podcast"] = "podcast"
    script_text: str
    speakers: dict[str, SpeakerVoice]
    output_format: str | None = None  # overrides Settings.segment_output_format
    gap_ms: int | None = None  # overrides Settings.inter_turn_gap_ms


class SleepStoryRequest(BaseModel):
    """Async-job payload for a single-speaker sleep story (``POST /api/jobs``).

    Plain prose (no ``[Speaker]`` markers), one voice, and calming controls. The
    sleep master is always rendered 44.1 kHz stereo with loudness normalization,
    gentle EQ/compression, fades, and an optional ambient bed — the sanctioned
    exception to the "no meditation processing" rule, scoped to this content type.
    """

    kind: Literal["sleep_story"] = "sleep_story"
    prose_text: str
    provider: str = "kokoro"
    voice_id: str
    speed: float | None = None  # overrides Settings.sleep_default_speed
    pause_ms: int | None = None  # inter-sentence silence; overrides default
    ambient_bed: str | None = None  # slug from /api/ambient (optional)


JobRequest = Annotated[
    Union[PodcastRequest, SleepStoryRequest],
    Field(discriminator="kind"),
]


class SegmentInfo(BaseModel):
    """Per-turn render metadata returned to the client."""

    index: int
    speaker: str
    voice_id: str
    provider: str
    duration_ms: int


class GeneratedFile(BaseModel):
    """A downloadable artifact of a generation job."""

    filename: str
    format: str
    download_url: str
    size_bytes: int


class GenerateResult(BaseModel):
    """Response for ``POST /api/generate`` and the ``result`` of a finished job."""

    job_id: str
    duration_ms: int
    segments: list[SegmentInfo]
    files: list[GeneratedFile] = Field(default_factory=list)


class JobCreated(BaseModel):
    """Immediate response to ``POST /api/jobs``."""

    job_id: str


class JobProgress(BaseModel):
    """A point-in-time progress snapshot, streamed over SSE and returned by poll."""

    status: Literal["queued", "running", "succeeded", "failed"]
    progress: float  # 0.0 .. 1.0
    step: str
    chunks_total: int = 0
    chunks_done: int = 0
    detail: str | None = None  # error message when failed


class JobView(BaseModel):
    """Full job status for ``GET /api/jobs/{id}`` polling."""

    job_id: str
    kind: Literal["podcast", "sleep_story"]
    progress: JobProgress
    result: GenerateResult | None = None


class AmbientBed(BaseModel):
    """A selectable ambient soundscape for sleep stories."""

    id: str
    name: str
