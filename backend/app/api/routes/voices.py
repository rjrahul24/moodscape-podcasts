"""Voices available for the per-speaker dropdowns, grouped by provider.

The response is resilient: each provider is listed independently, so one
provider failing (ElevenLabs without a key, F5 with no reference assets, a local
model whose libraries aren't installed) does not prevent the others from being
selectable. ElevenLabs additionally honours ``VOICE_CATALOG`` filtering.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import SettingsDep
from app.core import qc, ref_clean
from app.core.errors import ProviderError
from app.core.models import ProviderVoices, ReferenceVoiceCreated, Voice
from app.providers import reference_voice_registry, registry

router = APIRouter()

# Cloning providers that read the shared reference-voice registry.
_CLONE_PROVIDERS = ("f5", "cosyvoice")


def _elevenlabs_voices(settings, provider) -> list[Voice]:
    """List ElevenLabs voices, honouring the optional VOICE_CATALOG filter."""
    catalog = [e for e in settings.voice_catalog if e.provider == provider.name]
    if not catalog:
        return provider.list_voices()

    by_id = {v.id: v for v in provider.list_voices()}
    resolved: list[Voice] = []
    for entry in catalog:
        found = by_id.get(entry.id)
        if found is not None:
            # Prefer the catalog label over the API-returned name when set.
            if entry.label:
                found = Voice(
                    id=found.id, name=entry.label, provider=found.provider, category=found.category
                )
            resolved.append(found)
        else:
            resolved.append(
                Voice(id=entry.id, name=entry.label or entry.id, provider=provider.name)
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


@router.post("/voices/reference", response_model=ReferenceVoiceCreated)
async def add_reference_voice(
    settings: SettingsDep,
    name: str = Form(...),
    transcript: str | None = Form(None),
    audio: UploadFile = File(...),
) -> ReferenceVoiceCreated:
    """Upload + clean a short clip into the shared reference-voice registry.

    The clip is downmixed, resampled, silence-trimmed, optionally denoised, and
    length-capped, then persisted to ``assets/speakers/`` so F5 and CosyVoice3
    can clone from it. A transcript is required (the cloners condition on it); if
    none is supplied we try local Whisper (the QC extra) and fail with a clear
    message if that isn't available.
    """
    slug = reference_voice_registry.slugify(name)
    if not slug:
        raise HTTPException(422, "Provide a name made of letters or digits.")

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw_upload"
        raw.write_bytes(await audio.read())
        cleaned = Path(tmp) / "cleaned.wav"
        try:
            notes = ref_clean.clean_clip(str(raw), str(cleaned), settings=settings)
        except Exception as exc:  # noqa: BLE001 - bad/unsupported audio
            raise HTTPException(400, f"Could not read the audio file: {exc}") from exc

        text = (transcript or "").strip()
        if not text:
            text, note = qc.transcribe(str(cleaned), settings)
            if note:
                notes.append(note)
            if not text:
                raise HTTPException(
                    422,
                    "No transcript provided and auto-transcription is unavailable "
                    "(install with `uv sync --extra qc`). Add a transcript and retry.",
                )

        replaced = slug in reference_voice_registry.scan(settings.assets_dir)
        reference_voice_registry.save(settings.assets_dir, slug, str(cleaned), text)

    providers = [p for p in _CLONE_PROVIDERS if p in registry.available()]
    return ReferenceVoiceCreated(
        id=slug,
        name=slug.replace("_", " ").title(),
        providers=providers,
        transcript=text,
        replaced=replaced,
        notes=notes,
    )
