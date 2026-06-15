# Architecture

Moodscape Studio turns pasted text into finished mindfulness audio in two
content types:

- **Podcasts** — a multi-speaker script; each speaker is assigned a
  **model (provider) + voice**. No audio "treatment" is applied (see CLAUDE.md).
- **Sleep Stories** — single-speaker plain prose rendered with a calming
  treatment (slower pace, inter-sentence pauses, loudness normalization, gentle
  EQ/compression, fades, optional ambient bed) and exported 44.1 kHz **stereo**.
  This calming post-processing is the **sanctioned exception** to the
  "no meditation processing" rule, scoped to sleep stories only.

Generation runs as an **async job**: the client gets a `job_id` immediately and
watches progress over SSE/polling. Long text is **chunked** per provider, each
chunk is synthesized and written to disk, and the chunks are concatenated with
the **ffmpeg concat demuxer** (constant memory, no `MemoryError` on 30–45 min
output). This document is the current-state map — keep it updated (see
`CLAUDE.md` → Documentation discipline).

## Monorepo layout

```
moodscape-podcasts/
  backend/      FastAPI app (Python 3.13, uv-managed)
  frontend/     React + TypeScript (Vite)
  assets/       F5 reference voices (tracked in git)
  docs/         this guide, CHANGELOG, design specs
```

The backend is pinned to **Python 3.13** because the local-TTS stack
(Kokoro/F5 → spacy) has no cp314 wheels yet (`backend/.python-version`,
`requires-python = ">=3.11,<3.14"`).

## Backend layers

```
app/
  main.py            app factory: CORS, routers, provider bootstrap, ffmpeg check
  config.py          typed Settings (.env) — secrets, audio + model params, paths
  api/
    deps.py          SettingsDep
    routes/
      health.py      GET /api/health         (status, providers, ffmpeg, key?)
      voices.py      GET /api/voices         (provider-grouped, resilient)
      generate.py    POST /api/generate (legacy sync), GET /api/download/{job}/{file}
      jobs.py        POST /api/jobs, GET /api/jobs/{id}, GET /api/jobs/{id}/events (SSE)
      ambient.py     GET /api/ambient        (ambient beds for sleep stories)
  core/
    models.py        Voice, ProviderVoices, ScriptTurn, SpeakerVoice, Generate*,
                     PodcastRequest/SleepStoryRequest (discriminated JobRequest),
                     Job{Created,Progress,View}, AmbientBed
    script_parser.py "[Speaker N]: …" -> ordered turns
    chunker.py       sentence/turn-aware chunking (pure; per-provider char budgets)
    orchestrator.py  the generation engine for both content types (run)
    jobs.py          in-memory JobStore + ProgressReporter
    ffmpeg_stitch.py disk-based stitch: chunk WAVs -> ffmpeg concat -> WAV/MP3
    sleep_post.py    sleep-only ffmpeg filter chain (loudnorm/EQ/compress/fades)
    ambient.py       sleep-only ambient bed mix (loop/trim/gain/fade + amix)
    engine.py        legacy shim: GenerateRequest -> orchestrator.run
    stitcher.py      decode/convert + (legacy) in-memory normalize/concat/export
    errors.py        domain exceptions -> HTTP codes
  providers/
    base.py          TTSProvider ABC (synthesize -> AudioSegment)
    registry.py      name -> provider instance
    bootstrap.py     construct + register all providers from Settings
    elevenlabs_provider.py
    kokoro_provider.py     (reads voice_settings["speed"] for per-job speed)
    f5_provider.py         (reads voice_settings["speed"] for per-job speed)
    f5_voice_registry.py
  storage/
    files.py             per-job output dirs + safe download resolution
    ambient_registry.py  scan assets/ambient/*.{wav,mp3} -> {slug: Path}
```

## The provider abstraction

`TTSProvider` (`providers/base.py`) is the single extension point:

