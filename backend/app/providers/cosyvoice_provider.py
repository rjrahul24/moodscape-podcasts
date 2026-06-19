"""CosyVoice3 (MLX) provider — local Apple-Silicon cloning + Instruct Mode.

Voices come from the same reference ``.wav`` + ``.txt`` pairs F5 uses (see
``reference_voice_registry``). The heavy ``mlx_audio`` import (Apple Silicon only,
multi-GB) happens lazily inside ``synthesize`` — so the app still boots and lists
voices on any platform; failures surface as ``ProviderError`` and a per-provider
``error`` in ``/api/voices``.

Why this provider exists for sleep stories: CosyVoice3 is a flow-matching DiT
model with an *Instruct Mode* that decouples the cloned *timbre* from the
*delivery*. Passing an ``instruct`` directive in ``voice_settings`` (e.g. "Speak
slowly and calmly") drives a calm, hypnotic pace independently of the reference
clip's energy, so it holds across a 30–90 min story. The orchestrator injects the
sleep directive; without one we fall back to plain zero-shot cloning.

Pacing therefore rides the Instruct directive, not a numeric ``speed`` multiplier
(``consumes_local_speed = False``) — the model's own strength, no time-stretch
artifacts.

Core path only — no meditation-project conditioning/VAD/microprosody is copied.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from pydub import AudioSegment

from app.core.errors import ProviderError
from app.core.models import Voice

from . import reference_voice_registry
from .base import TTSProvider

logger = logging.getLogger("moodscape")

SAMPLE_RATE = 24000  # CosyVoice3 (HiFi-GAN vocoder) outputs 24 kHz


class CosyVoiceProvider(TTSProvider):
    name = "cosyvoice"
    # Delivery/pacing comes from the Instruct directive, not a rate multiplier.
    consumes_local_speed = False
    accepts_instruct = True

    def __init__(self, *, assets_dir: Path, model: str, cache_mb: int = 0):
        self._assets_dir = Path(assets_dir)
        self._model_id = model
        self._cache_mb = cache_mb  # MLX Metal cache cap in MB; 0 = MLX default
        self._model = None  # loaded MLX model, cached across chunks
        # slug -> {"audio": path, "text": transcript}
        self._ref_cache: dict[str, dict] = {}

    # ── interface ─────────────────────────────────────────────────────────────
    def list_voices(self) -> list[Voice]:
        registry = reference_voice_registry.scan(self._assets_dir)
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
        generate_audio = self._get_generate()
        model = self._get_model()
        ref = self._get_reference(voice_id)

        settings = voice_settings or {}
        instruct = settings.get("instruct")  # sleep delivery directive (optional)

        with tempfile.TemporaryDirectory() as tmp:
            # generate_audio writes to ``{file_prefix}.{audio_format}`` (relative
            # to CWD — it has no output-dir param), so make file_prefix a full
            # path inside the temp dir.
            prefix = str(Path(tmp) / "seg")
            kwargs: dict = dict(
                text=" ".join(text.split()),
                model=model,
                ref_audio=ref["audio"],
                file_prefix=prefix,
                audio_format="wav",
                join_audio=True,  # single deterministic {prefix}.wav
                verbose=False,
            )
            if instruct:
                # Instruct Mode: timbre from ref_audio, delivery from the
                # directive. ``ref_text`` MUST be omitted — CosyVoice3.generate
                # branches zero-shot (ref_text) *before* instruct, so passing
                # both silently drops the directive. The model skips Whisper when
                # instruct_text is set, so no transcript is needed.
                kwargs["instruct_text"] = instruct
            else:
                # Zero-shot cloning: pass the transcript (conditions cloning and
                # skips mlx_audio's ~1.5 GB Whisper auto-transcription).
                kwargs["ref_text"] = ref["text"]

            try:
                generate_audio(**kwargs)
            except Exception as exc:  # noqa: BLE001 - surface any inference failure
                raise ProviderError(self.name, f"synthesis failed: {exc}") from exc

            out = Path(f"{prefix}.wav")
            if not out.is_file():
                # Tolerate naming variance (e.g. join disabled -> per-chunk files).
                matches = sorted(Path(tmp).glob("seg*.wav"))
                if not matches:
                    raise ProviderError(
                        self.name, f"no audio produced for voice {voice_id!r}"
                    )
                out = matches[0]
            return AudioSegment.from_file(out, format="wav")

    # ── lazy import + model + reference loading ────────────────────────────────
    def _get_generate(self):
        try:
            from mlx_audio.tts.generate import generate_audio
        except Exception as exc:  # noqa: BLE001 - missing install / non-Apple Silicon
            raise ProviderError(
                self.name,
                "could not import 'mlx_audio'. CosyVoice3 runs on Apple Silicon "
                "only — install with `uv sync --extra mlx`. Underlying error: "
                f"{exc}",
            ) from exc
        return generate_audio

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from mlx_audio.tts.utils import load_model
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name,
                "could not import 'mlx_audio'. Install with `uv sync --extra mlx`. "
                f"Underlying error: {exc}",
            ) from exc

        self._cap_mlx_cache()
        logger.info("Loading CosyVoice3 (%s) via MLX", self._model_id)
        try:
            self._model = load_model(self._model_id)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name, f"failed to load CosyVoice3 model: {exc}"
            ) from exc
        return self._model

    def _cap_mlx_cache(self) -> None:
        """Bound MLX's Metal buffer cache so long jobs don't tip into SSD swap.

        Best-effort: the cache-limit API has moved between MLX releases
        (``mx.set_cache_limit`` vs ``mx.metal.set_cache_limit``), so we try the
        known spellings and quietly skip if none apply or ``cache_mb`` is 0.
        """
        if self._cache_mb <= 0:
            return
        limit_bytes = self._cache_mb * 1024 * 1024
        try:
            import mlx.core as mx
        except Exception:  # noqa: BLE001 - MLX missing (non-Apple-Silicon); nothing to cap
            return
        setter = getattr(mx, "set_cache_limit", None) or getattr(
            getattr(mx, "metal", None), "set_cache_limit", None
        )
        if setter is None:
            logger.info("MLX cache-limit API not found; skipping cap")
            return
        try:
            setter(limit_bytes)
            logger.info("Capped MLX Metal cache at %d MB", self._cache_mb)
        except Exception as exc:  # noqa: BLE001 - never fatal
            logger.info("Could not cap MLX cache: %s", exc)

    def warmup(self) -> None:
        """Pre-compile kernels with a silent dummy synthesis (best-effort).

        The first MLX inference pays a ~5x JIT penalty while Metal kernels
        compile. Calling this at startup moves that cost off the first real
        generate. Needs ``mlx_audio`` and at least one reference voice; any
        failure (missing install, no voices) is swallowed — warmup is optional.
        """
        voices = self.list_voices()
        if not voices:
            logger.info("CosyVoice3 warmup skipped: no reference voices")
            return
        try:
            self.synthesize(
                "Warming up.",
                voices[0].id,
                output_format="wav",
                voice_settings={"instruct": "Speak calmly."},
            )
            logger.info("CosyVoice3 warmup complete")
        except Exception as exc:  # noqa: BLE001 - warmup is best-effort
            logger.info("CosyVoice3 warmup skipped: %s", exc)

    def _get_reference(self, slug: str) -> dict:
        if slug in self._ref_cache:
            return self._ref_cache[slug]

        registry = reference_voice_registry.scan(self._assets_dir)
        if slug not in registry:
            raise ProviderError(
                self.name,
                f"reference voice {slug!r} not found. Add "
                f"reference_audio/{slug}.wav + reference_text/{slug}.txt under "
                f"{self._assets_dir}/speakers/.",
            )

        ref_audio = str(registry[slug]["audio"])
        ref_text = Path(registry[slug]["transcript"]).read_text(encoding="utf-8").strip()
        self._ref_cache[slug] = {"audio": ref_audio, "text": ref_text}
        return self._ref_cache[slug]
