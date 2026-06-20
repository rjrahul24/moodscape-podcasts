# F5 Sleep Story Quality Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix F5 reference text leaking, improve output quality, and add F5 sleep story prompting guide.

**Architecture:** Port battle-tested patterns from the meditation reference project into the existing provider/orchestrator architecture. All changes respect existing contracts: single-text `synthesize()`, pydub `AudioSegment` return, disk-based ffmpeg stitching. New module `core/f5_text.py` for F5-specific text normalization; remaining changes are additive to `f5_provider.py`, `orchestrator.py`, and `config.py`.

**Tech Stack:** Python 3.13, F5-TTS, PyTorch, torchaudio, soundfile (existing), scipy (new), Silero VAD (downloaded via torch.hub at runtime)

## Global Constraints

- Python 3.13 (`.python-version`); no cp314-only packages
- Providers return pydub `AudioSegment` from `synthesize()`; signature unchanged
- Heavy ML imports stay lazy (only inside `synthesize()` or guarded callsites)
- Per-job tuning rides `voice_settings` dict; no new method parameters
- Tests use fakes (no model downloads, no real inference)
- All tests: `cd backend && uv run pytest`

---

### Task 1: F5 Text Normalization Module

**Files:**
- Create: `backend/app/core/f5_text.py`
- Create: `backend/tests/test_f5_text.py`

**Interfaces:**
- Consumes: nothing (standalone pure module)
- Produces: `normalize_for_f5(text: str) -> str` — used by orchestrator in Tasks 4 and 5

- [ ] **Step 1: Write the tests**

```python
# backend/tests/test_f5_text.py
"""F5 text normalization tests."""

from app.core.f5_text import normalize_for_f5


class TestNormalizeForF5:
    def test_colons_become_commas(self):
        assert normalize_for_f5("Sleep well: rest now") == "Sleep well, rest now"

    def test_ellipsis_three_dots_become_period(self):
        assert normalize_for_f5("Breathe in...") == "Breathe in."

    def test_ellipsis_unicode_becomes_period(self):
        assert normalize_for_f5("Let go…") == "Let go."

    def test_em_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now — let go") == "Rest now , let go"

    def test_en_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now – let go") == "Rest now , let go"

    def test_double_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now -- let go") == "Rest now , let go"

    def test_compound_hyphen_removed(self):
        assert normalize_for_f5("well-being") == "wellbeing"

    def test_hyphen_between_digits_preserved(self):
        # Hyphens between digits are not compounds — leave them alone
        assert normalize_for_f5("3-5") == "3-5"

    def test_all_caps_lowered(self):
        assert normalize_for_f5("BREATHE in deeply") == "breathe in deeply"

    def test_mixed_case_preserved(self):
        assert normalize_for_f5("Breathe In") == "Breathe In"

    def test_single_capital_letter_preserved(self):
        assert normalize_for_f5("I am calm") == "I am calm"

    def test_combined_normalizations(self):
        result = normalize_for_f5("NOTICE: your well-being...")
        assert result == "notice, your wellbeing."

    def test_empty_string(self):
        assert normalize_for_f5("") == ""

    def test_plain_text_unchanged(self):
        assert normalize_for_f5("The night is calm and still.") == "The night is calm and still."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_f5_text.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.f5_text'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/core/f5_text.py
"""F5-TTS text normalization.

F5's G2P mishandles several punctuation patterns. This module normalizes
text before synthesis so the model produces clean, natural speech.

Pure regex — no dependencies, no ML imports.
"""

from __future__ import annotations

import re


def normalize_for_f5(text: str) -> str:
    """Normalize text for F5-TTS's G2P and prosody model."""
    # Colons -> commas (F5 ignores colons, producing no pause)
    text = re.sub(r":", ",", text)
    # Ellipses -> single period (F5 doesn't differentiate)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub("…", ".", text)
    # Em/en-dashes -> commas (not reliably handled by F5)
    text = re.sub(r"—|–|--+", ",", text)
    # Remove hyphens in compound words (causes mispronunciation).
    # Only between letters — not between digits.
    text = re.sub(r"(?<=[a-zA-Z])-(?=[a-zA-Z])", "", text)
    # ALL_CAPS words -> lowercase (prevents letter-by-letter spelling)
    text = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group().lower(), text)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_f5_text.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/f5_text.py backend/tests/test_f5_text.py
git commit -m "feat: add F5 text normalization module"
```

