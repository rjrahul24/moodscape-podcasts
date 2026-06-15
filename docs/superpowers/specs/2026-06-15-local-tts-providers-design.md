# Local TTS Providers (Kokoro + F5) — Design Spec

_Date: 2026-06-15_

## Context

Moodscape Podcasts shipped with one provider (ElevenLabs, cloud). This change
adds two **local** models — **Kokoro** (named built-in voices) and **F5**
(zero-shot voice cloning from a reference clip) — so that at launch a user can
pick **any of the three models per speaker** and mix them in one episode.

Reference implementations were studied in `moodscape-guided-meditations`
(`core/kokoro_tts`, `core/f5_tts`). That project is heavily tuned for meditation;
**only the core text→audio path was copied** — all meditation pre/post-processing
(silence padding, breath sounds, VAD, microprosody, presets, multi-phase voices)
is intentionally excluded. These are mindfulness podcasts, not meditations.

## Decisions

- Install all three models by default (torch/kokoro/f5 in backend deps).
- **Backend pinned to Python 3.13**: Kokoro/F5 pull in `spacy`, which has no
  cp314 wheels. 3.13 has wheels for the whole stack (`requires-python` =
  `>=3.11,<3.14`).
- F5 references require a matching verbatim `.txt` per `.wav` (no Whisper
  fallback). Assets mirror the source repo's two-folder layout.
- Per-speaker model selection (mix providers within an episode).

## Design

### Unified provider output: `AudioSegment`

`TTSProvider.synthesize(...)` returns a pydub `AudioSegment` instead of raw
bytes. Cloud providers decode their encoded bytes (`bytes_to_segment`); local
models convert numpy (`numpy_to_segment`). `stitch` normalizes all segments to
`Settings.target_sample_rate` (default 44100, mono) before concatenation, so a
single episode mixes providers with different native rates (ElevenLabs 44.1kHz,
locals 24kHz).

### Lazy heavy imports

Provider constructors and `list_voices()` never import torch/kokoro/f5 — only
`synthesize()` does (model cached as a lazy singleton). The app always boots, the
dropdowns populate (Kokoro static list, F5 filesystem scan), and ML failures
surface as `ProviderError` / per-provider `error` in `/api/voices`.

### Providers

- **Kokoro** (`kokoro_provider.py`): static `VOICES`; `KPipeline(lang_code,
  repo_id="hexgrad/Kokoro-82M", trf=True, device)`; CPU on Apple Silicon, second
  pipeline for British voices; numpy → segment.
- **F5** (`f5_provider.py`, `f5_voice_registry.py`): scan
  `assets/speakers/reference_audio/*.wav` + `reference_text/*.txt`; lazy
  `F5TTS(model="F5TTS_v1_Base")` + fp16; reference preprocessed once via
  `preprocess_ref_audio_text` and cached; `model.infer(...)` → numpy → segment.

### API + frontend

- `/api/voices` returns `list[ProviderVoices]` (provider, voices, error) — one
  failing provider doesn't break the rest.
- Each speaker row gets a model `<select>` + a voice `<select>` filtered to that
  provider; switching the model clears the voice; provider errors show inline.

## Verification

- pytest (39 tests), no model downloads: local providers via injected fake
  modules; numpy conversion + mixed-rate stitching; resilient grouped voices;
  generate→download round-trip. Real Kokoro render validated manually (24kHz WAV).
- Manual end-to-end: `uv sync`; add an F5 `.wav`+`.txt`; run backend + frontend;
  set three speakers to Kokoro / ElevenLabs / F5; generate one mixed-voice episode.

## Living documentation

Added `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, and `CLAUDE.md` with a
mandatory documentation-discipline rule so future sessions keep these current.

## Out of scope

Meditation processing, script generation, async/DB, auth, VibeVoice, MP4/video.
