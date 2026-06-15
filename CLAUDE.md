# CLAUDE.md — Moodscape Podcasts

Guidance for any agent or contributor working in this repo. Read this first.

## What this is

A local, single-user full-stack web app that turns pasted text into finished
mindfulness audio. Two content types:

- **Podcasts** — a multi-speaker script → one downloadable episode.
  **Mindfulness-themed podcasts — NOT guided meditations.** Do NOT add
  meditation-style processing (silence padding, breath sounds, VAD, tone
  shaping, presets) to podcasts.
- **Sleep Stories** — single-speaker plain prose → a calming, sleep-optimized
  episode. This content type has a **sanctioned exception** to the no-processing
  rule: slower pace, inter-sentence pauses, EBU R128 loudness normalization,
  gentle EQ/compression, fades, and an optional ambient bed (44.1 kHz stereo),
  living in `core/sleep_post.py` + `core/ambient.py`. Applied **only** to sleep
  stories — never to podcasts.

Generation is async: `POST /api/jobs` returns a `job_id`; progress streams over
SSE (`GET /api/jobs/{id}/events`). Long text is chunked per provider and stitched
on disk via the ffmpeg concat demuxer.

- **Backend:** FastAPI (Python), in `backend/`. Managed with `uv`. Pinned to
  **Python 3.13** (`.python-version`) — the local-TTS stack (Kokoro/F5 → spacy)
  has no cp314 wheels yet.
- **Frontend:** React + TypeScript (Vite), in `frontend/`.
- **Providers:** ElevenLabs (cloud), Kokoro (local), F5 (local, voice cloning).

## Repo map

```
backend/app/
  api/routes/      health, voices, generate+download, jobs (async+SSE), ambient
  core/            models, script_parser, chunker, orchestrator, jobs,
                   ffmpeg_stitch, sleep_post, ambient, engine (shim), stitcher, errors
  providers/       base (TTSProvider), registry, bootstrap, <provider>_provider.py
  storage/         per-job output files (files.py), ambient_registry.py
frontend/src/      api client + jobs, types, components, App
assets/speakers/   F5 reference voices: reference_audio/*.wav + reference_text/*.txt
assets/ambient/    sleep-story ambient beds: *.wav | *.mp3
docs/              ARCHITECTURE.md, CHANGELOG.md, specs/
```

## Run it

The app is two processes — FastAPI backend (`:8000`) and Vite frontend (`:5173`,
which proxies `/api` → `:8000`). Both must be running.

**One-time install:**

```bash
cd backend  && cp .env.example .env && uv sync --extra dev  # ELEVENLABS_API_KEY if using ElevenLabs; deps multi-GB
cd frontend && npm install
```

**Run both with one command** (from the repo root):

```bash
./dev.sh        # starts backend + frontend, streams both logs, Ctrl-C stops both
```

Then open http://localhost:5173. `dev.sh` keeps `--reload` / Vite hot-reload on
both sides and tears the whole process tree down on Ctrl-C.

**Run the sides separately** (isolated logs, or to restart one without the other):

```bash
# Backend (from backend/)
uv run pytest                            # fast: uses fakes, no model downloads
uv run uvicorn app.main:app --reload     # http://localhost:8000

# Frontend (from frontend/)
npm run dev                              # http://localhost:5173 (proxies /api → :8000)
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
  parser, orchestrator, stitcher, API, and frontend should not need changes.
- **Per-job tuning rides `voice_settings`.** Don't change the `synthesize`
  signature for per-job params — pass them in the `voice_settings` dict (today:
  `speed`, read by Kokoro/F5). The orchestrator injects `speed` only for local
  providers; chunking and pauses stay in the orchestrator, never in providers.
- **No meditation processing on podcasts.** Copy only the core text→audio path
  from any reference implementation. The calming treatment is allowed **only**
  for the Sleep Stories content type (`core/sleep_post.py`, `core/ambient.py`).

See `docs/ARCHITECTURE.md` for the full picture and runbooks ("add a provider",
"add an F5 voice", "add an ambient bed").

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
