# 🎙️ Moodscape Podcasts

Turn a written multi-speaker script into a finished podcast episode. Paste a
script, assign a voice to each speaker, and the app renders every line through a
text-to-speech provider, stitches them into one episode, and hands you a
downloadable audio file.

**Providers are pluggable.** ElevenLabs is implemented today; new providers
(e.g. Microsoft VibeVoice) drop in behind the same interface without touching
the parser, engine, API, or frontend.

```
┌──────────┐    [Speaker N]: …     ┌───────────────────────────────┐
│ Frontend │ ────────────────────▶ │ FastAPI backend               │
│ (React)  │   POST /api/generate  │  parse → synth per turn →      │
│          │ ◀──────────────────── │  stitch → export WAV/MP3       │
└──────────┘    episode + files    └───────────────────────────────┘
                                          │ TTSProvider (registry)
                                          ▼
                                    ElevenLabs · [VibeVoice · …]
```

## Layout

```
backend/    FastAPI app, TTS provider abstraction, audio engine, tests
frontend/   React + TypeScript (Vite) UI
docs/       Design spec
```

## Prerequisites

- **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/)
- **Node 18+** and npm
- **ffmpeg** on your PATH (audio decode/stitch/encode) — `brew install ffmpeg`
- An **ElevenLabs API key** and the **Voice IDs** you want to offer

## Setup

### Backend

```bash
cd backend
cp .env.example .env          # then fill in ELEVENLABS_API_KEY and VOICE_CATALOG
uv sync --extra dev           # create venv + install deps
uv run pytest                 # run the test suite
uv run uvicorn app.main:app --reload   # serves on http://localhost:8000
```

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

Open http://localhost:5173, pick the number of speakers, assign a voice to each,
paste your script, and click **Generate podcast**.

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
   (`list_voices()` and `synthesize(...)`).
2. Construct and register it in `backend/app/providers/bootstrap.py`.
3. Add its voice IDs to `VOICE_CATALOG` (with `"provider": "<name>"`).

Nothing else changes — speakers can even mix providers within one episode.
