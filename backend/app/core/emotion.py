"""Shared tone-tag vocabulary and provider-neutral mappings.

A small, fixed set of inline tone tags (e.g. ``[excited]``, ``[calm]``) can ride
a chunk via ``voice_settings`` to colour how a podcast turn is spoken. Every
provider interprets the *same* labels in its own terms: speed-aware local models
(Kokoro, F5) nudge their speaking rate; ElevenLabs maps each label to a native
voice-settings profile (see ``elevenlabs_provider``). Keeping the vocabulary in
one place means the text processor, orchestrator, and providers all agree.

This is the "voice emotion" half of the sanctioned podcast pacing exception —
it shapes *how words are spoken*, never adds meditation-style audio processing.
"""

from __future__ import annotations

# Recognized inline tone tags (lowercased). A leading ``[tag]`` whose name is in
# this set is consumed as the chunk's emotion; any other bracket tag is left in
# the text untouched (matching the parser's existing pass-through behaviour).
EMOTIONS: frozenset[str] = frozenset(
    {"excited", "calm", "sad", "whispering", "neutral"}
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
}


def speed_multiplier(emotion: str | None) -> float:
    """Return the speaking-rate multiplier for ``emotion`` (1.0 if unknown/None)."""
    if not emotion:
        return 1.0
    return EMOTION_SPEED.get(emotion, 1.0)
