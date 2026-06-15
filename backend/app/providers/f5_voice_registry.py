"""Discover F5 reference voices from the assets folder.

Layout (mirrors the source meditation project):

    <assets_dir>/speakers/reference_audio/<slug>.wav
    <assets_dir>/speakers/reference_text/<slug>.txt

A voice is registered only when both files exist and the transcript is
non-empty. The slug is the filename stem.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("moodscape")


def _dirs(assets_dir: Path) -> tuple[Path, Path]:
    speakers = Path(assets_dir) / "speakers"
    return speakers / "reference_audio", speakers / "reference_text"


def scan(assets_dir: Path) -> dict[str, dict[str, Path]]:
    """Return ``{slug: {"audio": Path, "transcript": Path}}`` for complete pairs."""
    audio_dir, text_dir = _dirs(assets_dir)
    registry: dict[str, dict[str, Path]] = {}

    if not audio_dir.is_dir():
        logger.debug("F5 reference_audio directory not found: %s", audio_dir)
        return registry

    for wav_path in sorted(audio_dir.glob("*.wav")):
        slug = wav_path.stem
        txt_path = text_dir / f"{slug}.txt"
        if not txt_path.is_file():
            logger.debug("F5 voice %r skipped — no transcript at %s", slug, txt_path)
            continue
        if txt_path.stat().st_size == 0:
            logger.warning("F5 voice %r skipped — empty transcript: %s", slug, txt_path)
            continue
        registry[slug] = {"audio": wav_path.resolve(), "transcript": txt_path.resolve()}

    return registry
