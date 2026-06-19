# 🎙️ Moodscape Studio

Turn pasted text into finished mindfulness audio. Two content types:

- **🎙️ Podcasts** — a multi-speaker script; assign a **model + voice** to each
  speaker and the app renders every line into one stitched episode.
- **🌙 Sleep Stories** — paste a full story as plain prose, pick one calming
  voice, and get a sleep-optimized episode: slower pace, gentle inter-sentence
  pauses, loudness normalization, soft EQ/compression, fades, and an optional
  ambient bed — exported 44.1 kHz **stereo**.

**Four TTS models, pickable per speaker/voice** (podcasts can mix them in one
episode):

| Model | Type | Voices |
| --- | --- | --- |
| **ElevenLabs** | Cloud API | Your account's voices (needs an API key) |
| **Kokoro** | Local | 11 built-in named voices |
| **F5** | Local | Zero-shot voice cloning from your own reference clips |
| **CosyVoice3** | Local (MLX, Apple Silicon) | Cloning + **Instruct Mode** for calm sleep delivery; `uv sync --extra mlx` |

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
                                  ElevenLabs · Kokoro · F5 · CosyVoice3
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

The app is two processes — a FastAPI backend (`:8000`) and a Vite frontend
(`:5173`) that proxies `/api` to the backend. Both need to be running.

### One command (recommended)

After the one-time installs below (`uv sync` and `npm install`), start both at
once from the repo root:

```bash
./dev.sh        # starts backend + frontend, streams both logs, Ctrl-C stops both
```

Then open http://localhost:5173. The script keeps `--reload` on the backend and
Vite's hot-reload on the frontend, and tears both down together on Ctrl-C. Run
the two sides separately (below) only when you want isolated logs or to restart
one without the other.

### Backend

```bash
cd backend
cp .env.example .env          # then fill in ELEVENLABS_API_KEY / VOICE_CATALOG if using ElevenLabs
uv sync --extra dev           # create venv + install deps (incl. torch/kokoro/f5 — multi-GB, slow)
uv sync --extra mlx           # OPTIONAL, Apple Silicon only: adds CosyVoice3 (mlx-audio-plus)
uv sync --extra qc            # OPTIONAL: long-form QC (Whisper-WER + speaker drift); enable with ENABLE_QC
uv sync --extra clean         # OPTIONAL: denoise uploaded reference clips (noisereduce)
uv run pytest                 # run the test suite (uses fakes; no model downloads)
uv run uvicorn app.main:app --reload   # serves on http://localhost:8000
```

> **First local generation is slow.** The first time you use Kokoro or F5 the
> model weights download and load (hundreds of MB each). On Apple Silicon both
> default to **CPU + float32** (reliable; `float16`-on-MPS garbles F5 output). To
> try Metal, set `F5_DEVICE=mps` after checking `backend/scripts/bench_f5.py`
> (`uv run python scripts/bench_f5.py`) to see whether MPS actually wins.
>
> **CosyVoice3 is opt-in and Apple-Silicon-only.** It needs `uv sync --extra mlx`;
> without it the model still shows in the dropdowns but generation reports a clear
> error. First use downloads the model (~1.1 GB). It clones from the same F5
> reference voices and uses **Instruct Mode** for a calm, hypnotic sleep delivery
> driven by `COSYVOICE_SLEEP_INSTRUCT` (overridable per story in the UI). Compare
> it against F5 with `uv run python scripts/bench_cosyvoice.py`.

> **Check long-form performance on your machine.** `uv run python scripts/bench_longform.py`
> synthesizes increasingly long narration per local provider and reports real-time
> factor (RTF) and peak memory. Use it to confirm 30–90 min jobs stay faster than
> real time and memory stays bounded; if RTF creeps up with length, set `MLX_CACHE_MB`.

Key `.env` settings:

