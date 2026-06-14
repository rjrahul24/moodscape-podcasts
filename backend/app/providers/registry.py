"""A tiny name -> provider registry.

Kept deliberately dumb: no import-time side effects, no config coupling.
Providers are constructed with their settings and registered explicitly at
startup (see ``bootstrap.py``), and tests can register fakes the same way.
"""

from __future__ import annotations

from app.core.errors import ProviderNotFoundError

from .base import TTSProvider

_registry: dict[str, TTSProvider] = {}


def register(provider: TTSProvider) -> None:
    """Register (or replace) a provider under ``provider.name``."""
    _registry[provider.name] = provider


def get(name: str) -> TTSProvider:
    """Return the provider registered under ``name``."""
    try:
        return _registry[name]
    except KeyError as exc:
        raise ProviderNotFoundError(
            f"No TTS provider registered under '{name}'. "
            f"Available: {sorted(_registry)}"
        ) from exc


def available() -> list[str]:
    """Return the names of all registered providers."""
    return sorted(_registry)


def clear() -> None:
    """Remove all providers (used by tests)."""
    _registry.clear()
