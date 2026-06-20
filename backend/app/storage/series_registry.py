"""Discover podcast series configurations from the assets folder.

Layout:

    <series_dir>/<slug>.json

Each JSON file defines a series brand: show name, speaker persona names, and
intro/outro music references. Used by the podcast content type when the user
selects a series for branded intro/outro with music.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.errors import SeriesMusicError
from app.core.models import SeriesConfig

logger = logging.getLogger("moodscape")


def scan(series_dir: str | Path) -> dict[str, SeriesConfig]:
    """Return ``{slug: SeriesConfig}`` for every valid series config found."""
    base = Path(series_dir)
    registry: dict[str, SeriesConfig] = {}
    if not base.is_dir():
        logger.debug("Series directory not found: %s", base)
        return registry

    for path in sorted(base.iterdir()):
        if path.suffix.lower() != ".json" or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("slug", path.stem)
            config = SeriesConfig(**data)
            registry[config.slug] = config
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping invalid series config %s: %s", path.name, exc)

    return registry


def get(slug: str, series_dir: str | Path) -> SeriesConfig:
    """Return the ``SeriesConfig`` for ``slug``, or raise ``SeriesMusicError``."""
    configs = scan(series_dir)
    config = configs.get(slug)
    if config is None:
        raise SeriesMusicError(f"Series {slug!r} not found in {series_dir}.")
    return config
