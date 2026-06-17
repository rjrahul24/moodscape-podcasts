# Model-specific TTS tailoring (ElevenLabs v2/v3 + F5 runtime)

**Date:** 2026-06-17 · **Status:** Implemented

## Problem

Generation was provider-agnostic to a fault: the orchestrator passed one uniform
`voice_settings` dict to every model, `text_processor` stripped tone tags the same
way for all, and nothing tailored output to (a) the selected model or (b) the
content type (podcast = conversational/expressive, sleep = calm/emotional). The
symptoms:

- **ElevenLabs** ran only `eleven_multilingual_v2`; v3's discrete stability +
  inline audio tags were unused. Sleep stories sent `voice_settings=None`, so the
  voice never narrated calmly at the model level (only the post chain did).
  Native `speed` (0.7–1.2) was never sent.
- **F5** ran `device="mps"` + `float16`, the documented cause of garbled output on
  Apple Silicon; unsupported ops bounced to CPU. ~18–20 min for 3 min of audio on
  an M1 Max, with random slurred words.

## Decisions

- **ElevenLabs model is user-selectable in the UI** (v2 vs v3) per speaker / per
  sleep story; the backend adapts settings to the choice and the content type.
- **F5 runtime is config-driven and benchmarked per host.** Default CPU + float32
  (reliable on Apple Silicon); a switch + `scripts/bench_f5.py` lets MPS be chosen
  if it wins on a given machine.
- **F5 reference transcripts are not a bug.** Multiple voices reading the same
  script legitimately share one transcript — identity comes from the audio.

## Design

- **Provider capability flags** (`TTSProvider`): `consumes_local_speed` (Kokoro,
  F5) and `has_native_speed` (ElevenLabs). The orchestrator branches on these,
  replacing the `_SPEED_AWARE` name set. This is the structural "split per model".
- **Hints ride `voice_settings`** (no signature change): `emotion`, `speed`, and —
  for ElevenLabs only — `content_type` and `model_id`. Local providers ignore the
  extra keys; ElevenLabs consumes all four so none leak into the API body.
- **`elevenlabs_provider._prepare`** resolves `(text, model_id, body)`:
  - v2: numeric profile (`EMOTION_PROFILES` for a tag, else `V2_CONTENT_BASE` per
    content type) + clamped native `speed`.
  - v3: discrete stability (Creative/Natural/Robust) + tone performed inline via
    `V3_AUDIO_TAGS`.
  - Model from `model_id`, else per-content default
    (`ELEVENLABS_PODCAST_MODEL`/`ELEVENLABS_SLEEP_MODEL`).
- **`orchestrator`**: `_podcast_voice_settings` and new `_sleep_voice_settings`
  build the dict from capability flags; sleep now sends ElevenLabs a calm profile
  + native slow speed. `text_processor`/`emotion` stay model-agnostic (v3's inline
  tag is re-formed inside the provider).
- **F5 provider**: `_resolve_device` (`auto|cpu|mps|cuda`), `F5_DTYPE` (default
  float32, fp16 opt-in), `PYTORCH_ENABLE_MPS_FALLBACK=1` for MPS,
  `torch.inference_mode()`, CPU thread count. `nfe_step` 32→16, `F5_CHUNK_CHARS`
  350→250. `scripts/bench_f5.py` for the per-host CPU-fp32 vs MPS-fp32 comparison.
- **Frontend**: `SpeakerVoice.model_id` / `SleepStoryJobRequest.model_id`;
  ElevenLabs-only v2/v3 dropdown in `SpeakerConfig` and `SleepStoryConfig`.

## Out of scope / future

- v3 expression library beyond the 5-tag mapping (e.g. authored `[laughs]` is
  already passed through to v3, but not surfaced as first-class UI).
- A real MPS/CUDA speed win for F5 beyond the per-host benchmark (ONNX/MLX
  backends).

## Verification

- `uv run pytest` — provider v2/v3 resolution, v3 inline-tag injection, sleep-EL
  calm settings, F5 device/dtype wiring, capability-flag gating (99 passing).
- `scripts/bench_f5.py` for runtime; end-to-end via `./dev.sh` for audible checks
  (v3 audio tags, F5 clean/fast render, calm sleep narration on ElevenLabs).
