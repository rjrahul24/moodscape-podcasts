"""The abstract interface every TTS provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.models import Voice


class TTSProvider(ABC):
    """Provider-agnostic text-to-speech interface.

    Implementations turn a single chunk of text into encoded audio bytes and
    expose the voices they offer. They must not know anything about scripts,
    stitching, or HTTP — that lives in the engine and API layers.
    """

    #: Stable, lowercase identifier used in the registry and in ``SpeakerVoice``.
    name: str

    @abstractmethod
    def list_voices(self) -> list[Voice]:
        """Return the voices available from this provider."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> bytes:
        """Render ``text`` with ``voice_id`` and return encoded audio bytes.

        ``output_format`` is the provider's own format string (e.g.
        ``"mp3_44100_128"`` or ``"wav_44100"``). The returned bytes are a
        complete, decodable audio container in that format.
        """
