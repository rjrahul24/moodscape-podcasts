# Async pipeline overhaul + Sleep Stories — design

Date: 2026-06-15

## Context

Moodscape rendered podcasts synchronously: `POST /api/generate` parsed a script,
called `provider.synthesize()` per turn, stitched in memory with pydub (mono),
and exported. That breaks on long content — HTTP/proxy timeouts on multi-minute
jobs, Kokoro's hard 510 phoneme-token cap (rushed/garbled audio with no
chunking), F5 degrading past ~30s, and pydub `MemoryError` on 30–45 min stereo
WAV held in RAM.

This change does two things:

1. **A model-agnostic architecture overhaul** (both content types): async jobs +
   progress, per-provider text chunking, and disk-based ffmpeg stitching.
2. **A net-new Sleep Stories content type** — single-speaker plain prose rendered
   with a calming, sleep-optimized master (slower pace, inter-sentence pauses,
   loudness normalization, gentle EQ/compression, fades, optional ambient bed),
   exported 44.1 kHz stereo.

The defining constraint: the `TTSProvider` contract (lazy ML imports, returns an
`AudioSegment`) must not change in signature, and the "no meditation processing"
rule must remain intact **for podcasts**. The calming treatment is a sanctioned
exception **scoped to sleep stories only**.

## Decisions

- **Async job model.** `POST /api/jobs` takes a discriminated body
  (`kind: "podcast" | "sleep_story"`), returns `{job_id}` immediately, and runs
  the work in a single-slot thread pool (`max_workers=1`) off the event loop.
  Progress via SSE (`GET /api/jobs/{id}/events`, `sse-starlette`) and polling
  (`GET /api/jobs/{id}`). In-memory `JobStore` (no DB; single-user local app).
- **Concurrency capped at 1** so two heavy local models never co-load (OOM guard).
- **Per-provider chunking** (`core/chunker.py`): sentence-aware, **character**
  budgets (Kokoro 400 / F5 350 / ElevenLabs 2400). Char budgets — not "tokens" —
  because Kokoro's limit is phonemized tokens (which track characters), avoiding a
  tokenizer dependency. Pure module, no provider/ML imports.
- **Disk-based stitching** (`core/ffmpeg_stitch.py`): each chunk → normalized WAV
  on disk → `ffmpeg -f concat` → master (constant memory). The legacy in-memory
  `stitcher.stitch` is retained for `POST /api/generate` and its tests.
- **`engine.generate` becomes a shim** over `core/orchestrator.run`, the single
  generation engine for both kinds.
- **Per-job speed via `voice_settings`.** Sleep passes
  `voice_settings={"speed": …}`; `KokoroProvider`/`F5Provider` read it (one-line
  change each). The orchestrator injects `speed` only for local providers, so the
  ElevenLabs request body is untouched. Chunking + inter-sentence pauses live in
  the orchestrator, never in providers.
- **Sleep input is plain prose** — no `[Speaker]` parsing, one provider + voice.
- **Sleep output is 44.1 kHz stereo** with a sanctioned ffmpeg master chain
  (`core/sleep_post.py`) and an optional ambient bed (`core/ambient.py` +
  `storage/ambient_registry.py`, files in `assets/ambient/*.{wav,mp3}`).
- **No model-lineup changes** (no Chatterbox, no F5 demotion); Kokoro stays
  CPU-on-Apple-Silicon by default.

## Design highlights

### Async data flow (both kinds)

`POST /api/jobs` → create `Job`, return `{job_id}` (202) → executor runs
`orchestrator.run(request, settings, store.reporter(job_id), job_id=...)`. The
worker reports `chunks_done/chunks_total` per chunk; SSE emits `progress` frames
and a terminal `done`/`error` frame; the result is a `GenerateResult` so
`GET /api/download/...` is unchanged.

### Orchestrator

- **Podcast:** parse → validate speakers → per-turn `chunk_turn` (tagged with the
  speaker's provider/voice) → synthesize each chunk to disk → insert `gap_ms`
  silence between turns → ffmpeg concat → export (matches prior behavior; no
  processing).
- **Sleep:** `chunk_prose` → synthesize with `{"speed": …}` → insert `pause_ms`
  silence between sentences → concat → `sleep_post.process`
  (`acompressor` → `lowpass` → `loudnorm` EBU R128 → `afade` in/out → 44.1 kHz
  stereo) → optional `ambient.mix` (loop/trim/gain/fade + `amix`) → export WAV+MP3.

### Frontend

Content-type toggle (`ContentTypeSelector`); `SleepStoryConfig` (single voice,
speed/pause sliders, ambient picker, prose textarea with word-count/duration
hint); `ProgressBar` driven by the SSE stream (`api/jobs.ts` `createJob`+`runJob`).
Podcasts reuse `SpeakerConfig`/`ScriptInput` and also run through the job flow.

## Verification

- **pytest (39 → 77, no model downloads):** chunker, job store, orchestrator
  (podcast + sleep, incl. per-job speed threading via `FakeProvider`), jobs API
  (`POST /api/jobs` → poll to `succeeded`, an SSE read, download round-trip),
  ambient registry, sleep filtergraph construction, plus the existing suites.
  Real-ffmpeg tests gated on `shutil.which("ffmpeg")`.
- **Frontend:** `tsc --noEmit` + `vite build` clean.
- **Manual end-to-end:** podcast job shows live progress, downloads correct
  unprocessed WAV/MP3; long sleep story (~3,000 words) on `af_heart` at 0.85 with
  a pause + ambient bed completes without timeout/`MemoryError` and yields a
  loudness-normalized 44.1 kHz stereo master with the bed mixed low.

## Out of scope

Model-lineup changes (Chatterbox, F5 demotion), database/persistent jobs,
multi-user/auth, MP4/video, script generation, and any calming processing on
podcasts.
