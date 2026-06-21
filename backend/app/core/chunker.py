"""Sentence/turn-aware text chunking.

Every local TTS model has a hard input ceiling and degrades well before it:
Kokoro errors past 510 phonemized tokens (and rushes well before that), F5 can
only generate ~30s per pass. So the orchestrator never hands a provider an
arbitrarily long string — it splits text into bounded chunks here first.

This module is intentionally pure: it imports no providers and no heavy ML
libraries, so it is fast to test and safe to call before any model loads.

Budgets are expressed in **characters**, not tokens. The remsky/Kokoro-FastAPI
"175/250/450 token" defaults refer to phonemized tokens, which correlate with
characters far more closely than with BPE tokens; the research's own Stage-1
guidance is "~400 chars for Kokoro". Char budgets keep us safely under each
model's real limit without shipping a tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ScriptTurn

# Default per-provider character budgets. The orchestrator may override these
# from Settings; these are the safe fallbacks.
DEFAULT_BUDGETS: dict[str, int] = {
    "kokoro": 400,  # well under Kokoro's 510 phoneme-token cap, no "rushed" artifacts
    "f5": 250,  # ~18s of narration; stay well under F5's ~30s garble edge
}

# Fallback for any provider not in DEFAULT_BUDGETS (e.g. a future provider).
FALLBACK_BUDGET = 600

# Sentence terminators followed by whitespace. Kept deliberately simple — a
# heuristic splitter is good enough for narration and avoids a spaCy dependency.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class TextChunk:
    """One bounded unit of text to hand to a provider.

    ``turn_index`` ties the chunk back to its source ScriptTurn (podcasts) or is
    ``0`` for single-speaker prose (sleep stories). ``chunk_index`` is the
    ordinal across the whole job. ``ends_sentence`` marks chunks that finish on a
    sentence boundary, so the orchestrator knows where an inter-sentence pause is
    appropriate (sleep stories).
    """

    turn_index: int
    chunk_index: int
    speaker: str
    text: str
    ends_sentence: bool = True


def budget_for(provider: str, *, overrides: dict[str, int] | None = None) -> int:
    """Return the character budget for ``provider``.

    ``overrides`` (typically derived from Settings) takes precedence over the
    built-in defaults.
    """
    if overrides and provider in overrides:
        return overrides[provider]
    return DEFAULT_BUDGETS.get(provider, FALLBACK_BUDGET)


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences on terminal punctuation + whitespace.

    Returns non-empty, stripped sentences in order. Newlines inside the text are
    collapsed to spaces first so wrapped prose chunks cleanly.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return []
    return [s.strip() for s in _SENTENCE_END.split(collapsed) if s.strip()]


def _hard_split(sentence: str, max_chars: int) -> list[str]:
    """Split a single over-long sentence on word boundaries under ``max_chars``."""
    words = sentence.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Pack sentences into chunks no longer than ``max_chars``.

    Sentences are never split unless a single sentence exceeds ``max_chars`` (then
    it is hard-split on whitespace). Order is preserved.
    """
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence, max_chars))
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_turn(
    turn: ScriptTurn,
    provider: str,
    *,
    start_index: int,
    overrides: dict[str, int] | None = None,
) -> list[TextChunk]:
    """Chunk one parsed ScriptTurn (podcast path), preserving its speaker."""
    max_chars = budget_for(provider, overrides=overrides)
    pieces = chunk_text(turn.text, max_chars)
    return [
        TextChunk(
            turn_index=turn.index,
            chunk_index=start_index + i,
            speaker=turn.speaker,
            text=piece,
        )
        for i, piece in enumerate(pieces)
    ]


def chunk_prose(
    text: str,
    provider: str,
    *,
    overrides: dict[str, int] | None = None,
) -> list[TextChunk]:
    """Chunk single-speaker prose (sleep path).

    No ``[Speaker]`` parsing — the whole text is one narrator. Each chunk ends on
    a sentence boundary, so the orchestrator can insert inter-sentence pauses.
    """
    max_chars = budget_for(provider, overrides=overrides)
    pieces = chunk_text(text, max_chars)
    return [
        TextChunk(
            turn_index=0,
            chunk_index=i,
            speaker="narrator",
            text=piece,
        )
        for i, piece in enumerate(pieces)
    ]