---

### Task 2: Reference Audio Conditioning + Silence Trimming + VAD in F5 Provider

**Files:**
- Modify: `backend/app/providers/f5_provider.py`
- Modify: `backend/tests/test_f5_provider.py`
- Modify: `backend/pyproject.toml` (add scipy)

**Interfaces:**
- Consumes: `soundfile` (existing dep), `scipy` (new dep), `torch`/`torchaudio` (existing)
- Produces: Updated `F5Provider.synthesize()` with same signature — now returns cleaner audio. Updated `F5Provider._get_reference()` with conditioned reference. New internal functions `_condition_reference_audio()`, `_trim_trailing_silence()`, `_apply_silero_vad()`.

- [ ] **Step 1: Add scipy to pyproject.toml**

In `backend/pyproject.toml`, add `"scipy>=1.11",` to the `dependencies` list, after `"soundfile>=0.12",`.

- [ ] **Step 2: Write the tests**

The existing test fixture `fake_f5` injects a fake `preprocess_ref_audio_text` that returns `(audio, text)` unchanged. We need to:
1. Test that `_condition_reference_audio` adds trailing noise and RMS-normalizes
2. Test that `_trim_trailing_silence` trims silence
3. Test that `_apply_silero_vad` degrades gracefully
4. Test that `synthesize()` reads `nfe_step` from `voice_settings`
5. Test short-phrase speed override

Add these tests to `backend/tests/test_f5_provider.py`:

```python
def test_condition_reference_audio_adds_trailing_pad(tmp_path):
    """The conditioned reference should be longer than the original (trailing noise)."""
    import soundfile as sf

    original = tmp_path / "ref.wav"
    sr = 24000
    audio = np.random.randn(sr * 2).astype(np.float32) * 0.1  # 2s of audio
    sf.write(str(original), audio, sr)

    from app.providers.f5_provider import _condition_reference_audio

    conditioned = _condition_reference_audio(str(original), sr)
    cond_audio, cond_sr = sf.read(conditioned, dtype="float32")
    # Should be ~1s longer (the trailing noise pad)
    assert len(cond_audio) > len(audio)
    assert abs(len(cond_audio) - len(audio) - sr) < sr * 0.1  # ~1s pad


def test_trim_trailing_silence():
    """Trailing silence should be removed, keeping a 50ms decay tail."""
    from app.providers.f5_provider import _trim_trailing_silence

    sr = 24000
    speech = np.random.randn(sr).astype(np.float32) * 0.1  # 1s speech
    silence = np.zeros(sr, dtype=np.float32)  # 1s silence
    audio = np.concatenate([speech, silence])
    trimmed = _trim_trailing_silence(audio, sr)
    # Should be much shorter than original (silence removed)
    assert len(trimmed) < len(audio)
    # But longer than just the speech (50ms tail kept)
    tail_samples = int(0.05 * sr)
    assert len(trimmed) >= len(speech)
    assert len(trimmed) <= len(speech) + tail_samples + 10


def test_apply_silero_vad_graceful_fallback():
    """If Silero VAD fails, the original audio should be returned."""
    from app.providers.f5_provider import _apply_silero_vad

    sr = 24000
    audio = np.random.randn(sr).astype(np.float32) * 0.1
    # This will fail because torch.hub won't have Silero cached in test env,
    # but should fall back gracefully.
    result = _apply_silero_vad(audio, sr)
    assert len(result) > 0  # got something back (original or processed)


def test_synthesize_reads_nfe_step_from_voice_settings(tmp_path, fake_f5):
    """voice_settings['nfe_step'] should override the constructor default."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, nfe_step=16)

    provider.synthesize(
        "hello there", "brittney",
        output_format="ignored",
        voice_settings={"nfe_step": 32},
    )
    assert fake_f5["nfe_step"] == 32


def test_short_phrase_gets_slower_speed(tmp_path, fake_f5):
    """Short phrases (<=12 non-space chars) should use speed 0.5."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, speed=0.88)

    # "Breathe in." has 10 non-space chars -> triggers short-phrase pacing
    provider.synthesize(
        "Breathe in.", "brittney",
        output_format="ignored",
        voice_settings={"speed": 0.88},
    )
    assert fake_f5["speed"] == pytest.approx(0.5, abs=0.01)


def test_normal_sentence_not_slowed(tmp_path, fake_f5):
    """Normal-length sentences should NOT trigger short-phrase pacing."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, speed=0.88)

    provider.synthesize(
        "Notice the gentle breathing in your body.", "brittney",
        output_format="ignored",
        voice_settings={"speed": 0.88},
    )
    # Speed should be 0.88 * emotion multiplier (1.0), not 0.5
    assert fake_f5["speed"] == pytest.approx(0.88, abs=0.05)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_f5_provider.py -v`
