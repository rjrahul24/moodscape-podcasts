# 🎙️ Moodscape Studio

Turn pasted text into finished mindfulness audio. Two content types:

- **🎙️ Podcasts** — a multi-speaker script; assign a **model + voice** to each
  speaker and the app renders every line into one stitched episode.
- **🌙 Sleep Stories** — paste a full story as plain prose, pick one calming
  voice, and get a sleep-optimized episode: slower pace, gentle inter-sentence
  pauses, loudness normalization, soft EQ/compression, fades, and an optional
  ambient bed — exported 44.1 kHz **stereo**.

**Three TTS models, pickable per speaker/voice** (podcasts can mix them in one
episode):

| Model | Type | Voices |
| --- | --- | --- |
| **ElevenLabs** | Cloud API | Your account's voices (needs an API key) |
| **Kokoro** | Local | 11 built-in named voices |
| **F5** | Local | Zero-shot voice cloning from your own reference clips |

Providers are pluggable behind a single `TTSProvider` interface — new ones drop
in without touching the parser, orchestrator, API, or frontend (see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

Generation is **async**: the frontend gets a `job_id`, then streams live progress
over SSE while the backend chunks the text, synthesizes each chunk to disk, and
stitches with the ffmpeg concat demuxer (so 30–45 min sleep stories don't time
out or exhaust memory).

```
┌──────────┐   POST /api/jobs      ┌───────────────────────────────┐
│ Frontend │ ────────────────────▶ │ FastAPI backend               │
│ (React)  │   {job_id}            │  chunk → synth per chunk →     │
│          │ ◀─ SSE progress ───── │  ffmpeg concat → (sleep:       │
│          │ ◀── episode + files── │  loudnorm/EQ/ambient) → WAV/MP3│
└──────────┘                       └───────────────────────────────┘
                                          │ TTSProvider (registry)
                                          ▼
                                  ElevenLabs · Kokoro · F5
```

## Layout

```
backend/    FastAPI app, TTS provider abstraction, async orchestrator, tests
frontend/   React + TypeScript (Vite) UI
assets/     F5 reference voices (speakers/) + sleep ambient beds (ambient/)
docs/       ARCHITECTURE.md, CHANGELOG.md, design specs
```

## Prerequisites

- **Python 3.11–3.13** and [`uv`](https://docs.astral.sh/uv/). The repo pins
  **3.13** (`backend/.python-version`) — the local models (Kokoro/F5) pull in
  `spacy`, which has no Python 3.14 wheels yet. `uv` fetches 3.13 automatically.
- **Node 18+** and npm
- **ffmpeg** on your PATH (audio decode/stitch/encode) — `brew install ffmpeg`
- For ElevenLabs: an **API key** and the **Voice IDs** you want to offer
  (Kokoro and F5 need no key)

## Setup

### Backend

```bash
cd backend
cp .env.example .env          # then fill in ELEVENLABS_API_KEY / VOICE_CATALOG if using ElevenLabs
uv sync --extra dev           # create venv + install deps (incl. torch/kokoro/f5 — multi-GB, slow)
uv run pytest                 # run the test suite (uses fakes; no model downloads)
uv run uvicorn app.main:app --reload   # serves on http://localhost:8000
```

> **First local generation is slow.** The first time you use Kokoro or F5 the
> model weights download and load (hundreds of MB each). Kokoro runs on CPU
> (fast enough), F5 on Apple Silicon's MPS.

Key `.env` settings:

| Variable | What it does |
| --- | --- |
| `ELEVENLABS_API_KEY` | Your ElevenLabs key (required to fetch voices / generate). |
| `VOICE_CATALOG` | JSON list of voices for the dropdown, e.g. `[{"id":"...","label":"Rachel"}]`. Empty `[]` offers every voice on the account. |
| `SEGMENT_OUTPUT_FORMAT` | Per-segment format requested from the provider. Best quality (Pro tier): `wav_44100`. Any tier: `mp3_44100_128`. |
| `FINAL_FORMAT` | Master export format: `wav` (lossless) or `mp3`. |
| `INTER_TURN_GAP_MS` | Silence between speaker turns (podcasts). |
| `KOKORO_CHUNK_CHARS` / `F5_CHUNK_CHARS` / `ELEVENLABS_CHUNK_CHARS` | Max characters per synthesis chunk (keeps Kokoro under its token cap, F5 under ~30s). |
| `SLEEP_DEFAULT_SPEED` / `SLEEP_DEFAULT_PAUSE_MS` | Sleep-story defaults (overridable per request in the UI). |
| `SLEEP_TARGET_LUFS` / `SLEEP_LOWPASS_HZ` / `SLEEP_FADE_*` / `AMBIENT_BED_GAIN_DB` | Sleep mastering: loudness target, EQ roll-off, fades, ambient level. |

### Frontend

```bash
cd frontend
npm install
npm run dev                   # serves on http://localhost:5173 (proxies /api → :8000)
```

Open http://localhost:5173 and choose a content type at the top:

- **Podcast** — pick the number of speakers, choose a **model and voice** for
  each, paste your `[Speaker N]:` script, and click **Generate podcast**.
- **Sleep Story** — pick one **model and voice**, set the **speed** and
  **inter-sentence pause**, optionally choose an **ambient bed**, paste your
  story as plain prose, and click **Generate sleep story**.

Either way a progress bar tracks the job live until the player + download links
appear.

## Sleep Stories

Sleep stories are single-speaker and take **plain prose** (no `[Speaker]` tags).
A warm Kokoro voice such as `af_heart` at speed ~0.85 works well. The backend
applies a calming master — narrowed dynamics, gentle high-frequency roll-off,
EBU R128 loudness normalization, slow fades — and exports **44.1 kHz stereo**.
Rough lengths: a 30-min story is ~2,700–3,300 words; 45 min is ~4,000–5,000.

To layer an ambient soundscape under the narration, drop audio files in
`assets/ambient/` (see below) and pick one from the **Ambient bed** dropdown.

> This calming treatment applies to **sleep stories only** — podcasts are never
> processed (a deliberate project rule; see `CLAUDE.md`).

## Adding ambient beds (sleep stories)

```
assets/ambient/<name>.wav     # or .mp3 — a short seamless loop is fine
```

The bed is looped/trimmed to the story length, pulled well under the voice, and
faded. Restart the backend and it appears in the ambient picker. See
[assets/ambient/README.md](assets/ambient/README.md).

## Adding F5 voices (cloning)

F5 clones a voice from a short reference clip. Drop two same-named files in:

```
assets/speakers/reference_audio/<name>.wav    # 10–12 s, mono (any rate)
assets/speakers/reference_text/<name>.txt     # verbatim transcript of that clip
```

Restart the backend and the voice appears under the **F5** model in each
speaker's voice dropdown. Both files are required; see [assets/README.md](assets/README.md).

## Script format

Each turn starts with a `[Speaker N]:` marker and may span multiple lines:

```
[Speaker 1]: Welcome to the show.
[Speaker 2]: Glad to be here — let's get into it.
[Speaker 1]: Our first topic is bioluminescence...
```

The speaker labels (`Speaker 1`, `Speaker 2`, …) map to the voices you assign in
the UI. Inline provider tags like `[excited]` are passed through to the provider.

## Output quality

Each chunk is rendered in the configured `SEGMENT_OUTPUT_FORMAT` (use lossless
`wav_44100` on a Pro+ account for best results), written to disk, and stitched
with the ffmpeg concat demuxer (constant memory) into a **WAV master** plus an
optional **MP3 320** for sharing. Sleep stories add a calming master and export
44.1 kHz stereo. (MP4 is a video container and isn't used for audio-only output.)

## Adding a new TTS provider

1. Implement `TTSProvider` in `backend/app/providers/<name>_provider.py`
   — `list_voices()` (cheap, no heavy imports) and
   `synthesize(...) -> AudioSegment` (heavy ML imports lazy, inside the method).
2. Construct and register it in `backend/app/providers/bootstrap.py`.

Nothing else changes — speakers can mix providers within one episode. Full
runbook (and the design rationale) in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

`docs/ARCHITECTURE.md` is the living architecture guide; `docs/CHANGELOG.md` logs
every change and decision; `CLAUDE.md` carries conventions and a documentation
rule that keeps all of the above current. Update them with any change.
