"""Domain models shared across the backend (and mirrored in the frontend).

These are deliberately provider-agnostic: a ``SpeakerVoice`` carries the
provider name so the engine can mix providers across speakers without any
special-casing.
"""

from __future__ import annotations

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
    """Response for ``POST /api/generate``."""

    job_id: str
    duration_ms: int
    segments: list[SegmentInfo]
    files: list[GeneratedFile] = Field(default_factory=list)