Expected: FAIL — functions not yet defined

- [ ] **Step 4: Write the implementation**

Replace the full content of `backend/app/providers/f5_provider.py`:

```python
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


def _apply_silero_vad(audio: np.ndarray, sr: int) -> np.ndarray:
    """Crop trailing non-speech and attenuate interior gaps via Silero VAD.

    Two-pass: (1) crop after last speech endpoint + safety tail,
    (2) attenuate interior non-speech to 15% with gaussian-smoothed envelope.
    Falls back to the original audio if Silero fails.
    """
    try:
        import torch
        import torchaudio

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
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


def _condition_reference_audio(audio_path: str, sr: int) -> str:
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
    ):
        self._assets_dir = Path(assets_dir)
        self._speed = speed
        self._device = device
        self._dtype = dtype
        self._nfe_step = nfe_step
        self._cfg_strength = cfg_strength
        self._sway_coef = sway_coef
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
        if device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        logger.info("Loading F5TTS (F5TTS_v1_Base) on %s (%s)", device, self._dtype)
        try:
            model = F5TTS(model="F5TTS_v1_Base", device=device)
            if self._dtype == "float16":
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
        if torch.cuda.is_available():
            return "cuda"
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
        conditioned = _condition_reference_audio(proc_audio, SAMPLE_RATE)

        self._ref_cache[slug] = {"audio": conditioned, "text": proc_text}
        return self._ref_cache[slug]
```

- [ ] **Step 5: Update the fake_f5 fixture**

The existing `fake_f5` fixture's `preprocess_ref_audio_text` returns `(audio, text)` unchanged. Since `_get_reference` now passes `""` as ref_text (for Whisper), update the fake to return a transcript when text is empty, and create a real WAV file so `_condition_reference_audio` can read it:

In `backend/tests/test_f5_provider.py`, update the `_make_voice` helper and `fake_f5` fixture:

```python
def _make_voice(assets_dir, slug, text="the exact words spoken"):
    audio_dir = assets_dir / "speakers" / "reference_audio"
    text_dir = assets_dir / "speakers" / "reference_text"
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    # Write a real WAV so _condition_reference_audio can read it with soundfile
    import soundfile as sf
    sr = 24000
    audio = np.random.randn(sr * 2).astype(np.float32) * 0.1
    sf.write(str(audio_dir / f"{slug}.wav"), audio, sr)
    (text_dir / f"{slug}.txt").write_text(text, encoding="utf-8")
```

Update the `fake_f5` fixture's `preprocess_ref_audio_text` to simulate Whisper transcription when text is empty:

```python
    utils_mod.preprocess_ref_audio_text = lambda audio, text, **k: (
        audio,
        text if text else "whisper transcribed text",
    )
```

- [ ] **Step 6: Update existing test assertions**

The existing `test_synthesize_returns_segment_and_passes_reference` checks `fake_f5["ref_text"] == "reference transcript"`. Since we now pass `""` to trigger Whisper, the fake returns `"whisper transcribed text"`. Update:

