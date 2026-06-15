"""List the ambient soundscape beds available for sleep stories."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.core.models import AmbientBed
from app.storage import ambient_registry

router = APIRouter()


@router.get("/ambient", response_model=list[AmbientBed])
def list_ambient(settings: SettingsDep) -> list[AmbientBed]:
    """Return the ambient beds discovered under ``ambient_dir`` (may be empty)."""
    beds = ambient_registry.scan(settings.ambient_dir)
    return [
        AmbientBed(id=slug, name=slug.replace("_", " ").title())
        for slug in sorted(beds)
    ]
