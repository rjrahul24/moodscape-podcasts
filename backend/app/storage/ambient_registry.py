"""Discover ambient soundscape beds from the assets folder.

Layout (mirrors the F5 voice registry):

    <ambient_dir>/<slug>.wav
    <ambient_dir>/<slug>.mp3

The slug is the filename stem; the display name is the slug title-cased. Any
``.wav``/``.mp3`` file is offered. Used by the sleep-story content type only.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("moodscape")

_EXTENSIONS = (".wav", ".mp3")


def scan(ambient_dir: str | Path) -> dict[str, Path]:
    """Return ``{slug: Path}`` for every ambient bed found in ``ambient_dir``."""
    base = Path(ambient_dir)
    registry: dict[str, Path] = {}
    if not base.is_dir():
        logger.debug("Ambient directory not found: %s", base)
        return registry

    for path in sorted(base.iterdir()):
        if path.suffix.lower() in _EXTENSIONS and path.is_file():
            # First file wins per slug (e.g. prefer .mp3 then .wav alphabetically).
            registry.setdefault(path.stem, path.resolve())
    return registry