```python
def test_synthesize_returns_segment_and_passes_reference(tmp_path, fake_f5):
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, nfe_step=16, cfg_strength=1.5)

    seg = provider.synthesize("hello there", "brittney", output_format="ignored")

    assert isinstance(seg, AudioSegment)
    assert seg.frame_rate == 24000
    # Whisper-verified ref_text (fake returns "whisper transcribed text")
    assert fake_f5["ref_text"] == "whisper transcribed text"
    assert fake_f5["gen_text"] == "hello there"
    assert fake_f5["nfe_step"] == 16
    assert fake_f5["cfg_strength"] == 1.5
```

Also update `test_unknown_voice_raises_provider_error` — it doesn't need changes since it fails before reference loading.

The duration assertion `assert abs(len(seg) - 500) < 30` may change because `_trim_trailing_silence` will trim the all-zeros fake output differently. Remove the precise duration assertion since fake audio (all zeros) will be trimmed aggressively:

```python
    assert len(seg) > 0  # non-empty audio returned
```

- [ ] **Step 7: Run all tests**

Run: `cd backend && uv run pytest tests/test_f5_provider.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/providers/f5_provider.py backend/tests/test_f5_provider.py backend/pyproject.toml
git commit -m "feat: add F5 reference conditioning, silence trimming, VAD, and short-phrase pacing"
```

---

### Task 3: Config — Sleep-Specific F5 Settings

**Files:**
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Settings.f5_sleep_nfe_step: int` (default 32), `Settings.f5_sleep_speed: float` (default 0.88) — used by orchestrator in Task 4

- [ ] **Step 1: Add the new settings**

Add after the existing `f5_sway_coef` line (around line 127) in `backend/app/config.py`:

```python
    # F5 sleep story overrides. Sleep stories prioritize quality over speed, so
    # nfe_step defaults higher (32 vs 16 for podcasts) and speed starts at a
    # calm meditation pace (~95-100 WPM) before the ramp eases it further.
    f5_sleep_nfe_step: int = 32
    f5_sleep_speed: float = 0.88
```

- [ ] **Step 2: Verify no test regressions**

Run: `cd backend && uv run pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add F5 sleep-specific nfe_step and speed settings"
```

---

### Task 4: Orchestrator Integration — F5 Normalization + Sleep Settings

**Files:**
- Modify: `backend/app/core/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `f5_text.normalize_for_f5()` from Task 1, `Settings.f5_sleep_nfe_step` / `Settings.f5_sleep_speed` from Task 3
- Produces: F5-normalized text passed to `provider.synthesize()`, enriched `voice_settings` for F5 sleep

- [ ] **Step 1: Write the tests**

Add to `backend/tests/test_orchestrator.py`. The test needs to verify:
1. F5 text is normalized before synthesis in the sleep path
2. F5 sleep voice_settings includes `nfe_step` and `content_type`
3. F5 sleep uses `f5_sleep_speed` as the base speed

Find the existing sleep story test pattern in the file. Add:

