"""F5 TTS provider — local, zero-shot voice cloning from a reference clip.

Voices come from reference ``.wav`` + ``.txt`` pairs under the assets folder
(see ``f5_voice_registry``). Heavy imports (``f5_tts``, ``torch``) happen lazily
inside ``synthesize``; ``list_voices`` only scans the filesystem.

Key quality features ported from the meditation reference project:
- Reference audio conditioning (RMS normalization + trailing noise pad)
- Whisper-verified ref_text (pass empty string to preprocess_ref_audio_text)
- Post-synthesis silence trimming + Silero VAD
- Short-phrase speed override for tiny fragments
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from app.core import emotion as emotion_map
from app.core.errors import ProviderError
from app.core.models import Voice
from app.core.stitcher import numpy_to_segment

from . import reference_voice_registry
from .base import TTSProvider

logger = logging.getLogger("moodscape")

SAMPLE_RATE = 24000  # F5 (Vocos vocoder) outputs 24 kHz

# ── Trailing-silence trimmer ─────────────────────────────────────────────────
_TRIM_THRESHOLD_DB = -45.0
_TRIM_TAIL_MS = 50.0


def _trim_trailing_silence(audio: np.ndarray, sr: int) -> np.ndarray:
    """Remove trailing silence from an F5-TTS speech chunk.

    Finds the last sample whose absolute amplitude exceeds _TRIM_THRESHOLD_DB,
    then retains a _TRIM_TAIL_MS decay tail.
    """
    threshold = 10 ** (_TRIM_THRESHOLD_DB / 20.0)
    active = np.where(np.abs(audio) > threshold)[0]
    if len(active) == 0:
        return audio
    tail = int(_TRIM_TAIL_MS / 1000.0 * sr)
    cut = min(int(active[-1]) + tail + 1, len(audio))
    return audio[:cut]


# ── Silero VAD ───────────────────────────────────────────────────────────────
_VAD_GAIN_FLOOR = 0.15
_VAD_CROP_TAIL_MS = 100.0
_vad_cache: tuple | None = None


def _get_vad():
    """Load Silero VAD once and cache for reuse across chunks."""
    global _vad_cache
    if _vad_cache is not None:
        return _vad_cache
    import torch

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        trust_repo=True,
    )
    _vad_cache = (model, utils)
    return _vad_cache


def _apply_silero_vad(audio: np.ndarray, sr: int) -> np.ndarray:
    """Crop trailing non-speech and attenuate interior gaps via Silero VAD.

    Two-pass: (1) crop after last speech endpoint + safety tail,
    (2) attenuate interior non-speech to 15% with gaussian-smoothed envelope.
    Falls back to the original audio if Silero fails.
    """
    try:
        import torch
        import torchaudio

        model, utils = _get_vad()
        (get_speech_timestamps, _, _, _, _) = utils

        vad_sr = 16000
        audio_torch = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        audio_16k = torchaudio.functional.resample(audio_torch, sr, vad_sr).squeeze(0)
        scale = sr / vad_sr

        speech_timestamps = get_speech_timestamps(audio_16k, model, sampling_rate=vad_sr)
        speech_timestamps = [
            {"start": int(ts["start"] * scale), "end": int(ts["end"] * scale)}
            for ts in speech_timestamps
        ]

        if not speech_timestamps:
            return audio

        # Pass 1: Crop trailing non-speech
        last_speech_end = speech_timestamps[-1]["end"]
        crop_tail = int(_VAD_CROP_TAIL_MS / 1000.0 * sr)
        crop_idx = min(last_speech_end + crop_tail, len(audio))
        audio = audio[:crop_idx]

        # Pass 2: Attenuate interior non-speech
        mask = np.full(len(audio), _VAD_GAIN_FLOOR, dtype=np.float64)
        fade_samples = int(0.05 * sr)

        for ts in speech_timestamps:
            start, end = ts["start"], min(ts["end"], len(audio))
            s = max(0, start - fade_samples)
            e = min(len(mask), end + fade_samples)
            mask[s:e] = 1.0

        from scipy.ndimage import gaussian_filter1d

        mask = gaussian_filter1d(mask, sigma=fade_samples / 4.0)
        return (audio * mask).astype(np.float32)
    except Exception as exc:
        logger.warning("Silero VAD failed, using trimmed audio: %s", exc)
        return audio


# ── Reference audio conditioning ─────────────────────────────────────────────
_REF_TARGET_DBFS = -20.0


def _clip_audio_file(audio_path: str, clip_seconds: float) -> str:
    """Trim an audio file to ``clip_seconds`` and return a temp WAV path.

    F5 recomputes the whole reference+generated sequence every chunk, so the
    reference length is a direct per-chunk runtime multiplier. A few seconds is
    plenty to clone a voice. Clipping happens *before* Whisper transcription so
    the derived ref_text matches the (shorter) audio exactly — otherwise the
    transcript would describe words no longer present, reintroducing leakage.
    Returns the original path unchanged if it's already within the limit.
    """
    import soundfile as sf

    audio, file_sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    max_samples = int(clip_seconds * file_sr)
    if len(audio) <= max_samples:
        return audio_path
    audio = audio[:max_samples]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="_clip.wav")
    tmp.close()
    sf.write(tmp.name, audio.astype(np.float32), file_sr, subtype="PCM_16")
    return tmp.name


def _condition_reference_audio(audio_path: str) -> str:
    """Condition reference audio: RMS-normalize + append trailing noise pad.

    The trailing noise (~1s at -55 dBFS) prevents F5's duration heuristic from
    leaking stray reference syllables into short generations.
    Returns a temp WAV path with conditioned audio.
    """
    import soundfile as sf

    audio, file_sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # RMS normalize
    preserve = os.environ.get("MOODSCAPE_F5_REF_PRESERVE_DYNAMICS", "0") == "1"
    rms = float(np.sqrt(np.mean(audio**2)))
    if rms > 1e-8 and not preserve:
        target_rms = 10 ** (_REF_TARGET_DBFS / 20.0)
        audio = audio * (target_rms / rms)

    # Trailing noise pad
    if os.environ.get("MOODSCAPE_F5_REF_PAD", "1") == "1":
        pad_sec = float(os.environ.get("MOODSCAPE_F5_REF_PAD_SEC", "1.0"))
        pad_dbfs = float(os.environ.get("MOODSCAPE_F5_REF_PAD_DBFS", "-55.0"))
        n_pad = int(pad_sec * file_sr)
        if n_pad > 0:
            pad_rms = 10 ** (pad_dbfs / 20.0)
            tail = np.random.randn(n_pad).astype(np.float32) * pad_rms
            audio = np.concatenate([audio.astype(np.float32), tail])

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="_conditioned.wav")
    tmp.close()
    sf.write(tmp.name, audio.astype(np.float32), file_sr, subtype="PCM_16")
    logger.debug("Conditioned reference audio: RMS->%.1f dBFS -> %s", _REF_TARGET_DBFS, tmp.name)
    return tmp.name


class F5Provider(TTSProvider):
    name = "f5"
    consumes_local_speed = True

    def __init__(
        self,
        *,
        assets_dir: Path,
        speed: float = 1.0,
        device: str = "auto",
        dtype: str = "float32",
        nfe_step: int = 16,
        cfg_strength: float = 2.0,
        sway_coef: float = -1.0,
        ref_clip_seconds: float = 0.0,
    ):
        self._assets_dir = Path(assets_dir)
        self._speed = speed
        self._device = device
        self._dtype = dtype
        self._nfe_step = nfe_step
        self._cfg_strength = cfg_strength
        self._sway_coef = sway_coef
        self._ref_clip_seconds = ref_clip_seconds
        self._model = None
        self._ref_cache: dict[str, dict] = {}

    # -- interface -------------------------------------------------------------
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
        model = self._get_model()
        ref = self._get_reference(voice_id)

        settings = voice_settings or {}
        speed = settings.get("speed", self._speed)
        speed *= emotion_map.speed_multiplier(settings.get("emotion"))

        # Short-phrase pacing: slow down tiny fragments to prevent ref leakage
        gen_text = " ".join(text.split())
        if os.environ.get("MOODSCAPE_F5_SHORT_PHRASE_PACING", "1") == "1":
            max_chars = int(os.environ.get("MOODSCAPE_F5_SHORT_PHRASE_MAX_CHARS", "12"))
            if len(gen_text.replace(" ", "")) <= max_chars:
                speed = float(os.environ.get("MOODSCAPE_F5_SHORT_PHRASE_SPEED", "0.5"))

        # Per-call nfe_step override (sleep stories use 32)
        nfe_step = settings.get("nfe_step", self._nfe_step)

        try:
            import torch

            with torch.inference_mode():
                wav, _sr, _ = model.infer(
                    ref_file=ref["audio"],
                    ref_text=ref["text"],
                    gen_text=gen_text,
                    speed=speed,
                    nfe_step=nfe_step,
                    cfg_strength=self._cfg_strength,
                    sway_sampling_coef=self._sway_coef,
                    remove_silence=False,
                )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, f"synthesis failed: {exc}") from exc

        arr = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
        arr = arr.astype(np.float32).squeeze()

        # Post-processing: trim trailing silence, then VAD
        arr = _trim_trailing_silence(arr, SAMPLE_RATE)
        arr = _apply_silero_vad(arr, SAMPLE_RATE)

        return numpy_to_segment(arr, SAMPLE_RATE)

    # -- lazy model + reference loading ----------------------------------------
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

        device = self._resolve_device(torch)
        dtype = self._dtype
        if device == "mps" and dtype == "float32":
            dtype = "float16"
            logger.info("Auto-selecting float16 for MPS device")
        if device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        logger.info("Loading F5TTS (F5TTS_v1_Base) on %s (%s)", device, dtype)
        try:
            model = F5TTS(model="F5TTS_v1_Base", device=device)
            if dtype == "float16":
                model.ema_model.to(torch.float16)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.name, f"failed to load F5 model: {exc}") from exc

        if device == "cpu":
            try:
                torch.set_num_threads(os.cpu_count() or 4)
            except Exception:  # noqa: BLE001
                pass

        self._model = model
        return model

    def _resolve_device(self, torch) -> str:
        pref = (self._device or "auto").lower()
        if pref == "cpu":
            return "cpu"
        if pref == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if pref == "mps":
            return "mps" if torch.backends.mps.is_available() else "cpu"
        # auto: CUDA > MPS > CPU
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

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

        # Clip the reference *before* Whisper so the transcript matches the
        # shorter audio. This is the dominant per-chunk F5 runtime multiplier.
        if self._ref_clip_seconds and self._ref_clip_seconds > 0:
            ref_audio = _clip_audio_file(ref_audio, self._ref_clip_seconds)

        try:
            from f5_tts.infer.utils_infer import preprocess_ref_audio_text

            # Pass empty string to let Whisper transcribe the clipped audio,
            # ensuring ref_text matches exactly what F5 internally uses.
            proc_audio, proc_text = preprocess_ref_audio_text(
                ref_audio, "",
                show_info=lambda msg: logger.debug("F5 preprocess: %s", msg),
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.name, f"failed to preprocess reference {slug!r}: {exc}"
            ) from exc

        # Condition: RMS-normalize + trailing noise pad
        conditioned = _condition_reference_audio(proc_audio)

        self._ref_cache[slug] = {"audio": conditioned, "text": proc_text}
        return self._ref_cache[slug]
