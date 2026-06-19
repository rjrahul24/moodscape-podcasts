"""Long-form quality control: transcript fidelity (WER) + speaker drift (SIM).

The two failure modes that creep into 30–90 min local generations are (1) the
model hallucinating or dropping words and (2) a cloned voice slowly drifting away
from the reference timbre. Neither is visible without listening to the whole thing
— so this module checks both automatically against the rendered master.

It is an **opt-in, non-fatal post-step** (gated by ``Settings.enable_qc``): a
successful render must never fail because QC couldn't run. The heavy libraries
(Whisper for ASR, a speaker encoder for embeddings) are imported lazily and, if
missing, degrade to a ``None`` metric plus a human-readable note — exactly the
philosophy the providers use. So ``uv run pytest`` and the default render path
stay light; QC deps live behind ``uv sync --extra qc``.

Pure helpers (word normalization, edit-distance WER) have no dependencies and are
unit-tested directly; the lazy ASR/embedding paths are faked in tests.
"""

from __future__ import annotations

import logging
import re

from app.config import Settings

from .models import QCReport, QCWindow

logger = logging.getLogger("moodscape")

# Words for WER: lowercase alphanumerics + apostrophes. Punctuation and casing
# don't count as errors; markup tags are stripped before this ever runs.
_WORD_RE = re.compile(r"[a-z0-9']+")
_TAG_RE = re.compile(r"\[[^\]]*\]")  # inline markup like [pause:600] / [calm]


def strip_markup(text: str) -> str:
    """Remove inline ``[...]`` tags so they don't count as reference words."""
    return _TAG_RE.sub(" ", text)


def normalize_words(text: str) -> list[str]:
    """Lowercase, drop punctuation/markup, return the bare word sequence."""
    return _WORD_RE.findall(text.lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level WER = edit distance(ref, hyp) / len(ref words).

    Returns 0.0 for two empty inputs and 1.0 when the reference is empty but the
    hypothesis is not (everything is an insertion). Uses an O(n·m) DP with two
    rolling rows, which is plenty for a single episode's word counts.
    """
    ref = normalize_words(reference)
    hyp = normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        curr = [i]
        for j, h in enumerate(hyp, start=1):
            cost = 0 if r == h else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1] / len(ref)


# ── transcription (lazy) ──────────────────────────────────────────────────────
def transcribe(audio_path: str, settings: Settings) -> tuple[str | None, str | None]:
    """Transcribe ``audio_path`` with a local Whisper.

    Prefers ``mlx_whisper`` (Apple Silicon), falls back to ``faster_whisper``
    (CPU). Returns ``(text, None)`` on success or ``(None, note)`` when neither
    backend is available/usable — never raises.
    """
    try:
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio_path, path_or_hf_repo=settings.qc_whisper_mlx_repo
        )
        return (result["text"].strip(), None)
    except Exception as exc:  # noqa: BLE001 - fall through to faster-whisper
        mlx_note = f"mlx_whisper unavailable ({exc})"

    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(settings.qc_whisper_faster_size)
        segments, _info = model.transcribe(audio_path)
        text = " ".join(seg.text for seg in segments).strip()
        return (text, None)
    except Exception as exc:  # noqa: BLE001
        return (
            None,
            f"transcription skipped — no Whisper backend: {mlx_note}; "
            f"faster_whisper unavailable ({exc}). Install with `uv sync --extra qc`.",
        )


# ── speaker similarity (lazy) ──────────────────────────────────────────────────
def speaker_similarity(
    audio_path: str, reference_audio: str, settings: Settings
) -> tuple[QCReport, str | None]:
    """Window the master and compare each window's voice print to the reference.

    Uses ``resemblyzer``'s partial embeddings (it windows internally), so drift
    that develops late in a long story shows up as windows whose cosine
    similarity to the reference falls below ``qc_sim_threshold``. Returns a
    partial ``QCReport`` (sim_* fields only) plus an optional note; degrades to an
    empty report + note when the encoder isn't installed. Never raises.
    """
    try:
        import numpy as np
        from resemblyzer import VoiceEncoder, preprocess_wav
    except Exception as exc:  # noqa: BLE001
        return (
            QCReport(),
            f"speaker-similarity skipped — resemblyzer unavailable ({exc}). "
            "Install with `uv sync --extra qc`.",
        )

    try:
        encoder = VoiceEncoder(verbose=False)
        ref_embed = encoder.embed_utterance(preprocess_wav(reference_audio))
        gen_wav = preprocess_wav(audio_path)
        _whole, partials, slices = encoder.embed_utterance(
            gen_wav, return_partials=True
        )
    except Exception as exc:  # noqa: BLE001
        return (QCReport(), f"speaker-similarity skipped — embedding failed ({exc})")

    def _cos(a, b) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)

    threshold = settings.qc_sim_threshold
    sims = [_cos(ref_embed, p) for p in partials]
    if not sims:
        return (QCReport(), "speaker-similarity skipped — audio too short to window")

    flagged = [
        QCWindow(start_s=float(sl.start) / 16000.0, similarity=round(s, 4))
        for sl, s in zip(slices, sims)
        if s < threshold
    ]
    return (
        QCReport(
            sim_mean=round(sum(sims) / len(sims), 4),
            sim_min=round(min(sims), 4),
            sim_flagged=flagged,
        ),
        None,
    )


# ── orchestration entry point ──────────────────────────────────────────────────
def run_qc(
    audio_path: str,
    *,
    source_text: str,
    settings: Settings,
    reference_audio: str | None = None,
) -> QCReport:
    """Run the enabled QC checks on a rendered master and return a report.

    Always attempts WER (against ``source_text``, markup stripped). Runs speaker
    similarity only when a ``reference_audio`` clip is supplied (i.e. a single
    cloned voice). Any missing dependency degrades to a ``None`` metric plus a
    note in ``report.notes`` — this function never raises.
    """
    notes: list[str] = []
    report = QCReport()

    transcript, note = transcribe(audio_path, settings)
    if note:
        notes.append(note)
    if transcript is not None:
        report.transcript = transcript
        report.wer = round(word_error_rate(strip_markup(source_text), transcript), 4)

    if reference_audio:
        sim_report, sim_note = speaker_similarity(
            audio_path, reference_audio, settings
        )
        if sim_note:
            notes.append(sim_note)
        report.sim_mean = sim_report.sim_mean
        report.sim_min = sim_report.sim_min
        report.sim_flagged = sim_report.sim_flagged

    report.notes = notes
    return report