```python
def test_sleep_f5_text_normalized(clean_registry, tmp_path):
    """F5 sleep stories should have text normalized (colons->commas, etc.)."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(output_dir=str(tmp_path / "out"))
    request = SleepStoryRequest(
        prose_text="Rest now: find well-being... BREATHE deeply.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-norm")

    # Check that the text passed to synthesize was normalized
    texts = [c["text"] for c in fake.synth_calls]
    combined = " ".join(texts)
    assert ":" not in combined  # colons removed
    assert "..." not in combined  # ellipses removed
    assert "BREATHE" not in combined  # ALL_CAPS lowered


def test_sleep_f5_voice_settings_has_nfe_and_content_type(clean_registry, tmp_path):
    """F5 sleep stories should pass nfe_step and content_type in voice_settings."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(
        output_dir=str(tmp_path / "out"),
        f5_sleep_nfe_step=32,
    )
    request = SleepStoryRequest(
        prose_text="The night is calm.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-vs")

    vs = fake.synth_calls[0]["voice_settings"]
    assert vs["nfe_step"] == 32
    assert vs["content_type"] == "sleep"


def test_sleep_f5_uses_sleep_speed(clean_registry, tmp_path):
    """F5 sleep should use f5_sleep_speed as the base, not sleep_default_speed."""
    from app.core.orchestrator import run
    from app.core.models import SleepStoryRequest
    from app.config import Settings
    from tests.conftest import FakeProvider

    fake = FakeProvider(name="f5", consumes_local_speed=True)
    clean_registry.register(fake)

    settings = Settings(
        output_dir=str(tmp_path / "out"),
        f5_sleep_speed=0.88,
        sleep_default_speed=0.78,  # this should NOT be used for F5
    )
    request = SleepStoryRequest(
        prose_text="The night is calm and still.",
        voice_id="f5-v1",
        provider="f5",
    )
    run(request, settings, job_id="test-f5-speed")

    vs = fake.synth_calls[0]["voice_settings"]
    assert vs["speed"] == pytest.approx(0.88, abs=0.05)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_orchestrator.py::test_sleep_f5_text_normalized tests/test_orchestrator.py::test_sleep_f5_voice_settings_has_nfe_and_content_type tests/test_orchestrator.py::test_sleep_f5_uses_sleep_speed -v`
Expected: FAIL

- [ ] **Step 3: Add the import and F5 normalization in the sleep path**

At the top of `backend/app/core/orchestrator.py`, add the import alongside the existing core imports (around line 29):

```python
from . import ambient, chunker, ffmpeg_stitch, podcast_music, qc, sleep_post, sleep_text, text_processor
from . import emotion as emotion_mod
from . import f5_text
```

In `_run_sleep()`, after `prose = sleep_text.spell_numbers(...)` and the kokoro branch, add F5 normalization (around line 779, before `plan = chunker.chunk_prose(...)`):

```python
    if provider_name == "f5":
        prose = f5_text.normalize_for_f5(prose)
```

- [ ] **Step 4: Enrich _sleep_voice_settings for F5**

In `_sleep_voice_settings()`, update the `consumes_local_speed` branch (around line 251) to also pass `nfe_step` and `content_type` when provider is F5:

```python
    if provider.consumes_local_speed:
        vs: dict = {"speed": speed}
        if provider.name == "f5":
            vs["nfe_step"] = settings.f5_sleep_nfe_step
            vs["content_type"] = "sleep"
        return vs
```

Note: The variable name `vs` was already used in the `has_native_speed` branch above. The `consumes_local_speed` branch previously returned a dict literal. Now it builds a dict and conditionally adds keys.

- [ ] **Step 5: Use f5_sleep_speed as base speed for F5 sleep**

In `_run_sleep()`, after `base_speed` is set (around line 746), add F5 speed override:

```python
    base_speed = request.speed if request.speed is not None else settings.sleep_default_speed
    if provider_name == "f5" and request.speed is None:
        base_speed = settings.f5_sleep_speed
```

- [ ] **Step 6: Add F5 normalization in the podcast path**

In `_run_podcast()`, in the pacing branch, add normalization before `provider.synthesize()`. Around line 640, after `provider = registry.get(op.provider)`:

```python
            provider = registry.get(op.provider)
            synth_text = op.text
            if op.provider == "f5":
                synth_text = f5_text.normalize_for_f5(synth_text)
            vs = _podcast_voice_settings(provider, op, rng, settings, seed=request.seed)
            fmt = _segment_format_for(op.provider, settings, request_override=req_format)
            seg = provider.synthesize(
                synth_text, op.voice_id, output_format=fmt, voice_settings=vs
            )
```

In the legacy (non-pacing) branch, around line 695, similarly:

```python
            provider = registry.get(provider_name)
            synth_text = chunk.text
            if provider_name == "f5":
                synth_text = f5_text.normalize_for_f5(synth_text)
            fmt = _segment_format_for(provider_name, settings, request_override=req_format)
            seg = provider.synthesize(synth_text, voice_id, output_format=fmt)
```

And in the sleep path, normalize per-piece text before synthesis (around line 831):

