# Changelog

Append-only log of notable changes and the decisions behind them. Newest first.
Every change should add an entry (see `CLAUDE.md` → Documentation discipline).

## 2026-06-15 — Add Kokoro + F5 TTS providers

Added two local TTS models behind the existing provider abstraction so a user
can pick **any of the three models per speaker** and mix them in one episode.

- **New providers** (core text→audio path only — no meditation processing copied
  from the source repo):
  - **Kokoro** (`kokoro_provider.py`): 11 static built-in voices; lazy
    `KPipeline` (CPU on Apple Silicon, a second pipeline for British voices).
    Validated end-to-end (real 24kHz render).
  - **F5** (`f5_provider.py` + `f5_voice_registry.py`): zero-shot voice cloning;
    voices discovered from `assets/speakers/reference_audio/*.wav` +
    `reference_text/*.txt` pairs; lazy `F5TTS` model with cached per-voice
    reference preprocessing.
- **Interface change:** `TTSProvider.synthesize` now returns a pydub
  `AudioSegment` (was raw `bytes`), unifying cloud encoded-bytes with local numpy
  output. Added `stitcher.numpy_to_segment` and sample-rate normalization in
  `stitch` (default target 44.1kHz) so mixed-provider episodes concatenate cleanly.
- **Voices API** is now provider-grouped and resilient (`list[ProviderVoices]`):
  one provider failing (no ElevenLabs key, empty F5 assets, missing ML lib) no
  longer breaks the others.
- **Frontend:** each speaker row gained a **model** dropdown + a voice dropdown
  filtered to the chosen provider; provider errors show inline.
- **Decisions:**
  - Install all three models by default (no optional extra) — user wants every
    model available at launch.
  - **Pin backend to Python 3.13.** Kokoro/F5 pull in `spacy`, which has no
    cp314 wheels; 3.13 has wheels for the whole stack (torch 2.12, spacy 3.8).
    `requires-python` set to `>=3.11,<3.14`.
  - Heavy ML imports kept lazy (registration + `list_voices` never import torch).
  - F5 references require a matching `.txt` transcript (no Whisper fallback);
    assets mirror the source meditation repo's two-folder layout.
  - Local models default to speed 1.0 (normal podcast pace, not meditation 0.90).
- **Docs:** added `docs/ARCHITECTURE.md`, this changelog, and `CLAUDE.md` with a
  mandatory documentation-discipline rule for future sessions.
- Tests: 26 → 39 (local providers via injected fake modules; mixed-rate
  stitching; resilient grouped voices). README updated for the three models +
  assets.

## 2026-06-15 — Initial scaffold

Greenfield FastAPI + React monorepo to turn a multi-speaker script into a
stitched podcast episode via pluggable TTS providers.

- **Decisions:** full-stack web app; TTS-only scope (script in → audio out);
  FastAPI + React/Vite stack; synchronous generation, minimal persistence
  (files on disk, no DB), single-user, no auth; provider abstraction with
  ElevenLabs as the first implementation; output = lossless-stitched WAV master
  + optional MP3 320 (MP4 deliberately skipped); `audioop-lts` added for
  pydub on Python 3.13+.
- Backend: `TTSProvider` + registry, script parser, audio engine, pydub/ffmpeg
  stitcher, synchronous generate + download API. Frontend: speaker config, voice
  dropdowns, script input, player/download. 26 passing tests.
