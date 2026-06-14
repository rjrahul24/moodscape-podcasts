"""Construct and register the concrete providers from settings.

This is the single place where providers are wired up. To add VibeVoice later,
construct it here and call ``registry.register(...)`` — nothing else changes.
"""

from __future__ import annotations

from app.config import Settings

from . import registry
from .elevenlabs_provider import ElevenLabsProvider


def bootstrap_providers(settings: Settings) -> None:
    """Register every provider the app should offer."""
    registry.register(
        ElevenLabsProvider(
            api_key=settings.elevenlabs_api_key,
            base_url=settings.elevenlabs_base_url,
            model_id=settings.elevenlabs_model_id,
        )
    )