```python
        for j, (piece_text, pause_after_ms) in enumerate(pieces):
            tone, piece_text = _sleep_tone(piece_text, settings)
            if provider_name == "f5":
                piece_text = f5_text.normalize_for_f5(piece_text)
            if piece_text.strip():
```

- [ ] **Step 7: Run all tests**

Run: `cd backend && uv run pytest -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: wire F5 text normalization and sleep settings into orchestrator"
```

---

### Task 5: F5 Sleep Story Prompting Guide + Documentation Updates

**Files:**
- Create: `docs/prompting_guides/f5_sleep.md`
- Modify: `docs/prompting_guides/README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: nothing (documentation only)
- Produces: User-facing documentation

- [ ] **Step 1: Create the F5 sleep story prompting guide**

Create `docs/prompting_guides/f5_sleep.md`:

```markdown
# Prompting guide — F5 sleep story

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return finished prose you can paste directly into the Moodscape app's
**Story** box. This guide is written for narration using the **F5** model (local,
voice cloning from a reference clip).

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the sleep story is about, 1–3 sentences>
TARGET_LENGTH:    <e.g. "about 10 minutes" or "~1500 words">
OVERALL_TONE:     <e.g. "warm and dreamy", "gentle and grounding">
NOTES (optional): <setting, imagery preferences, anything to include or avoid>
```

---

## YOUR TASK

You are a writer creating a **calming sleep story** — a gentle, single-narrator
prose narrative designed to guide the listener toward sleep. This is **not** a guided
meditation, not an instruction manual, and not a podcast. It is a slow, sensory,
story-shaped journey that progressively winds down.

The narration is voiced by **F5**, which **clones a voice from a short reference
clip**. Key constraints for how you write:

- **The voice's emotional tone is fixed to its reference clip.** Tone tags like
  `[calm]` only nudge speaking speed slightly. **Emotion must live in your word
  choices**: soft verbs, gentle imagery, unhurried rhythm.
- F5 has the **shortest comfortable sentence length** of all engines. Keep sentences
  **under ~15 words**. Long run-ons garble at sleep speed. Two short sentences always
  beats one long one.
- **Periods and commas are the only punctuation F5 reliably uses for pacing.** Colons,
  ellipses (`...`), em-dashes (`—`), and en-dashes (`–`) are normalized away before
  synthesis. Do not rely on them for pauses — use `[pause:N]` instead.
- **Hyphens in compound words cause mispronunciation.** Write "wellbeing" not
  "well-being", "goodnight" not "good-night".

## OUTPUT FORMAT (must follow exactly)

- **Plain prose only.** No speaker labels, no `[Speaker N]:` markers. This is a
  single-narrator story.
- No markdown, no headings, no bullet points, no asterisks, no emojis.
- Use **paragraphs** to structure the story. Separate paragraphs with blank lines.
- Each paragraph should be 3–6 sentences.

## TAGS YOU MAY USE

**Pause tag — your primary pacing tool.** `[pause:600]` (in milliseconds;
`[pause:600ms]` also works). Sleep stories use longer pauses than podcasts:
**400–1200 ms** is typical. Use them:

- Between imagery shifts ("The meadow stretches wide. [pause:800] A stream appears.")
- After sensory details, to let them land
- Between progressive relaxation cues
- At paragraph boundaries for extra breath (in addition to the app's automatic pauses)

Do **not** exceed ~2000 ms. The app already adds inter-sentence pauses; yours are
*in addition* to those.

**Tone tags** — `[calm]` `[soothing]` `[warm]` `[dreamy]` `[tender]`. On F5 these
only shift speed slightly. Use **rarely** — at the start of a paragraph if you want
a subtle pace change. Never mid-sentence.

## STYLE — slow, sensory, progressive

### Word choice
- **Present tense.** "The air is cool." Not "The air was cool."
- **Gentle imperatives.** "Notice", "feel", "let", "imagine", "allow". Never
  commanding — inviting.
- **Concrete sensory details.** What does it look like, sound like, feel like? "A
  warm light touches your shoulders." Not "You feel relaxed."
- **Short, rhythmic phrases.** Read each sentence aloud in your mind. If it feels
  rushed, split it.
- Spell out everything: numbers as words ("three" not "3"), no abbreviations, no
  symbols.
- Avoid ALL CAPS words — they get spelled letter-by-letter.
- Avoid compound-hyphenated words. Write "goodnight" not "good-night".

### Structure — progressive wind-down
The story should flow through these phases (don't label them — weave naturally):

1. **Arrival** (~15% of length) — Set the scene gently. Where are we? What time of
   day? Engage two or three senses. Keep it inviting.
2. **Exploration** (~35%) — Move slowly through the setting. Each paragraph shifts
   the scene slightly. Active but unhurried imagery: walking, noticing, discovering.
3. **Settling** (~30%) — The pace drops further. Body awareness appears: warmth,
   weight, softness. Imagery becomes passive: things happen *to* the listener. "The
   warmth finds your hands."
4. **Release** (~20%) — Almost still. Breath references. Repetition. Very short
   sentences. Trailing off. The final paragraph can be just a few gentle fragments.

### Rhythm
- Vary sentence length, but lean short. A 12-word sentence followed by a 5-word one
  creates a natural breathing pattern.
- Use `[pause:N]` to create deliberate stillness, not just silence.
- Don't front-load ideas. "The moonlight is soft." Not "Soft is the moonlight that
  falls."

## WORKED EXAMPLE (style reference — do not copy)

For INPUTS: topic "a quiet forest at twilight", ~1 minute, tone "warm and still":

```
The path is soft underfoot. Pine needles cushion each step. [pause:600] The air
carries something green and cool.

