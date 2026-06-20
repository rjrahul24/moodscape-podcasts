"""Backwards-compatible alias for the shared reference-voice registry.

F5 reference voices are now discovered by ``reference_voice_registry``. This
module re-exports ``scan``/``_dirs`` so existing imports
(``from . import f5_voice_registry``) keep working unchanged.
"""

from __future__ import annotations

from .reference_voice_registry import _dirs, scan

__all__ = ["scan", "_dirs"]
