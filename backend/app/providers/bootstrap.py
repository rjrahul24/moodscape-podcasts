"""Construct and register the concrete providers from settings.

This is the single place where providers are wired up. To add another provider,
construct it here and call ``registry.register(...)`` — nothing else changes.

Registration is dependency-light on purpose: provider constructors and
``list_voices`` must not import heavy ML libraries, so every provider is always
registered and the app always boots. Heavy imports happen lazily at synthesis.
"""

from __future__ import annotations

from app.config import Settings

from . import registry
from .elevenlabs_provider import ElevenLabsProvider
from .f5_provider import F5Provider
from .kokoro_provider import KokoroProvider


def bootstrap_providers(settings: Settings) -> None:
    """Register every provider the app should offer."""
    registry.register(
        ElevenLabsProvider(
            api_key=settings.elevenlabs_api_key,
            base_url=settings.elevenlabs_base_url,
            model_id=settings.elevenlabs_model_id,
            podcast_model=settings.elevenlabs_podcast_model,
            sleep_model=settings.elevenlabs_sleep_model,
            use_speaker_boost=settings.elevenlabs_use_speaker_boost,
            text_normalization=settings.elevenlabs_text_normalization,
            sleep_v3_stability=settings.elevenlabs_sleep_v3_stability,
            sleep_v3_pacing_tag=settings.elevenlabs_sleep_v3_pacing_tag,
            v2_native_breaks=settings.elevenlabs_v2_native_breaks,
        )
    )
    registry.register(KokoroProvider(speed=settings.kokoro_speed))
    registry.register(
        F5Provider(
            assets_dir=settings.assets_dir,
            speed=settings.f5_speed,
            device=settings.f5_device,
            dtype=settings.f5_dtype,
            nfe_step=settings.f5_nfe_step,
            cfg_strength=settings.f5_cfg_strength,
            sway_coef=settings.f5_sway_coef,
            ref_clip_seconds=settings.f5_ref_clip_seconds,
        )
    )
