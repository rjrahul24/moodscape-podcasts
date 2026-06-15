"""Voices available for the per-speaker dropdowns, grouped by provider.

The response is resilient: each provider is listed independently, so one
provider failing (ElevenLabs without a key, F5 with no reference assets, a local
model whose libraries aren't installed) does not prevent the others from being
selectable. ElevenLabs additionally honours ``VOICE_CATALOG`` filtering.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.core.errors import ProviderError
from app.core.models import ProviderVoices, Voice
from app.providers import registry

router = APIRouter()


def _elevenlabs_voices(settings, provider) -> list[Voice]:
    """List ElevenLabs voices, honouring the optional VOICE_CATALOG filter."""
    catalog = [e for e in settings.voice_catalog if e.provider == provider.name]
    if not catalog:
        return provider.list_voices()

    by_id = {v.id: v for v in provider.list_voices()}
    resolved: list[Voice] = []
    for entry in catalog:
        found = by_id.get(entry.id)
        resolved.append(
            found
            if found is not None
            else Voice(id=entry.id, name=entry.label or entry.id, provider=provider.name)
        )
    return resolved


@router.get("/voices", response_model=list[ProviderVoices])
def list_voices(settings: SettingsDep) -> list[ProviderVoices]:
    groups: list[ProviderVoices] = []
    for name in registry.available():
        provider = registry.get(name)
        try:
            if name == "elevenlabs":
                voices = _elevenlabs_voices(settings, provider)
            else:
                voices = provider.list_voices()
            groups.append(ProviderVoices(provider=name, voices=voices))
        except ProviderError as exc:
            groups.append(ProviderVoices(provider=name, voices=[], error=str(exc)))
        except Exception as exc:  # noqa: BLE001 - never let one provider break the list
            groups.append(ProviderVoices(provider=name, voices=[], error=str(exc)))
    return groups
