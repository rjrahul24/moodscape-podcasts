"""F5 TTS provider — local, zero-shot voice cloning from a reference clip.

Voices come from reference ``.wav`` + ``.txt`` pairs under the assets folder
(see ``f5_voice_registry``). Heavy imports (``f5_tts``, ``torch``) happen lazily
inside ``synthesize``; ``list_voices`` only scans the filesystem.

Core path only — none of the meditation project's conditioning/VAD/microprosody
is copied. Reference preprocessing uses F5's own ``preprocess_ref_audio_text``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from app.core.errors import ProviderError
from app.core.models import Voice
from app.core.stitcher import numpy_to_segment

from . import f5_voice_registry
from .base import TTSProvider

logger = logging.getLogger("moodscape")

SAMPLE_RATE = 24000  # F5 (Vocos vocoder) outputs 24 kHz


class F5Provider(TTSProvider):
    name = "f5"

    def __init__(
        self,
        *,
        assets_dir: Path,
        speed: float = 1.0,
        nfe_step: int = 32,
        cfg_strength: float = 2.0,
        sway_coef: float = -1.0,
    ):
        self._assets_dir = Path(assets_dir)
        self._speed = speed
        self._nfe_step = nfe_step
        self._cfg_strength = cfg_strength
        self._sway_coef = sway_coef
        self._model = None
        # slug -> {"audio": processed_path, "text": transcript}
        self._ref_cache: dict[str, dict] = {}

    # ── interface ─────────────────────────────────────────────────────────────
    def list_voices(self) -> list[Voice]:
        registry = f5_voice_registry.scan(self._assets_dir)
        return [
            Voice(id=slug, name=slug.replace("_", " ").title(), provider=self.name)
            for slug in sorted(registry)
        ]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> AudioSegment:
        model = self._get_model()
        ref = self._get_reference(voice_id)

        try:
            wav, _sr, _ = model.infer(
                ref_file=ref["audio"],
                ref_text=ref["text"],
                gen_text=" ".join(text.split()),
                speed=self._speed,
                nfe_step=self._nfe_step,
                cfg_strength=self._cfg_strength,
                sway_sampling_coef=self._sway_coef,
                remove_silence=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, f"synthesis failed: {exc}") from exc

        arr = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
        return numpy_to_segment(arr.astype(np.float32).squeeze(), SAMPLE_RATE)

    # ── lazy model + reference loading ────────────────────────────────────────
    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            import torch
            from f5_tts.api import F5TTS
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name,
                "could not import 'f5_tts'/'torch'. Install local-TTS deps "
                f"(`uv sync`). Underlying error: {exc}",
            ) from exc

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info("Loading F5TTS (F5TTS_v1_Base) on %s", device)
        try:
            model = F5TTS(model="F5TTS_v1_Base", device=device)
            # fp16 avoids distortion artifacts seen with bf16/fp32 on some HW.
            model.ema_model.to(torch.float16)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, f"failed to load F5 model: {exc}") from exc

        self._model = model
        return model

    def _get_reference(self, slug: str) -> dict:
        if slug in self._ref_cache:
            return self._ref_cache[slug]

        registry = f5_voice_registry.scan(self._assets_dir)
        if slug not in registry:
            raise ProviderError(
                self.name,
                f"reference voice {slug!r} not found. Add "
                f"reference_audio/{slug}.wav + reference_text/{slug}.txt under "
                f"{self._assets_dir}/speakers/.",
            )

        ref_audio = str(registry[slug]["audio"])
        ref_text = Path(registry[slug]["transcript"]).read_text(encoding="utf-8").strip()

        try:
            from f5_tts.infer.utils_infer import preprocess_ref_audio_text

            proc_audio, proc_text = preprocess_ref_audio_text(ref_audio, ref_text)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name, f"failed to preprocess reference {slug!r}: {exc}"
            ) from exc

        self._ref_cache[slug] = {"audio": proc_audio, "text": proc_text}
        return self._ref_cache[slug]