| Variable | What it does |
| --- | --- |
| `ELEVENLABS_API_KEY` | Your ElevenLabs key (required to fetch voices / generate). |
| `ELEVENLABS_PODCAST_MODEL` / `ELEVENLABS_SLEEP_MODEL` | Default ElevenLabs model per content type. Both default to **`eleven_v3`** (expressive, performs inline audio tags); set to `eleven_multilingual_v2` for the stable fallback. The UI overrides this per speaker / per sleep story. v3 needs account access. |
| `ELEVENLABS_USE_SPEAKER_BOOST` / `ELEVENLABS_TEXT_NORMALIZATION` | Send `use_speaker_boost` (default `true` — intimate proximity) and `apply_text_normalization` (default `auto` — spells numbers server-side) on every request. |
| `F5_DEVICE` / `F5_DTYPE` | F5 runtime: `auto`/`cpu`/`mps`/`cuda` and `float32`/`float16`. Default `auto`+`float32` → CPU on Apple Silicon. |
| `COSYVOICE_MODEL` / `COSYVOICE_SLEEP_INSTRUCT` | CosyVoice3 MLX model id and the default sleep delivery directive (Instruct Mode). The UI overrides the directive per story (`style_prompt`). Apple Silicon only. |
| `MLX_CACHE_MB` | Cap MLX's Metal buffer cache (MB) so a long (30–90 min) job doesn't balloon into SSD swap. `0` (default) keeps MLX's own default; `1024` holds peak memory steady. |
| `WARMUP_PROVIDERS` | If `true`, pre-compile kernels at startup with a silent dummy synthesis so the first real generate skips the ~5× JIT penalty. Off by default (adds boot latency, needs the heavy ML libs). |
| `ENABLE_QC` | If `true`, run long-form quality control after each render — transcript word error rate (WER) and cloned-voice drift (speaker similarity). Off by default (≈doubles wall-clock); needs `uv sync --extra qc`. |
| `QC_WHISPER_MLX_REPO` / `QC_WHISPER_FASTER_SIZE` / `QC_SIM_THRESHOLD` | QC tuning: Apple-Silicon Whisper repo, CPU faster-whisper model size, and the cosine-similarity threshold below which a window is flagged as drift. |
| `REFERENCE_CLIP_SAMPLE_RATE` / `REFERENCE_CLIP_MAX_SECONDS` | How uploaded reference clips are cleaned before cloning: target sample rate and the length cap (cloners need only a short window). |
| `VOICE_CATALOG` | JSON list of voices for the dropdown, e.g. `[{"id":"...","label":"Rachel"}]`. Empty `[]` offers every voice on the account. |
| `SEGMENT_OUTPUT_FORMAT` | Per-segment format requested from the provider. Best quality (Pro tier): `wav_44100`. Any tier: `mp3_44100_128`. |
| `FINAL_FORMAT` | Master export format: `wav` (lossless) or `mp3`. |
| `INTER_TURN_GAP_MS` | Silence between speaker turns (podcasts). |
| `CHUNK_EDGE_FADE_MS` | Short edge fade applied to each chunk WAV to remove concat-boundary clicks (default `8`; `0` disables). |
| `KOKORO_CHUNK_CHARS` / `F5_CHUNK_CHARS` / `COSYVOICE_CHUNK_CHARS` / `ELEVENLABS_CHUNK_CHARS` | Max characters per synthesis chunk (keeps Kokoro under its token cap, F5/CosyVoice under ~30s). |
| `SLEEP_DEFAULT_SPEED` / `SLEEP_DEFAULT_PAUSE_MS` | Sleep-story defaults (overridable per request in the UI). |
| `SLEEP_RAMP_SPEED_END_FACTOR` / `SLEEP_RAMP_PAUSE_SCALE` | Progressive ramp-down: how far speed eases (×, default 0.94) and how much pauses lengthen (×, default 1.6) by the end of a story. The UI toggles ramp per story. |
| `SLEEP_TARGET_LUFS` / `SLEEP_TRUE_PEAK_DB` / `SLEEP_LOWPASS_HZ` / `SLEEP_FADE_*` / `AMBIENT_BED_GAIN_DB` | Sleep mastering: loudness target (default −18 LUFS), true-peak ceiling (−2 dBTP), EQ roll-off, fades, ambient level. |

### Frontend

```bash
cd frontend
npm install
npm run dev                   # serves on http://localhost:5173 (proxies /api → :8000)
```

Open http://localhost:5173 and choose a content type at the top:

