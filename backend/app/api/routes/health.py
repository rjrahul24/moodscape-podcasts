"""Health + capability check."""

from __future__ import annotations

import shutil

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.providers import registry

router = APIRouter()


@router.get("/health")
def health(settings: SettingsDep) -> dict:
    return {
        "status": "ok",
        "providers": registry.available(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "elevenlabs_key_configured": bool(settings.elevenlabs_api_key),
    }
