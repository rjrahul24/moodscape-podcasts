"""Turn → conversational plan: sentences, micro-pauses, and tone tags.

This is the provider-agnostic core of the "lifelike podcast" feature. Given one
parsed turn's text, it produces an ordered list of :class:`Speech` and
:class:`Pause` items that the orchestrator renders into audio with real silence
between them:

* a leading recognized tone tag (``[excited]``/``[calm]``/...) is lifted off a
  span and attached to its speech as ``emotion`` (and stripped from the text so
  no provider ever speaks the literal tag);
* explicit ``[pause:600]`` / ``[pause:600ms]`` markers become :class:`Pause`
  items at that exact point;
* each span is sentence-split, with a small *randomized* gap inserted between
  sentences (conversational micro-pauses, tens–low-hundreds of ms — NOT the
  long meditation-style padding used by sleep stories);
* byte-budget splitting of each sentence is delegated to :mod:`chunker` so the
  provider input ceilings are still respected.

The randomness source (``rng``) is injected so a job seeded by its id renders
deterministically and tests are stable. This module imports no providers and no
heavy ML libraries — it stays fast and safe to call before any model loads.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from . import chunker
from .emotion import EMOTIONS, SFX_PAUSE_MS, sfx_pause_ms

# Explicit author pause: [pause:600] or [pause:600ms] (whitespace tolerant).
_PAUSE_RE = re.compile(r"\[pause:\s*(\d+)\s*(?:ms)?\]", re.IGNORECASE)
# A single leading bracket tag at the start of a span, e.g. "[excited] ...".
_LEADING_TAG_RE = re.compile(r"^\s*\[([A-Za-z][\w-]*)\]\s*")
# Inline breath / SFX tags, e.g. [breath] / [deep_breath] / [sigh].
_SFX_RE = re.compile(
    r"\[(" + "|".join(re.escape(k) for k in SFX_PAUSE_MS) + r")\]", re.IGNORECASE
)


def _sfx_to_pauses(text: str) -> str:
    """Rewrite breath/SFX tags into equivalent ``[pause:N]`` markers.

    Used for providers that can't *perform* an inline breath: the tag becomes a
    short silence at the same point, so the timing beat still lands and no model
    ever speaks the literal tag. Providers that can perform tags
    (``accepts_inline_sfx``) skip this and keep the tag in the text.
    """
    return _SFX_RE.sub(lambda m: f"[pause:{sfx_pause_ms(m.group(1))}]", text)


@dataclass(frozen=True)
class Speech:
    """A chunk of text to synthesize, plus the silence that should follow it.

    ``emotion`` is a recognized tone label or ``None``. ``gap_after_ms`` is the
    micro-pause to insert after this chunk (0 at a span's final sentence — the
    inter-turn gap or an explicit pause handles that boundary).
    """

    text: str
    emotion: str | None
    gap_after_ms: int


@dataclass(frozen=True)
class Pause:
    """An explicit author-requested silence (from a ``[pause:N]`` tag)."""

    ms: int


PlanItem = Speech | Pause


def extract_emotion(span: str) -> tuple[str | None, str]:
    """Lift a recognized leading tone tag off ``span``.

    Returns ``(emotion, remaining_text)``. If the leading bracket tag is not a
    recognized emotion (e.g. ``[laughs]``), it is left in place and ``emotion``
    is ``None`` — preserving the existing parser's pass-through of unknown tags.
    """
    match = _LEADING_TAG_RE.match(span)
    if match and match.group(1).lower() in EMOTIONS:
        return match.group(1).lower(), span[match.end() :]
    return None, span


def plan_turn(
    text: str,
    *,
    provider: str,
    max_chars: int,
    rng: random.Random,
    gap_min_ms: int,
    gap_max_ms: int,
    inline_sfx: bool = False,
) -> list[PlanItem]:
    """Break one turn's ``text`` into an ordered list of speech + pause items.

    ``gap_min_ms``/``gap_max_ms`` bound the randomized inter-sentence micro-pause
    (drawn from ``rng``). ``max_chars`` is the provider's byte budget; overlong
    sentences are split via :func:`chunker.chunk_text`.

    ``inline_sfx`` reflects the provider's ``accepts_inline_sfx`` capability: when
    True, breath/SFX tags are left in the text for the model to perform; when
    False (the default for current providers) they become short ``[pause:N]``
    silences so the timing beat still lands.
    """
    lo, hi = (gap_min_ms, gap_max_ms) if gap_min_ms <= gap_max_ms else (gap_max_ms, gap_min_ms)
    items: list[PlanItem] = []

    if not inline_sfx:
        text = _sfx_to_pauses(text)

    # Split on explicit [pause:N] tags: re.split keeps captured durations in the
    # odd positions (text, ms, text, ms, ...).
    parts = _PAUSE_RE.split(text)
    for i, part in enumerate(parts):
        if i % 2 == 1:
            ms = int(part)
            if ms > 0:
                items.append(Pause(ms))
            continue

        emotion, body = extract_emotion(part)
        sentences = chunker.split_sentences(body)
        last_sentence = len(sentences) - 1
        for j, sentence in enumerate(sentences):
            pieces = chunker.chunk_text(sentence, max_chars)
            for k, piece in enumerate(pieces):
                is_last_piece = k == len(pieces) - 1
                # Only the end of a sentence (that isn't the span's last) earns a
                # micro-pause; sub-pieces of one sentence run together.
                if is_last_piece and j < last_sentence:
                    gap = rng.randint(lo, hi)
                else:
                    gap = 0
                items.append(Speech(piece, emotion, gap))

    return items
