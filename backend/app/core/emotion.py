"""Shared tone-tag vocabulary and provider-neutral mappings.

A small, fixed set of inline tone tags (e.g. ``[excited]``, ``[calm]``) can ride
a chunk via ``voice_settings`` to colour how a podcast turn is spoken. Local
models (Kokoro, F5) nudge their speaking rate based on the label. Keeping the
vocabulary in one place means the text processor, orchestrator, and providers all
agree.

This is the "voice emotion" half of the sanctioned podcast pacing exception —
it shapes *how words are spoken*, never adds meditation-style audio processing.
"""

from __future__ import annotations

# Recognized inline tone tags (lowercased). A leading ``[tag]`` whose name is in
# this set is consumed as the chunk's emotion; any other bracket tag is left in
# the text untouched (matching the parser's existing pass-through behaviour). The
# mindfulness-leaning words (soothing/reflective/warm) extend the original set for
# wellness content — every provider still maps the same labels in its own terms.
EMOTIONS: frozenset[str] = frozenset(
    {
        "excited",
        "calm",
        "sad",
        "whispering",
        "neutral",
        "soothing",
        "reflective",
        "warm",
        "dreamy",
        "tender",
    }
)

# Per-emotion speaking-rate multiplier for speed-aware local providers
# (Kokoro, F5). Applied on top of the base/jittered speed, so values stay close
# to 1.0 to keep speech natural rather than caricatured.
EMOTION_SPEED: dict[str, float] = {
    "excited": 1.06,
    "calm": 0.94,
    "sad": 0.92,
    "whispering": 0.95,
    "neutral": 1.0,
    "soothing": 0.93,
    "reflective": 0.95,
    "warm": 0.97,
    "dreamy": 0.90,
    "tender": 0.96,
}

# Inline breath / SFX tags and the short silence each stands in for. These shape
# *timing* at conversational scale (a beat to breathe) — the same tens–to-low-
# hundreds-of-ms register as an author's explicit ``[pause:N]``, NOT the long
# meditative padding reserved for sleep stories. Tags are rewritten to this
# silence so the beat still lands without the model speaking the literal tag.
SFX_PAUSE_MS: dict[str, int] = {
    "breath": 250,
    "deep_breath": 600,
    "sigh": 400,
}


def speed_multiplier(emotion: str | None) -> float:
    """Return the speaking-rate multiplier for ``emotion`` (1.0 if unknown/None)."""
    if not emotion:
        return 1.0
    return EMOTION_SPEED.get(emotion, 1.0)


def sfx_pause_ms(tag: str | None) -> int | None:
    """Return the stand-in silence (ms) for a breath/SFX ``tag``, or None."""
    if not tag:
        return None
    return SFX_PAUSE_MS.get(tag.lower())