- `name: str`
- `list_voices() -> list[Voice]` — **cheap, dependency-light** (populates the UI;
  must not import heavy ML libs or load models).
- `synthesize(text, voice_id, *, output_format, voice_settings=None) -> AudioSegment`

### Why `AudioSegment` is the contract

Cloud providers emit **encoded bytes** (mp3/wav); local models emit **raw numpy**
samples at a fixed rate. Returning a decoded pydub `AudioSegment` unifies them so
the engine and stitcher work in one currency:

- ElevenLabs: `synthesize_bytes(...)` → `stitcher.bytes_to_segment(bytes, fmt)`.
- Kokoro / F5: numpy → `stitcher.numpy_to_segment(samples, 24000)`.

`output_format` is meaningful to cloud providers (it selects request quality);
local providers ignore it (they have a fixed native rate).

### Per-job parameters via `voice_settings`

The contract signature never changed to carry per-job tuning. Instead the
orchestrator passes a `voice_settings` dict, and providers read what they
understand. Today the only key is `speed`: sleep stories pass
`voice_settings={"speed": 0.85}` and `KokoroProvider`/`F5Provider` use it,
falling back to their configured default. ElevenLabs is **not** sent a `speed`
key (the orchestrator only injects it for local providers), so nothing leaks into
its request body. Chunking and inter-sentence pauses never reach providers — they
live in the orchestrator.

### Sample-rate normalization

Providers have different native rates (ElevenLabs up to 44.1kHz, locals 24kHz).
The disk stitcher (`ffmpeg_stitch.segment_to_wav_file`) normalizes every chunk to
the target rate + channel count before writing it, so a single episode can freely
mix providers. (The legacy in-memory `stitcher.stitch` does the same for the old
synchronous path and the tests that still use it.)

### Lazy heavy imports

`KokoroProvider` / `F5Provider` constructors and `list_voices()` do **not** import
torch/kokoro/f5. Those imports happen only inside `synthesize()` (and the model
is cached on the instance as a lazy singleton). Consequences:

- The app always boots; Kokoro/F5 voices populate the dropdowns immediately
  (Kokoro from a static list, F5 from a filesystem scan).
- A missing/broken ML install only fails at generate time, surfaced as a
  `ProviderError` and as a per-provider `error` in `/api/voices`.

## Providers

### ElevenLabs (cloud)
REST via httpx. `list_voices()` → `GET /v1/voices` (optionally filtered by
`VOICE_CATALOG`). `synthesize` → `POST /v1/text-to-speech/{voice}` with
`output_format`, decoded to an `AudioSegment`. Needs `ELEVENLABS_API_KEY`.

### Kokoro (local)
`kokoro.KPipeline(lang_code, repo_id="hexgrad/Kokoro-82M", trf=True, device)`.
CPU on Apple Silicon (MPS causes bus errors), CUDA if available. American voices
use `lang_code="a"`, British (`bf_*`/`bm_*`) use a second `lang_code="b"`
pipeline. 11 built-in named voices (static list in `kokoro_provider.VOICES`).
Output 24kHz.

### F5 (local, voice cloning)
`f5_tts.api.F5TTS(model="F5TTS_v1_Base", device)` (MPS/CPU), `ema_model` cast to
fp16. Each reference is preprocessed once with F5's `preprocess_ref_audio_text`
(clips to ≤12s) and cached. `synthesize` → `model.infer(ref_file, ref_text,
gen_text, nfe_step, cfg_strength, sway_sampling_coef, speed)`. Output 24kHz.

Voices are discovered from the assets folder (`f5_voice_registry.scan`):

```
assets/speakers/reference_audio/<slug>.wav   (≤12s, mono, any rate)
assets/speakers/reference_text/<slug>.txt    (verbatim transcript)
```

Both files required; the slug is the filename stem; display name is the slug
title-cased.

## Async jobs

