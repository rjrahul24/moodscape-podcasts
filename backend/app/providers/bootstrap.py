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
from .cosyvoice_provider import CosyVoiceProvider
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
        )
    )
    cosyvoice = CosyVoiceProvider(
        assets_dir=settings.assets_dir,
        model=settings.cosyvoice_model,
        cache_mb=settings.mlx_cache_mb,
    )
    registry.register(cosyvoice)

    # Optionally pre-compile kernels so the first real generate is fast. Off by
    # default; best-effort, so a missing MLX install just no-ops.
    if settings.warmup_providers:
        cosyvoice.warmup()
