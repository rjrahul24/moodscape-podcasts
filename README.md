# 🎙️ Moodscape Podcasts

Turn a written multi-speaker script into a finished podcast episode. Paste a
script, assign a **model + voice** to each speaker, and the app renders every
line, stitches them into one episode, and hands you a downloadable audio file.

**Three TTS models, pickable per speaker** (mix them in one episode):

| Model | Type | Voices |
| --- | --- | --- |
| **ElevenLabs** | Cloud API | Your account's voices (needs an API key) |
| **Kokoro** | Local | 11 built-in named voices |
| **F5** | Local | Zero-shot voice cloning from your own reference clips |

Providers are pluggable behind a single `TTSProvider` interface — new ones drop
in without touching the parser, engine, API, or frontend (see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

```
┌──────────┐    [Speaker N]: …     ┌───────────────────────────────┐
│ Frontend │ ────────────────────▶ │ FastAPI backend               │
│ (React)  │   POST /api/generate  │  parse → synth per turn →      │
│          │ ◀──────────────────── │  normalize → stitch → WAV/MP3  │
└──────────┘    episode + files    └───────────────────────────────┘
                                          │ TTSProvider (registry)
                                          ▼
                                  ElevenLabs · Kokoro · F5
```

## Layout

```
backend/    FastAPI app, TTS provider abstraction, audio engine, tests
frontend/   React + TypeScript (Vite) UI
assets/     F5 reference voices (reference_audio/*.wav + reference_text/*.txt)
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
| `INTER_TURN_GAP_MS` | Silence between speaker turns. |

### Frontend

```bash
cd frontend
npm install
npm run dev                   # serves on http://localhost:5173 (proxies /api → :8000)
```

Open http://localhost:5173, pick the number of speakers, choose a **model and
voice** for each, paste your script, and click **Generate podcast**.

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

Each turn is rendered in the configured `SEGMENT_OUTPUT_FORMAT` (use lossless
`wav_44100` on a Pro+ account for best results), stitched losslessly to avoid
recompression artifacts, and exported as a **WAV master** plus an optional
**MP3 320** for sharing. (MP4 is a video container and isn't used for audio-only
podcasts.)

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
