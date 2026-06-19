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
    """The provider + voice assigned to one speaker label.

    ``model_id`` is an optional, provider-specific model override (used by
    ElevenLabs to pick ``eleven_multilingual_v2`` vs ``eleven_v3``). Other
    providers ignore it; when unset the provider falls back to its configured
    per-content-type default.
    """

    provider: str = "elevenlabs"
    voice_id: str
    model_id: str | None = None


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
    # Conversational pacing: sentence micro-pauses, variable turn gaps, per-chunk
    # speed jitter, and inline tone/pause tags. On by default; set False for the
    # legacy flat render (one block per turn, fixed gaps, no emotion).
    pacing: bool = True
    # Optional deterministic seed forwarded to ElevenLabs so a re-render matches
    # the previous cadence/emotion trajectory. None lets the model sample freely.
    seed: int | None = None


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
    model_id: str | None = None  # ElevenLabs model override (v2/v3); else ignored
    speed: float | None = None  # overrides Settings.sleep_default_speed
    pause_ms: int | None = None  # inter-sentence silence; overrides default
    ambient_bed: str | None = None  # slug from /api/ambient (optional)
    # Progressive ramp-down: speed gently decelerates and inter-sentence pauses
    # lengthen across the story (toward sleep onset). On by default; False holds a
    # single fixed speed/pause for the whole narration.
    ramp: bool = True
    # Delivery directive for instruct-capable providers (CosyVoice3 Instruct
    # Mode), e.g. "Speak very slowly and softly". Overrides the configured sleep
    # default; ignored by providers that don't accept instructions.
    style_prompt: str | None = None
    # Optional deterministic seed forwarded to ElevenLabs for reproducible
    # re-renders. None lets the model sample freely.
    seed: int | None = None


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


class QCWindow(BaseModel):
    """One windowed slice of the master flagged for low speaker similarity."""

    start_s: float  # window start time in the rendered master
    similarity: float  # cosine similarity to the reference clip (0..1)


class QCReport(BaseModel):
    """Optional long-form quality report (opt-in via ``Settings.enable_qc``).

    ``wer`` is the word error rate of a local-Whisper transcript vs the source
    text (markup stripped). The ``sim_*`` fields summarize speaker drift for a
    single cloned voice; ``notes`` records any check that was skipped (e.g. a QC
    dependency not installed), so a missing extra is visible rather than silent.
    """

    wer: float | None = None
    transcript: str | None = None
    sim_mean: float | None = None
    sim_min: float | None = None
    sim_flagged: list[QCWindow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GenerateResult(BaseModel):
    """Response for ``POST /api/generate`` and the ``result`` of a finished job."""

    job_id: str
    duration_ms: int
    segments: list[SegmentInfo]
    files: list[GeneratedFile] = Field(default_factory=list)
    qc: QCReport | None = None  # populated only when QC is enabled


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


class ReferenceVoiceCreated(BaseModel):
    """Result of uploading a reference clip for cloning (``POST /api/voices/reference``)."""

    id: str  # slug, the registry key + voice_id
    name: str  # display name
    providers: list[str]  # cloning providers that can now use it (f5, cosyvoice)
    transcript: str  # the transcript stored alongside the clip
    replaced: bool = False  # True if an existing voice with this slug was overwritten
    notes: list[str] = Field(default_factory=list)  # hygiene steps applied / skipped
