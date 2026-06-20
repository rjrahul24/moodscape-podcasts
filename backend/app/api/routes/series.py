"""List the podcast series available for branded intro/outro."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.core.models import SeriesInfo
from app.storage import series_registry

router = APIRouter()


@router.get("/series", response_model=list[SeriesInfo])
def list_series(settings: SettingsDep) -> list[SeriesInfo]:
    """Return the series configs discovered under ``series_dir`` (may be empty)."""
    configs = series_registry.scan(settings.series_dir)
    return [
        SeriesInfo(id=slug, name=cfg.name)
        for slug, cfg in sorted(configs.items())
    ]