- **Podcast** — pick the number of speakers, choose a **model and voice** for
  each (ElevenLabs speakers also get a **v2 / v3** engine picker), paste your
  `[Speaker N]:` script, and click **Generate podcast**. Leave **Natural pacing**
  on (default) for sentence pauses, varied timing, and inline tags — `[pause:600]`
  silence, `[breath]`/`[deep_breath]`/`[sigh]` breaths, and tone tags
  `[excited]`/`[calm]`/`[soothing]`/`[reflective]`/`[warm]`/`[sad]`/`[whispering]`;
  turn it off for a flat, evenly-spaced render.
- **Sleep Story** — pick one **model and voice** (ElevenLabs adds the **v3 / v2**
  engine picker — v3 is the default; CosyVoice3 adds a **Delivery style** field —
  its Instruct-Mode directive drives the pace, so the speed slider is ignored), set
  the **speed** and **inter-sentence pause**, leave **Progressive ramp-down** on to
  gently decelerate toward sleep, optionally choose an **ambient bed**, paste your
  story as plain prose, and click
  **Generate sleep story**. The chosen voice now narrates calmly at the model
  level, then the sleep mastering chain runs on top.

Either way a progress bar tracks the job live until the player + download links
appear.

**Clone a voice from the UI.** The **Clone a voice** panel uploads a short clip
(≈10–30 s): it's denoised and trimmed server-side and added to **F5** and
**CosyVoice3** so it appears in their voice dropdowns. A transcript is recommended
(cloning conditions on it); leave it blank to auto-transcribe with local Whisper
(`uv sync --extra qc`). Clips can still be dropped into `assets/speakers/` by hand
instead. Clone only voices you have the right to use.

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

Restart the backend and the voice appears under the **F5** model — and, on Apple
Silicon with `--extra mlx`, the **CosyVoice3** model — in each voice dropdown
(both reuse these reference pairs). Both files are required; see
[assets/README.md](assets/README.md).

## Script format

Each turn starts with a `[Speaker N]:` marker and may span multiple lines:

```
[Speaker 1]: Welcome to the show.
[Speaker 2]: Glad to be here — let's get into it.
[Speaker 1]: Our first topic is bioluminescence...
```

The speaker labels (`Speaker 1`, `Speaker 2`, …) map to the voices you assign in
the UI.

### Conversational pacing & tone tags (podcasts)

With **Natural pacing** on, podcasts get sentence micro-pauses, slightly varied
speaking speed, and variable gaps between turns — so they sound like a real
conversation rather than one flat read. You can also author timing and tone
inline:

| Tag | Effect |
| --- | --- |
| `[pause:600]` or `[pause:600ms]` | Insert silence (here, 600 ms) at that point in the turn. |
| `[excited]` `[calm]` `[sad]` `[whispering]` `[warm]` `[soothing]` `[reflective]` `[neutral]` | Set the tone for the rest of that line. Local voices (Kokoro/F5) adjust speaking rate; ElevenLabs **v2** maps it to native voice settings, **v3** performs it as an inline audio tag. |
| `[laughs]` `[soft laugh]` `[sighs]` `[exhales softly]` `[deep breath]` … | **ElevenLabs v3 only** — performed mid-line cues. v3 acts them out; v2 (and the recognized-tag set above aside) strips unknown bracket tags so they're never spoken. Use sparingly. |

```
[Speaker 1]: That's a great point. [pause:500] I hadn't thought of it that way.
[Speaker 2]: [excited] Right?! The data totally surprised me too.
```

Recognized tags are removed before synthesis (never spoken). Any other bracketed
text is passed through to the provider unchanged. Tone tags are *not* needed —
pacing alone already makes a big difference. Turning Natural pacing off ignores
these tags and renders flat.

**Want an LLM to write the whole script?** `docs/prompting_guides/` has
ready-to-use, model-specific prompts ([ElevenLabs](docs/prompting_guides/elevenlabs.md),
[Kokoro](docs/prompting_guides/kokoro.md), [F5](docs/prompting_guides/f5.md)) —
paste one into ChatGPT/Claude, fill in your topic and speakers, and it returns a
paste-ready script. See [the index](docs/prompting_guides/README.md).

> **Mindfulness podcasts, not meditations.** Pacing + tone only ever change
> *timing and delivery* at conversational scale. The heavier calming treatment
> (loudness mastering, EQ, fades, ambient beds) stays exclusive to Sleep Stories.

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