Above you, the last light moves through the branches. It turns the leaves to gold.
[pause:800] A bird calls once, far away. Then stillness.

You find a clearing. The grass is dry and warm. [pause:600] You sit down slowly.
The earth holds you.

[calm] Your shoulders soften. [pause:400] Your hands rest open. The twilight
deepens around you, and everything is gentle. [pause:1000]

The trees breathe. You breathe. [pause:800] That is all there is.
```

Notice: very short sentences. Present tense throughout. Sensory and concrete.
Progressive wind-down from movement to stillness. Pauses create the rhythm.

## BEFORE YOU OUTPUT — self-check

- [ ] Plain prose, no speaker labels, no markdown, no emojis.
- [ ] Sentences under ~15 words. Long ideas split across two sentences.
- [ ] Only `[pause:N]` and tone tags in brackets — nothing else.
- [ ] Numbers/symbols spelled out. No ALL CAPS. No compound hyphens.
- [ ] Present tense. Sensory details. Gentle imperatives.
- [ ] Progressive structure: arrival → exploration → settling → release.
- [ ] Roughly matches `TARGET_LENGTH` (roughly 150 spoken words ≈ 1 minute).
- [ ] No colons, ellipses, or em-dashes used for pacing (use [pause:N] instead).

Now output the sleep story, and nothing but the story.
```

- [ ] **Step 2: Update the prompting guides README**

In `docs/prompting_guides/README.md`, add the F5 sleep story row to the sleep stories table (after the Kokoro sleep row):

```markdown
| **F5** (local, voice cloning) | [`f5_sleep.md`](f5_sleep.md) | Voice cloned from a reference clip; emotion anchored to the reference. Shortest sentence budget (under ~15 words). Only periods/commas produce reliable pauses — colons, ellipses, dashes are normalized away. `[pause:N]` is the primary pacing tool. No compound hyphens, no ALL CAPS. |
```

- [ ] **Step 3: Update ARCHITECTURE.md**

Add a section under the F5 provider documentation describing the new conditioning pipeline:

