# Changelog

Append-only log of notable changes and the decisions behind them. Newest first.
Every change should add an entry (see `CLAUDE.md` → Documentation discipline).

## 2026-06-15 — Async pipeline overhaul + Sleep Stories content type

Two coordinated changes: a model-agnostic architecture overhaul that fixes
long-content generation, and a net-new **Sleep Stories** content type.

### Architecture overhaul (both content types)

- **Async jobs.** New `POST /api/jobs` (discriminated `podcast`/`sleep_story`
  body) returns a `job_id` immediately; work runs in a single-slot thread pool
  (`max_workers=1`) off the event loop. Progress via SSE
  (`GET /api/jobs/{id}/events`, `sse-starlette`) and polling
  (`GET /api/jobs/{id}`). The legacy synchronous `POST /api/generate` stays as a
  thin adapter over the new orchestrator, so existing callers/tests are unaffected.
- **Per-provider chunking** (`core/chunker.py`): sentence-aware, character-based
  budgets (Kokoro 400 / F5 350 / ElevenLabs 2400) keep each call under Kokoro's
  510 phoneme-token cap and F5's ~30s/pass. Pure module, no ML imports.
- **Disk-based stitching** (`core/ffmpeg_stitch.py`): each chunk is written to a
  temp WAV and concatenated with the ffmpeg concat demuxer — constant memory, no
  `MemoryError` on 30–45 min output. Replaces in-memory pydub concat on the async
  path (`stitcher.stitch` retained for the legacy path + its tests).
- **`engine.generate` is now a shim** over `core/orchestrator.run`, the single
  generation engine for both content types.

### Sleep Stories (single-speaker, plain prose)

- New `SleepStoryRequest`: paste plain prose (no `[Speaker]` tags), one
  provider + voice, with `speed` (default 0.85), inter-sentence `pause_ms`
  (default 900), and an optional ambient bed.
- **Calming post-processing** (`core/sleep_post.py`, ffmpeg): gentle compression
  → low-pass roll-off → EBU R128 `loudnorm` → fade in/out → **44.1 kHz stereo**.
- **Ambient beds** (`core/ambient.py` + `storage/ambient_registry.py`): files in
  `assets/ambient/*.{wav,mp3}` are looped/trimmed to the story length, pulled
  ~22 dB under the voice, faded, and `amix`ed under the narration. Listed at
  `GET /api/ambient`.
- **Per-job speed** rides the existing `voice_settings` dict — `KokoroProvider`
  and `F5Provider` read `voice_settings["speed"]` (one-line change each), so the
  `TTSProvider` signature is unchanged and ElevenLabs never receives the key.

### Frontend

- Content-type toggle (`ContentTypeSelector`); Sleep config (`SleepStoryConfig`:
  single voice, speed/pause sliders, ambient picker, prose textarea with
  word-count/duration hint); live `ProgressBar` driven by the SSE stream
  (`api/jobs.ts`). Podcasts reuse `SpeakerConfig`/`ScriptInput` and now also run
  through the async job flow.

### Decisions / trade-offs

- **Sanctioned exception to "no meditation processing."** The rule still holds
  for podcasts; the calming treatment applies to sleep stories only. CLAUDE.md
  updated to record the boundary.
- **No model-lineup changes** (no Chatterbox, no F5 demotion); Kokoro's
  CPU-on-Apple-Silicon default is kept and documented.
- **Char-based chunk budgets** instead of "tokens": Kokoro's limit is phonemized
  tokens, which track characters, not BPE tokens — char budgets are safe and need
  no tokenizer dependency.
- **Concurrency capped at 1** so two heavy local models never co-load (OOM guard);
  parallel jobs are serialized.
- **In-memory job store** (no DB): single-user local app; jobs clear on restart,
  output files persist for download.

### Docs & testing

- Added `sse-starlette`; new sleep/chunking/ambient config in `config.py` +
  `.env.example`; `assets/ambient/` scaffold + README.
- Tests: 39 → 77 (chunker, job store, orchestrator podcast+sleep, jobs API incl.
  SSE, ambient registry, sleep filtergraph, per-job speed threading). No model
  downloads; real-ffmpeg tests gated on ffmpeg presence.
- Updated `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, and added a design spec.

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
