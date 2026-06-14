# Moodscape Podcasts — Design Spec

_Date: 2026-06-15_

## Context

Greenfield project to **produce podcasts from a written script via
text-to-speech**. A user pastes a multi-speaker script, assigns a voice to each
speaker, and the app renders each line, stitches them into one episode, and
returns a downloadable audio file.

The defining requirement is **provider extensibility**: ElevenLabs is the only
provider implemented now, but new TTS providers (e.g. Microsoft VibeVoice) must
slot in by writing one class and registering it — with no changes to the script
parser, engine, API, or frontend. VibeVoice is out of scope for this build (it
is CUDA-only and impractical on the target Mac), but the abstraction is designed
so it fits cleanly later.

## Decisions

- **Form factor:** Full-stack web app (local, single-user, no auth).
- **Pipeline scope:** TTS only — script in → audio out. No script generation or
  post-production.
- **Stack:** FastAPI (Python) backend + React/TypeScript (Vite) frontend.
- **Providers:** ElevenLabs only now, behind a `TTSProvider` abstraction.
- **Granularity:** Per speaker — each speaker maps to `(provider, voice_id)`.
- **Script input:** Single textarea; `[Speaker N]: …` markers, spoken order,
  multi-line turns supported, inline provider tags passed through.
- **Voices:** Per-speaker dropdown populated from configured ElevenLabs Voice
  IDs (`VOICE_CATALOG`), names resolved from the ElevenLabs API; empty catalog
  offers all account voices.
- **Output:** Lossless per-segment render → lossless stitch → WAV master plus
  optional MP3 320. Format configurable. MP4 intentionally skipped.
- **Execution/persistence:** Synchronous generation, files on disk, no database.

## Architecture

```
backend/app/
  config.py                 typed settings (.env)
  main.py                   app factory, CORS, router + provider bootstrap
  api/routes/               health, voices, generate + download
  core/
    models.py               ScriptTurn, Voice, SpeakerVoice, Generate*…
    script_parser.py        "[Speaker N]:" → ordered turns
    engine.py               parse → synth per turn → stitch → export
    stitcher.py             decode/concat/export (pydub + ffmpeg)
    errors.py               domain exceptions → HTTP codes
  providers/
    base.py                 TTSProvider ABC
    registry.py             name → provider
    bootstrap.py            construct + register providers from settings
    elevenlabs_provider.py  concrete ElevenLabs (httpx)
  storage/files.py          per-job output dirs, safe download resolution
frontend/src/               api client, types, components, App
```

### Provider abstraction (core mechanism)

`TTSProvider` exposes `name`, `list_voices()`, and
`synthesize(text, voice_id, *, output_format, voice_settings)`. A dumb registry
maps name → instance; `bootstrap.py` is the single wiring point. `SpeakerVoice`
carries the provider name, so the engine resolves a provider per turn and can
**mix providers across speakers** in one episode. Adding a provider = new
`TTSProvider` subclass + one `register(...)` line.

### Data flow

1. Frontend loads `GET /api/voices` → per-speaker dropdowns.
2. User sets speaker count, assigns voices, pastes the script.
3. `POST /api/generate` `{ script_text, speakers, output_format?, gap_ms? }`.
4. Backend parses turns, validates every speaker has a voice, synthesizes each
   turn, stitches with a configurable gap, exports to `output/<job_id>/`.
5. Response returns metadata + `download_url`s; `GET /api/download/...` serves
   files. Synchronous, with a frontend loading state.

### Error handling

- Parse / missing-voice → `422` with a clear message.
- Unknown provider → `400`. Provider/API failure → `502` (generate) / `503`
  (voices). Missing ffmpeg → startup warning. Path traversal on download → `404`.

## Verification

- **Unit/integration (pytest, 26 tests):** parser edge cases, stitcher
  concat/gap/export, engine with a fake provider (incl. mixed-provider episode),
  ElevenLabs provider with mocked HTTP (respx), and full HTTP generate→download
  round-trip producing a valid WAV.
- **Manual:** `uvicorn` + `npm run dev`; configure 2 speakers, assign voices,
  paste a short script, generate, play/download.

## Out of scope (YAGNI)

Script generation, music/intro-outro/post-production, VibeVoice or any
non-ElevenLabs provider, database/async jobs, auth/multi-user, MP4/video, cloud
deployment.
