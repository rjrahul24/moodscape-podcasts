"""Filesystem layout for generated episodes.

Each generation job gets its own directory under ``OUTPUT_DIR``:

    output/<job_id>/episode.wav
    output/<job_id>/episode.mp3
"""

from __future__ import annotations

import uuid
from pathlib import Path

EPISODE_BASENAME = "episode"


def new_job_id() -> str:
    return uuid.uuid4().hex


def job_dir(output_dir: str | Path, job_id: str) -> Path:
    """Return the directory for ``job_id`` (not created)."""
    return Path(output_dir) / job_id


def resolve_download(output_dir: str | Path, job_id: str, filename: str) -> Path | None:
    """Resolve a requested download path, guarding against path traversal.

    Returns the file path if it exists and lives inside the job directory,
    otherwise ``None``.
    """
    base = job_dir(output_dir, job_id).resolve()
    candidate = (base / filename).resolve()
    if base not in candidate.parents and candidate != base:
        return None
    if not candidate.is_file():
        return None
    return candidate
