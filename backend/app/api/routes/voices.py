"""Voices available for the per-speaker dropdown.

If ``VOICE_CATALOG`` is configured, only those voice ids are offered (names
resolved from the provider, label used as a fallback). Otherwise every voice on
the account is returned.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import SettingsDep
from app.core.errors import ProviderError, ProviderNotFoundError
from app.core.models import Voice
from app.providers import registry

router = APIRouter()


@router.get("/voices", response_model=list[Voice])
def list_voices(settings: SettingsDep) -> list[Voice]:
    try:
        if not settings.voice_catalog:
            return registry.get(settings.default_provider).list_voices()

        # Resolve only the catalogued voices, grouped by their provider.
        catalog_by_provider: dict[str, dict[str, str | None]] = {}
        for entry in settings.voice_catalog:
            catalog_by_provider.setdefault(entry.provider, {})[entry.id] = entry.label

        resolved: list[Voice] = []
        for provider_name, wanted in catalog_by_provider.items():
            by_id = {v.id: v for v in registry.get(provider_name).list_voices()}
            for voice_id, label in wanted.items():
                found = by_id.get(voice_id)
                resolved.append(
                    found
                    if found is not None
                    else Voice(
                        id=voice_id,
                        name=label or voice_id,
                        provider=provider_name,
                    )
                )
        return resolved
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
