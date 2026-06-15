"""Kokoro TTS provider — local, named built-in voices.

Heavy imports (``kokoro``, ``torch``) happen lazily inside ``synthesize`` so the
app boots and voices list even when the ML stack isn't ready. The model is
loaded once and cached on the instance.

Core path only — none of the meditation project's pacing/humanize/FX is copied.
"""

from __future__ import annotations

import logging

import numpy as np
from pydub import AudioSegment

from app.core.errors import ProviderError
from app.core.models import Voice
from app.core.stitcher import numpy_to_segment

from .base import TTSProvider

logger = logging.getLogger("moodscape")

SAMPLE_RATE = 24000  # Kokoro always outputs 24 kHz

# Built-in voices (id -> human label). British voices (bf_/bm_) need the
# lang_code="b" pipeline; everything else uses American English ("a").
VOICES: dict[str, str] = {
    "af_heart": "Heart (US F) — warm, calm",
    "af_bella": "Bella (US F) — warm, friendly",
    "af_nicole": "Nicole (US F) — smooth, ASMR",
    "af_sarah": "Sarah (US F)",
    "af_sky": "Sky (US F)",
    "af_nova": "Nova (US F) — intimate",
    "am_adam": "Adam (US M)",
    "am_michael": "Michael (US M)",
    "bf_emma": "Emma (UK F)",
    "bf_lily": "Lily (UK F)",
    "bm_george": "George (UK M)",
}


class KokoroProvider(TTSProvider):
    name = "kokoro"

    def __init__(self, *, speed: float = 1.0):
        self._speed = speed
        self._pipeline_us = None  # lang_code="a"
        self._pipeline_gb = None  # lang_code="b"

    # ── interface ─────────────────────────────────────────────────────────────
    def list_voices(self) -> list[Voice]:
        return [
            Voice(id=vid, name=label, provider=self.name)
            for vid, label in VOICES.items()
        ]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> AudioSegment:
        pipe = self._get_pipeline(voice_id)
        try:
            chunks: list[np.ndarray] = []
            for _graphemes, _phonemes, audio in pipe(
                text, voice=voice_id, speed=self._speed, split_pattern=""
            ):
                if audio is None:
                    continue
                arr = audio if isinstance(audio, np.ndarray) else audio.detach().cpu().numpy()
                chunks.append(arr.astype(np.float32).squeeze())
        except Exception as exc:  # noqa: BLE001 - surface any inference failure
            raise ProviderError(self.name, f"synthesis failed: {exc}") from exc

        if not chunks:
            raise ProviderError(self.name, f"no audio produced for voice {voice_id!r}")

        samples = np.concatenate(chunks)
        return numpy_to_segment(samples, SAMPLE_RATE)

    # ── lazy model loading ────────────────────────────────────────────────────
    def _get_pipeline(self, voice_id: str):
        is_british = voice_id.split("_", 1)[0] in ("bf", "bm")
        if is_british:
            if self._pipeline_gb is None:
                self._pipeline_gb = self._build_pipeline("b")
            return self._pipeline_gb
        if self._pipeline_us is None:
            self._pipeline_us = self._build_pipeline("a")
        return self._pipeline_us

    def _build_pipeline(self, lang_code: str):
        try:
            from kokoro import KPipeline
        except Exception as exc:  # noqa: BLE001 - missing/broken install
            raise ProviderError(
                self.name,
                "could not import 'kokoro'. Install local-TTS deps "
                f"(`uv sync`). Underlying error: {exc}",
            ) from exc

        # Force CPU on Apple Silicon — MPS triggers deallocation bus errors with
        # Kokoro (per the reference implementation). Use CUDA when present.
        device = "cpu"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
        except Exception:  # noqa: BLE001
            pass

        logger.info("Loading Kokoro pipeline (lang_code=%s) on %s", lang_code, device)
        try:
            return KPipeline(
                lang_code=lang_code,
                repo_id="hexgrad/Kokoro-82M",
                trf=True,  # transformer G2P -> no espeak system dependency
                device=device,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name, f"failed to load Kokoro model: {exc}"
            ) from exc