`POST /api/jobs` accepts a discriminated `JobRequest` (`kind: "podcast" |
"sleep_story"`), creates a `Job` in an in-memory `JobStore`, and returns
`{ job_id }` (202) immediately. The work runs in a **single-slot thread pool**
(`app.state.job_executor`, `max_workers=1`) so the CPU-bound Kokoro/F5 synthesis
stays off the event loop and two heavy models never load at once (OOM guard).

Clients watch progress two ways:

- `GET /api/jobs/{id}/events` — SSE (`sse-starlette`), emitting `progress`
  frames and a terminal `done`/`error` frame. Sends `X-Accel-Buffering: no` +
  `Cache-Control: no-cache`.
- `GET /api/jobs/{id}` — a polling snapshot (`JobView`).

The job's `result` is a `GenerateResult` (same shape as the sync endpoint), so
`GET /api/download/{job}/{file}` is unchanged.

## Chunking

`chunker.py` splits text into bounded chunks **before** any provider call so
Kokoro stays under its 510 phoneme-token cap (it rushes well before that) and F5
stays within ~30s/pass. Budgets are **character**-based per provider
(`KOKORO_CHUNK_CHARS=400`, `F5_CHUNK_CHARS=350`, `ELEVENLABS_CHUNK_CHARS=2400`)
— the "175/250/450 token" references are phonemized tokens, which track
characters far better than BPE tokens, and the research's own guidance is
"~400 chars for Kokoro". The chunker is pure (no provider/ML imports) and splits
on sentence boundaries, only hard-splitting a single over-long sentence.

`chunks_total` is known up front, so progress is simply `chunks_done /
chunks_total`.

## Disk-based stitching

`ffmpeg_stitch.py` replaces in-memory pydub concatenation for the async path:
each synthesized chunk → `AudioSegment` → `segment_to_wav_file` (normalized) on
disk under `output/<job_id>/_chunks/`; gaps/pauses are silence WAVs; then
`ffmpeg -f concat -safe 0` streams them into the master (constant memory). The
working dir is removed after a successful concat.

## Sleep-story pipeline (the sanctioned processing exception)

For `kind: "sleep_story"` the orchestrator: sentence-chunks the prose →
synthesizes with `voice_settings={"speed": …}` → inserts `pause_ms` silence
between sentences → concats to a raw narration WAV → `sleep_post.process`
(ffmpeg: `acompressor` → `lowpass` → `loudnorm` EBU R128 → `afade` in/out →
44.1 kHz **stereo**) → if an ambient bed is chosen, `ambient.mix` loops/trims the
bed to length, pulls it ~22 dB under the voice, fades it, and `amix`es it under
the narration → exports WAV + MP3. None of this touches the podcast path.

Ambient beds are discovered from `assets/ambient/*.{wav,mp3}` via
`ambient_registry.scan` and listed at `GET /api/ambient`.

## Data flow (both content types)

1. Frontend loads `GET /api/voices` (and `GET /api/ambient` for sleep) →
   populates the model/voice (and ambient) dropdowns.
2. User picks a content type. **Podcast:** speaker count + `(provider, voice)`
   per speaker + `[Speaker N]:` script. **Sleep:** one `(provider, voice)`,
   speed/pause/ambient, and plain prose.
3. `POST /api/jobs` → `{ job_id }`. The frontend opens the SSE stream and shows a
   progress bar.
4. The worker runs `orchestrator.run`: chunk → synthesize per chunk to disk →
   ffmpeg concat → (sleep) post-process + ambient → export to `output/<job_id>/`.
5. On the terminal `done` frame the frontend renders the player + download links
   from the job's `result`. No DB, no auth.

The legacy synchronous `POST /api/generate` remains (it adapts `GenerateRequest`
→ `PodcastRequest` and runs `orchestrator.run` with no progress reporting).

## Configuration (Settings)

