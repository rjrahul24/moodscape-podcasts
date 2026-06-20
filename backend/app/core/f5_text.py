"""F5-TTS text normalization.

F5's G2P mishandles several punctuation patterns. This module normalizes
text before synthesis so the model produces clean, natural speech.

Pure regex — no dependencies, no ML imports.
"""

from __future__ import annotations

import re


def normalize_for_f5(text: str) -> str:
    """Normalize text for F5-TTS's G2P and prosody model."""
    # Colons -> commas (F5 ignores colons, producing no pause)
    text = re.sub(r":", ",", text)
    # Ellipses -> single period (F5 doesn't differentiate)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub("…", ".", text)
    # Em/en-dashes -> commas (not reliably handled by F5)
    text = re.sub(r"—|–|--+", ",", text)
    # Remove hyphens in compound words (causes mispronunciation).
    # Only between letters — not between digits.
    text = re.sub(r"(?<=[a-zA-Z])-(?=[a-zA-Z])", "", text)
    # ALL_CAPS words -> lowercase (prevents letter-by-letter spelling)
    text = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group().lower(), text)
    return text
