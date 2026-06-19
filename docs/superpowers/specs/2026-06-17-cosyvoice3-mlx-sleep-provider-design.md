# CosyVoice3 (MLX) sleep-story provider with Instruct Mode

**Date:** 2026-06-17 · **Status:** Implemented

## Problem

Three deep-research reports proposed building a local Apple-Silicon sleep-story
generator. Synthesized against this codebase, the app already implements most of
their recommendations: per-provider chunking, constant-memory disk stitching, EBU
R128 mastering, gentle EQ/compression/fades, ambient beds, and zero-shot voice
cloning (F5). The one genuine **sleep-quality** gap is the TTS model itself: F5
and Kokoro clone *timbre* but carry the reference clip's *energy/delivery* into
the output, so a calm, hypnotic narration isn't guaranteed across a 30–90 min
story, and autoregressive-style models can drift over long outputs.

The reports disagreed on the exact model (VibeVoice+NeuTTS / Qwen3-TTS-MLX /
CosyVoice3-MLX). The best-grounded, most sleep-specific recommendation is
**CosyVoice3-0.5B (MLX)**: a flow-matching DiT model (more drift-stable than
autoregressive) whose **Instruct Mode** decouples the cloned *timbre* from the
*delivery* — you clone a voice and *separately* instruct it to "speak slowly and
calmly," so the calm holds regardless of the reference clip.

## Decisions

- **Add CosyVoice3 as a new provider, additive via the registry.** F5, Kokoro,
  and ElevenLabs are untouched. (User decision: prioritize sleep TTS quality; add
  MLX *alongside* torch, not a full migration.)
- **Opt-in, not the default sleep provider.** Kokoro stays the default until
  `scripts/bench_cosyvoice.py` confirms an A/B win vs F5. Calm delivery via
  Instruct must be validated, not assumed.
- **Pacing rides Instruct, not numeric speed** (`consumes_local_speed = False`,
  `accepts_instruct = True`). This plays to the model's strength and avoids
  time-stretch artifacts. The UI notes the speed slider is ignored for CosyVoice3.
- **Reuse the F5 clone-voice assets.** CosyVoice3 needs the same reference
  audio + exact transcript pairs. `f5_voice_registry` was renamed to the generic
  `reference_voice_registry` (shared), with `f5_voice_registry` kept as a thin
  re-export for back-compat.
- **Apple-Silicon-only, optional extra.** `mlx-audio-plus` (imports as
  `mlx_audio`) goes under a `mlx` extra (`uv sync --extra mlx`) so non-Mac/CI
  installs and `uv run pytest` (fakes) stay clean. The heavy import is lazy
  (synthesis only); failures degrade to `ProviderError` + a per-provider error in
  `/api/voices`.

## Feasibility (verified, not assumed)

- Package `mlx-audio-plus==0.1.8`, `requires_python >=3.10` (project is 3.13);
  its `transformers <5.0,>=4.49` is compatible with the project's `>=4.55,<4.58`.
- API: `from mlx_audio.tts.generate import generate_audio` — returns `None`,
  writes files. **Installed `mlx-audio-plus==0.1.8`** writes to
  `{file_prefix}.{audio_format}` relative to CWD (no `output_path`/`seed`
  params), so we set `file_prefix` to a full temp-dir path and use
  `join_audio=True` → deterministic `{prefix}.wav`, read back as an
  `AudioSegment` (24 kHz). (Designing against GitHub `main` instead of the pinned
  release caused the first integration bug — see the post-implementation fix.)
- Model `mlx-community/Fun-CosyVoice3-0.5B-2512-4bit` (~1.1 GB), loaded once via
  `mlx_audio.tts.utils.load_model` and cached across chunks.
- **Mode selection:** `CosyVoice3.generate` branches zero-shot (`ref_text`)
  *before* instruct (`instruct_text`); passing both runs zero-shot and drops the
  directive. So instruct mode passes `instruct_text` and **omits** `ref_text`
  (Whisper is skipped when instructing); zero-shot passes `ref_text` (which also
  skips the ~1.5 GB Whisper auto-transcription). Instruct mode is keyed off
  `instruct_text`, not `instruct`.
- Reference audio ≤30 s, cleanly trimmed — matches the existing F5 layout.

## Design

- **Capability flag** `TTSProvider.accepts_instruct` (base). CosyVoice sets it.
- **`CosyVoiceProvider`** (`providers/cosyvoice_provider.py`): `list_voices` scans
  `reference_voice_registry` (no MLX import); `synthesize` lazily imports
  `mlx_audio`, resolves the reference (audio + transcript), reads `instruct` from
  `voice_settings`, calls `generate_audio(...)` to a temp dir, and returns the
  WAV as an `AudioSegment`.
- **Orchestrator** `_sleep_voice_settings` injects `{"instruct": ...}` for
  `accepts_instruct` providers — `cosyvoice_sleep_instruct`, overridable per story
  via `SleepStoryRequest.style_prompt`.
- **Config:** `cosyvoice_model`, `cosyvoice_sleep_instruct`,
  `cosyvoice_chunk_chars=300`. **Chunker:** `cosyvoice` budget 300.
- **Frontend:** CosyVoice3 in the sleep provider dropdown + a "Delivery style"
  field bound to `style_prompt`.

## Out of scope (sequenced follow-ups from the reports)

LLM script generation (e.g. Quill-v1), full MLX migration of F5/Kokoro, ASR/
speaker-drift QC over long outputs, and Pedalboard reverb/spatial DSP.

## Verification

- `uv run pytest` (fakes; green without MLX installed) — provider registration,
  `list_voices` without `mlx_audio`, instruct injection + `style_prompt` override,
  `ProviderError` on missing/non-Apple `mlx_audio`.
- `/api/voices` returns a `cosyvoice` group with the reference voices (verified).
- Sleep-story UI shows CosyVoice3 + the Delivery style field (verified in browser).
- `uv sync --extra mlx` + `scripts/bench_cosyvoice.py` on the M1 Max for the A/B
  listen that decides whether to flip the default (manual, hardware-gated).
