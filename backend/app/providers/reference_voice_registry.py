"""Discover reference voices (clone targets) from the assets folder.

Shared by every local provider that clones from a short reference clip — F5 and
CosyVoice3 both read the same audio + transcript pairs.

Layout (mirrors the source meditation project):

    <assets_dir>/speakers/reference_audio/<slug>.wav
    <assets_dir>/speakers/reference_text/<slug>.txt

A voice is registered only when both files exist and the transcript is
non-empty. The slug is the filename stem.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger("moodscape")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _dirs(assets_dir: Path) -> tuple[Path, Path]:
    speakers = Path(assets_dir) / "speakers"
    return speakers / "reference_audio", speakers / "reference_text"


def slugify(name: str) -> str:
    """Turn a display name into a filesystem-safe slug (the registry key)."""
    return _SLUG_RE.sub("_", name.strip().lower()).strip("_")


def save(
    assets_dir: Path, slug: str, audio_src: str | Path, transcript: str
) -> dict[str, Path]:
    """Persist a cleaned clip + transcript into the registry layout.

    Copies ``audio_src`` to ``reference_audio/<slug>.wav`` and writes
    ``transcript`` to ``reference_text/<slug>.txt`` (creating the dirs). Overwrites
    an existing voice with the same slug. Returns the written paths. F5 and
    CosyVoice3 pick it up automatically on the next ``scan``.
    """
    audio_dir, text_dir = _dirs(assets_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{slug}.wav"
    text_path = text_dir / f"{slug}.txt"
    shutil.copyfile(audio_src, audio_path)
    text_path.write_text(transcript.strip(), encoding="utf-8")
    return {"audio": audio_path.resolve(), "transcript": text_path.resolve()}


def scan(assets_dir: Path) -> dict[str, dict[str, Path]]:
    """Return ``{slug: {"audio": Path, "transcript": Path}}`` for complete pairs."""
    audio_dir, text_dir = _dirs(assets_dir)
    registry: dict[str, dict[str, Path]] = {}

    if not audio_dir.is_dir():
        logger.debug("reference_audio directory not found: %s", audio_dir)
        return registry

    for wav_path in sorted(audio_dir.glob("*.wav")):
        slug = wav_path.stem
        txt_path = text_dir / f"{slug}.txt"
        if not txt_path.is_file():
            logger.debug("voice %r skipped — no transcript at %s", slug, txt_path)
            continue
        if txt_path.stat().st_size == 0:
            logger.warning("voice %r skipped — empty transcript: %s", slug, txt_path)
            continue
        registry[slug] = {"audio": wav_path.resolve(), "transcript": txt_path.resolve()}

    return registry
