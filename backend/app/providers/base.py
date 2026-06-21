"""The abstract interface every TTS provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydub import AudioSegment

from app.core.models import Voice


class TTSProvider(ABC):
    """Provider-agnostic text-to-speech interface.

    Implementations turn a single chunk of text into a decoded pydub
    ``AudioSegment`` and expose the voices they offer. Local models emit raw
    numpy samples which are converted via ``stitcher.numpy_to_segment`` —
    the engine and stitcher then work in one currency.

    Providers must not know anything about scripts, stitching, or HTTP — that
    lives in the engine and API layers.
    """

    #: Stable, lowercase identifier used in the registry and in ``SpeakerVoice``.
    name: str

    # ── capability flags ──────────────────────────────────────────────────────

    #: Provider applies a numeric ``speed`` from voice_settings as an internal
    #: speaking-rate multiplier (local models: Kokoro, F5).
    consumes_local_speed: bool = False

    @abstractmethod
    def list_voices(self) -> list[Voice]:
        """Return the voices available from this provider.

        Must be cheap and dependency-light: it is called to populate the UI and
        should not import heavy ML libraries or load models.
        """

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> AudioSegment:
        """Render ``text`` with ``voice_id`` and return a decoded AudioSegment.

        ``output_format`` is the provider's own format string (e.g.
        ``"mp3_44100_128"``); cloud providers use it to request a quality, local
        providers ignore it (they emit a fixed sample rate). The engine
        normalizes sample rates across providers before stitching.
        """
