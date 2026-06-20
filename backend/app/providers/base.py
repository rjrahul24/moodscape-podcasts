"""The abstract interface every TTS provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydub import AudioSegment

from app.core.models import Voice


class TTSProvider(ABC):
    """Provider-agnostic text-to-speech interface.

    Implementations turn a single chunk of text into a decoded pydub
    ``AudioSegment`` and expose the voices they offer. Returning an
    ``AudioSegment`` (rather than raw bytes) unifies cloud providers that emit
    encoded audio (ElevenLabs) with local models that emit raw numpy samples
    (Kokoro, F5) — the engine and stitcher then work in one currency.

    Providers must not know anything about scripts, stitching, or HTTP — that
    lives in the engine and API layers.
    """

    #: Stable, lowercase identifier used in the registry and in ``SpeakerVoice``.
    name: str

    # ── capability flags ──────────────────────────────────────────────────────
    # The orchestrator branches on these instead of hardcoding provider names, so
    # behaviour stays "split per model" without name checks leaking up the stack.

    #: Provider applies a numeric ``speed`` from voice_settings as an internal
    #: speaking-rate multiplier (local models: Kokoro, F5).
    consumes_local_speed: bool = False

    #: Provider accepts a native ``speed`` setting in its own API range
    #: (ElevenLabs, 0.7–1.2). Distinct from ``consumes_local_speed``: this is a
    #: model-native control, not a resampling/rate multiplier we apply ourselves.
    has_native_speed: bool = False

    #: Provider can *perform* inline breath/SFX tags (e.g. ``[deep_breath]``)
    #: rather than speaking them literally. When True the text processor leaves
    #: those tags in the chunk text; when False (every current provider) they are
    #: rewritten to short ``[pause:N]`` silences so the beat still lands. This is
    #: the extension point for a future model whose inline-tag vocabulary is
    #: verified against its real output.
    accepts_inline_sfx: bool = False

    #: Provider accepts cross-chunk context (``previous_text`` / ``next_text`` in
    #: voice_settings) so prosody flows across chunk boundaries in long-form
    #: renders (ElevenLabs). The orchestrator only builds and injects context for
    #: providers that advertise this.
    accepts_continuity: bool = False

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