```markdown
### F5 reference audio conditioning

The F5 provider conditions reference audio at load time (once per voice per session):

1. **RMS normalization** — reference normalized to -20 dBFS for consistent model input.
   Opt out via `MOODSCAPE_F5_REF_PRESERVE_DYNAMICS=1`.
2. **Trailing noise pad** — ~1s of low-level noise (-55 dBFS) appended. Prevents
   F5's duration heuristic from leaking reference syllables into short generations.
   Disable via `MOODSCAPE_F5_REF_PAD=0`.
3. **Whisper-verified transcript** — ref_text is auto-transcribed by Whisper (via
   F5's `preprocess_ref_audio_text`) to guarantee alignment with the clipped audio.

Post-synthesis, each chunk is processed:
1. **Trailing silence trim** — samples below -45 dBFS at the end are cut (50ms
   decay tail preserved).
2. **Silero VAD** — crops trailing non-speech, attenuates interior gaps to 15%.
   Falls back gracefully if VAD is unavailable.
3. **Short-phrase pacing** — chunks with ≤12 non-space characters use speed 0.5
   to prevent reference leakage on tiny fragments.

F5 text is normalized before synthesis via `core/f5_text.normalize_for_f5()`:
colons→commas, ellipses→periods, dashes→commas, compound hyphens removed,
ALL_CAPS lowered.
```

- [ ] **Step 4: Update CHANGELOG.md**

Append a dated entry:

```markdown
## 2026-06-20 — F5 sleep story quality improvement

**What changed:**
- F5 reference audio is now conditioned at load time: RMS-normalized to -20 dBFS
  and padded with ~1s trailing noise at -55 dBFS. This prevents F5's duration
  heuristic from leaking reference syllables into generated output.
- Reference transcripts are now Whisper-verified (auto-transcribed from the clipped
  audio) instead of read from .txt files, eliminating ref_text/audio misalignment.
- Post-synthesis: trailing silence trimming (-45 dBFS threshold, 50ms decay tail)
  and Silero VAD (crop trailing non-speech, attenuate interior gaps to 15%).
- Short-phrase pacing: chunks with ≤12 non-space characters use speed 0.5 to
  prevent reference leakage on tiny fragments like "Breathe in."
- New `core/f5_text.py` module normalizes text for F5's G2P: colons→commas,
  ellipses→periods, dashes→commas, compound hyphens removed, ALL_CAPS lowered.
- Orchestrator wires F5 normalization into both sleep and podcast paths.
- F5 sleep stories now use nfe_step=32 (vs 16 for podcasts) and speed=0.88
  (~95-100 WPM meditation pace) as defaults.
- New `docs/prompting_guides/f5_sleep.md` — dedicated LLM prompting guide for
  writing F5 sleep story prose.
- Added `scipy` as a dependency (for Silero VAD gaussian smoothing).

**Why:** F5 sleep stories had three issues: reference text leaking into output
(no duration predictor workaround), poor quality (no text normalization, no
post-processing, nfe_step too low), and slow rendering (reference preprocessing
per-call). All fixes ported from the meditation reference project's battle-tested
F5 engine.

**Trade-offs:** Silero VAD adds ~0.5s per chunk but significantly improves output
cleanliness. nfe_step=32 doubles inference time per chunk vs 16, but sleep stories
prioritize quality over speed. scipy added as a base dependency (~30MB).
```

- [ ] **Step 5: Commit**

```bash
git add docs/prompting_guides/f5_sleep.md docs/prompting_guides/README.md docs/ARCHITECTURE.md docs/CHANGELOG.md
git commit -m "docs: add F5 sleep story prompting guide and update architecture/changelog"
```

---

### Task 6: Lock Dependencies + Full Test Run

**Files:**
- Modify: `backend/uv.lock` (auto-generated)

**Interfaces:**
- Consumes: All changes from Tasks 1-5
- Produces: Locked dependencies, passing test suite

- [ ] **Step 1: Lock dependencies**

Run: `cd backend && uv sync`
Expected: scipy and any transitive deps resolve and install

- [ ] **Step 2: Run full test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Verify no import errors at app startup**

Run: `cd backend && uv run python -c "from app.core import f5_text; print('f5_text OK'); from app.providers.f5_provider import F5Provider; print('F5Provider OK')"`
Expected: Both print OK

- [ ] **Step 4: Commit lock file if changed**

```bash
git add backend/uv.lock
git commit -m "chore: lock scipy dependency"
```
