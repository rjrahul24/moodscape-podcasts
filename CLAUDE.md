# CLAUDE.md — Moodscape Podcasts

Guidance for any agent or contributor working in this repo. Read this first.

## What this is

A local, single-user full-stack web app that turns a pasted multi-speaker script
into one downloadable podcast episode via text-to-speech. **Mindfulness-themed
podcasts — NOT guided meditations.** Do not add meditation-style processing
(silence padding, breath sounds, VAD, tone shaping, presets).

- **Backend:** FastAPI (Python), in `backend/`. Managed with `uv`. Pinned to
  **Python 3.13** (`.python-version`) — the local-TTS stack (Kokoro/F5 → spacy)
  has no cp314 wheels yet.
- **Frontend:** React + TypeScript (Vite), in `frontend/`.
- **Providers:** ElevenLabs (cloud), Kokoro (local), F5 (local, voice cloning).

## Repo map

```
backend/app/
  api/routes/      health, voices (provider-grouped), generate + download
  core/            models, script_parser, engine, stitcher, errors
  providers/       base (TTSProvider), registry, bootstrap, <provider>_provider.py
  storage/         per-job output files
frontend/src/      api client, types, components, App
assets/speakers/   F5 reference voices: reference_audio/*.wav + reference_text/*.txt
docs/              ARCHITECTURE.md, CHANGELOG.md, specs/
```

## Run it

```bash
# Backend (from backend/)
cp .env.example .env          # add ELEVENLABS_API_KEY / VOICE_CATALOG if using ElevenLabs
uv sync --extra dev           # installs everything incl. torch/kokoro/f5 (multi-GB)
uv run pytest                 # fast: uses fakes, no model downloads
uv run uvicorn app.main:app --reload    # http://localhost:8000

# Frontend (from frontend/)
npm install && npm run dev    # http://localhost:5173 (proxies /api → :8000)
```

## Key conventions (don't break these)

- **Providers return a pydub `AudioSegment`** from `synthesize(...)`, not bytes.
  Cloud providers decode their encoded bytes; local models convert numpy via
  `stitcher.numpy_to_segment`. The engine normalizes sample rates before stitching.
- **Heavy ML imports are lazy.** Provider constructors and `list_voices()` must
  NOT import torch/kokoro/f5 — only `synthesize()` may. This keeps the app
  bootable and the voice dropdowns populated even if a heavy lib is missing;
  failures surface as `ProviderError` and a per-provider `error` in `/api/voices`.
- **The provider registry is the extension point.** Add a provider by writing a
  `TTSProvider` subclass and registering it in `providers/bootstrap.py`. The
  parser, engine, stitcher, API, and frontend should not need changes.
- **No meditation processing.** Copy only the core text→audio path from any
  reference implementation.

See `docs/ARCHITECTURE.md` for the full picture and runbooks ("add a provider",
"add an F5 voice").

## Documentation discipline (MANDATORY — applies every session)

Before you consider any change complete:

1. **`docs/ARCHITECTURE.md`** — update it if you changed structure, a contract,
   the provider set, the data flow, or config.
2. **`docs/CHANGELOG.md`** — append a dated entry: what changed, why, and any
   decisions/trade-offs. This log is append-only.
3. **`README.md`** — update if anything user-facing changed (setup, run, env
   vars, the UI flow, supported models).
4. **`docs/superpowers/specs/`** — for a net-new feature, add a dated design spec.

Keeping these current is part of the task, not optional follow-up.
