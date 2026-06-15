# Architecture

Moodscape Podcasts turns a pasted multi-speaker script into a single
downloadable podcast episode. A user assigns a **model (provider) + voice** to
each speaker; the backend renders each turn, normalizes and stitches the
segments, and exports the episode. This document is the current-state map — keep
it updated (see `CLAUDE.md` → Documentation discipline).

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
      generate.py    POST /api/generate, GET /api/download/{job}/{file}
  core/
    models.py        Voice, ProviderVoices, ScriptTurn, SpeakerVoice, Generate*
    script_parser.py "[Speaker N]: …" -> ordered turns
    engine.py        parse -> synth per turn -> stitch -> export
    stitcher.py      decode/convert, sample-rate normalize, concat, export
    errors.py        domain exceptions -> HTTP codes
  providers/
    base.py          TTSProvider ABC (synthesize -> AudioSegment)
    registry.py      name -> provider instance
    bootstrap.py     construct + register all providers from Settings
    elevenlabs_provider.py
    kokoro_provider.py
    f5_provider.py
    f5_voice_registry.py
  storage/files.py   per-job output dirs + safe download resolution
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

### Sample-rate normalization

Providers have different native rates (ElevenLabs up to 44.1kHz, locals 24kHz).
`stitcher.stitch(...)` normalizes every segment to `Settings.target_sample_rate`
(default 44100, mono) before concatenating, so a single episode can freely mix
providers across speakers.

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

## Data flow

1. Frontend loads `GET /api/voices` → provider-grouped voices → populates each
   speaker's **model** dropdown and (filtered) **voice** dropdown.
2. User sets speaker count, assigns `(provider, voice)` per speaker, pastes the
   `[Speaker N]:` script.
3. `POST /api/generate` `{ script_text, speakers, output_format?, gap_ms? }`.
4. `engine.generate`: parse turns → validate each speaker has a voice → for each
   turn resolve the provider via the registry and `synthesize()` → normalize +
   stitch with a gap → export master (WAV) + optional MP3 to `output/<job_id>/`.
5. Response returns metadata + `download_url`s; `GET /api/download/...` serves
   files. Synchronous, with a frontend loading state. No DB, no auth.

## Configuration (Settings)

Loaded from `backend/.env` (see `.env.example`). Highlights: `ELEVENLABS_API_KEY`,
`ELEVENLABS_MODEL_ID`, `VOICE_CATALOG`, `SEGMENT_OUTPUT_FORMAT`, `FINAL_FORMAT`,
`ALSO_EXPORT_MP3`, `INTER_TURN_GAP_MS`, `OUTPUT_DIR`, `TARGET_SAMPLE_RATE`,
`ASSETS_DIR`, `KOKORO_SPEED`, `F5_SPEED`, `F5_NFE_STEP`, `F5_CFG_STRENGTH`,
`F5_SWAY_COEF`.

## Frontend

`App.tsx` holds state: provider-grouped voices, `numSpeakers`, and
`speakerVoices: Record<speaker, {provider, voice_id}>`. `SpeakerConfig` renders
each speaker row as a **model** `<select>` + a **voice** `<select>` filtered to
the chosen provider (switching the model clears the voice; a provider's `error`
shows inline). `ScriptInput` is the textarea; `ResultPlayer` plays/downloads the
episode. The Vite dev server proxies `/api` → `:8000`.

## Testing

`backend/tests/` (pytest) runs without any model downloads — local providers are
exercised against fake `kokoro`/`f5_tts`/`torch` modules injected into
`sys.modules`, and ElevenLabs against mocked httpx (respx). Coverage: script
parsing, stitching (incl. numpy conversion + mixed-rate normalization), the
engine (incl. a mixed-provider episode), each provider, and the API
(generate→download round-trip + resilient grouped voices).

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
