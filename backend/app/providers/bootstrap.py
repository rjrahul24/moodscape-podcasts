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
from .f5_provider import F5Provider
from .kokoro_provider import KokoroProvider


def bootstrap_providers(settings: Settings) -> None:
    """Register every provider the app should offer."""
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