Loaded from `backend/.env` (see `.env.example`). Highlights: `ELEVENLABS_API_KEY`,
`ELEVENLABS_MODEL_ID`, `VOICE_CATALOG`, `SEGMENT_OUTPUT_FORMAT`, `FINAL_FORMAT`,
`ALSO_EXPORT_MP3`, `INTER_TURN_GAP_MS`, `OUTPUT_DIR`, `TARGET_SAMPLE_RATE`,
`ASSETS_DIR`, `KOKORO_SPEED`, `F5_SPEED`, `F5_NFE_STEP`, `F5_CFG_STRENGTH`,
`F5_SWAY_COEF`. **Chunking:** `KOKORO_CHUNK_CHARS`, `F5_CHUNK_CHARS`,
`ELEVENLABS_CHUNK_CHARS`. **Sleep stories:** `SLEEP_DEFAULT_SPEED`,
`SLEEP_DEFAULT_PAUSE_MS`, `SLEEP_SAMPLE_RATE`, `SLEEP_CHANNELS`,
`SLEEP_TARGET_LUFS`, `SLEEP_LOWPASS_HZ`, `SLEEP_FADE_IN_S`, `SLEEP_FADE_OUT_S`,
`AMBIENT_BED_GAIN_DB`, `AMBIENT_DIR`.

## Frontend

`App.tsx` holds the content type plus per-type state, and drives the async job.
`ContentTypeSelector` toggles Podcast/Sleep. **Podcast:** `SpeakerConfig` (model
+ filtered voice per speaker) + `ScriptInput`. **Sleep:** `SleepStoryConfig`
(single model/voice, speed + pause sliders, ambient picker, prose textarea with a
word-count/duration hint). Both submit to `POST /api/jobs` via `api/jobs.ts`
(`createJob` + `runJob`, which follows the SSE stream); `ProgressBar` renders live
progress; `ResultPlayer` plays/downloads the finished episode. `api/client.ts`
keeps `fetchVoices`. The Vite dev server proxies `/api` → `:8000`.

## Testing

`backend/tests/` (pytest) runs without any model downloads — local providers are
exercised against fake `kokoro`/`f5_tts`/`torch` modules injected into
`sys.modules`, ElevenLabs against mocked httpx (respx), and the orchestrator/jobs
against the network-free `FakeProvider` (which records `voice_settings` so
per-job speed is asserted). Coverage: chunking, the job store, the orchestrator
(podcast + sleep), the jobs API (`POST /api/jobs` → poll to `succeeded`, an SSE
read, download round-trip), the ambient registry, sleep filtergraph construction,
script parsing, stitching, each provider, and resilient grouped voices.
ffmpeg-dependent tests are split: pure filtergraph/concat-list builders always
run; real-ffmpeg round-trips are gated with
`@pytest.mark.skipif(shutil.which("ffmpeg") is None)`.

## Runbook: add a new TTS provider

1. Create `app/providers/<name>_provider.py` implementing `TTSProvider`
   (`name`, `list_voices`, `synthesize -> AudioSegment`). Keep heavy imports
   inside `synthesize`; convert numpy via `stitcher.numpy_to_segment`.
2. Register it in `app/providers/bootstrap.py`.
3. Add any config to `config.py` + `.env.example`.
4. Add tests using a fake-module fixture (see `tests/test_f5_provider.py`).
5. Update this file, `docs/CHANGELOG.md`, and `README.md`.

No changes to the parser, engine, stitcher, API, or frontend should be required.

## Runbook: add an F5 reference voice

Drop `assets/speakers/reference_audio/<name>.wav` and
`assets/speakers/reference_text/<name>.txt` (verbatim transcript, same stem),
restart the backend — the voice appears under the F5 provider. See
`assets/README.md`.

## Runbook: add an ambient bed (sleep stories)

Drop `assets/ambient/<name>.wav` (or `.mp3`), restart the backend — the bed
appears in the Sleep Story ambient picker and at `GET /api/ambient`. A short
seamless loop works for a long story (it is looped/trimmed automatically). See
`assets/ambient/README.md`.
