"""Domain-level exceptions.

These are raised by the core/provider layers (which know nothing about HTTP)
and translated into HTTP responses by the API layer.
"""

from __future__ import annotations


class ScriptParseError(ValueError):
    """The pasted script could not be parsed into speaker turns."""


class VoiceAssignmentError(ValueError):
    """A speaker appears in the script but has no voice assigned."""


class ProviderError(RuntimeError):
    """A TTS provider failed (auth, quota, rate limit, network, ...)."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class ProviderNotFoundError(KeyError):
    """No provider is registered under the requested name."""


class AudioProcessingError(RuntimeError):
    """An ffmpeg subprocess (stitch, post-process, ambient mix) failed."""


class AmbientBedError(ValueError):
    """The requested ambient bed slug was not found in the ambient assets."""


class SeriesMusicError(ValueError):
    """The series config or its music assets could not be found/loaded."""
