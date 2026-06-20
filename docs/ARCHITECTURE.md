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
  dev.sh        dev launcher: starts backend + frontend together, Ctrl-C stops both
  backend/      FastAPI app (Python 3.13, uv-managed)
  frontend/     React + TypeScript (Vite)
  assets/       F5 reference voices (tracked in git)
  docs/         this guide, CHANGELOG, design specs
```

The app runs as two processes: the FastAPI backend on `:8000` and the Vite dev
server on `:5173`, which proxies `/api` → `:8000` (see `frontend/vite.config.ts`)
so the browser makes same-origin requests. `./dev.sh` launches both as child
processes, streams their logs to one terminal, and tears the whole tree down on
Ctrl-C (it kills each child's descendants via `pgrep -P`, since `uv`/`uvicorn`'s
reload child and `npm`'s `vite` child don't forward signals). You can still run
the two sides independently when you want isolated logs.

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
      voices.py      GET /api/voices, POST /api/voices/reference (clip upload)
      generate.py    POST /api/generate (legacy sync), GET /api/download/{job}/{file}
      jobs.py        POST /api/jobs, GET /api/jobs/{id}, GET /api/jobs/{id}/events (SSE)
      ambient.py     GET /api/ambient        (ambient beds for sleep stories)
      series.py      GET /api/series        (podcast series for branded intro/outro)
  core/
    models.py        Voice, ProviderVoices, ScriptTurn, SpeakerVoice, Generate*,
                     PodcastRequest/SleepStoryRequest (discriminated JobRequest),
                     Job{Created,Progress,View}, AmbientBed, SeriesConfig/Info
    script_parser.py "[Speaker N]: …" -> ordered turns; [INTRO]/[BODY]/[OUTRO] sections
    chunker.py       sentence/turn-aware chunking (pure; per-provider char budgets)
    text_processor.py podcast pacing: turn -> Speech/Pause plan items (pure)
    emotion.py       shared tone-tag vocabulary + emotion->speed multipliers (pure)
    ref_clean.py     reference-clip hygiene: mono/resample/trim/denoise (lazy)
    orchestrator.py  the generation engine for both content types (run)
    qc.py            opt-in long-form QC: Whisper-WER + speaker-similarity (lazy)
    jobs.py          in-memory JobStore + ProgressReporter
    ffmpeg_stitch.py disk-based stitch: chunk WAVs -> ffmpeg concat -> WAV/MP3
    sleep_post.py    sleep-only ffmpeg filter chain (loudnorm/EQ/compress/fades)
    ambient.py       sleep-only ambient bed mix (loop/trim/gain/fade + amix)
    podcast_music.py intro/outro music mix (volume envelope + amix, mono)
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
    cosyvoice_provider.py  (MLX; reads voice_settings["instruct"] for delivery)
    reference_voice_registry.py  (shared F5 + CosyVoice clone-voice scan)
    f5_voice_registry.py   (thin re-export of reference_voice_registry)
  storage/
    files.py             per-job output dirs + safe download resolution
    ambient_registry.py  scan assets/ambient/*.{wav,mp3} -> {slug: Path}
    series_registry.py   scan assets/series/*.json -> {slug: SeriesConfig}
```

## The provider abstraction

`TTSProvider` (`providers/base.py`) is the single extension point:

- `name: str`
- **Capability flags** — `consumes_local_speed` (Kokoro, F5: apply a numeric
  `speed` as an internal rate multiplier), `has_native_speed` (ElevenLabs:
  accepts a model-native `speed`, 0.7–1.2), `accepts_instruct` (CosyVoice3:
  takes a natural-language delivery directive in `voice_settings["instruct"]`),
  `accepts_inline_sfx` (performs inline breath/SFX and delivery tags rather than
  speaking them; **True on ElevenLabs** — v3 performs them, so the text processor
  leaves them in the text; default False → tags map to short pauses), and
  `accepts_continuity` (True on ElevenLabs: takes `previous_text`/`next_text`
  context so prosody flows across chunk boundaries). The orchestrator branches on
  these flags instead of hardcoding provider names, so behaviour stays "split per
  model" without name checks leaking up the stack.
- `list_voices() -> list[Voice]` — **cheap, dependency-light** (populates the UI;
  must not import heavy ML libs or load models).
- `synthesize(text, voice_id, *, output_format, voice_settings=None) -> AudioSegment`

### Why `AudioSegment` is the contract

Cloud providers emit **encoded bytes** (mp3/wav); local models emit **raw numpy**
samples at a fixed rate. Returning a decoded pydub `AudioSegment` unifies them so
the engine and stitcher work in one currency:

- ElevenLabs: `synthesize_bytes(...)` → `stitcher.bytes_to_segment(bytes, fmt)`.
- Kokoro / F5: numpy → `stitcher.numpy_to_segment(samples, 24000)`.
- CosyVoice3: `mlx_audio` writes a 24 kHz WAV → `AudioSegment.from_file(...)`.

`output_format` is meaningful to cloud providers (it selects request quality);
local providers ignore it (they have a fixed native rate). ElevenLabs uses a
per-provider override (`ELEVENLABS_SEGMENT_FORMAT=pcm_44100` by default) to
request raw PCM, avoiding double-encode quality loss; `bytes_to_segment`
handles `pcm_*` formats by constructing the `AudioSegment` from raw 16-bit
mono samples.

### Per-job parameters via `voice_settings`

The contract signature never changed to carry per-job tuning. Instead the
orchestrator passes a `voice_settings` dict, and providers read what they
understand (ignoring keys they don't). The keys today:

- **`speed`** — sleep stories pass the configured slow speed; podcasts pass a
  fixed base speed for cloud providers (`has_native_speed`) or a per-chunk
  jittered speed for local models (`consumes_local_speed`). ElevenLabs applies
  it as a model-native speed clamped to 0.7–1.2; local models use it as a rate
  multiplier.
- **`emotion`** — a recognized podcast tone tag. Kokoro/F5 multiply it into their
  rate via `core/emotion.py`. ElevenLabs handles it per model: **v2** maps it to a
  numeric `stability/similarity_boost/style` profile; **v3** performs it as an
  *inline audio tag* prepended to the chunk text (e.g. `[excited]`).
- **`content_type`** (`"podcast"`/`"sleep"`) and **`model_id`** — sent to
  ElevenLabs only. They let the provider pick the right tailoring: an expressive
  profile for podcasts vs a calm, high-stability profile for sleep, and the
  selected generation (v2 vs v3, per speaker / per sleep story). Local providers
  ignore them.
- **`instruct`** — a natural-language delivery directive for CosyVoice3
  (`accepts_instruct`). The sleep path injects `cosyvoice_sleep_instruct`
  (overridable per story via `SleepStoryRequest.style_prompt`) so a calm/hypnotic
  pace is driven by *Instruct Mode*, independent of the cloned clip's energy —
  CosyVoice3 therefore does **not** take `speed`. Other providers ignore it.
- **`previous_text` / `next_text` / `seed`** — sent to continuity-capable
  providers (`accepts_continuity`, i.e. ElevenLabs) only. The orchestrator fills
  the first two with the trailing/leading text of the adjacent chunks (≤200 chars,
  bracket tags stripped) so the model matches pitch/tone across a hard boundary;
  `seed` (from the request) makes a re-render reproducible. The provider forwards
  them as **top-level request-body fields**, not `voice_settings` keys.

ElevenLabs consumes the hint keys (`content_type`/`model_id`/`emotion`/`speed`/
`previous_text`/`next_text`/`seed`) when building the request body, so they never
leak into the API's `voice_settings`. It also always sends `use_speaker_boost`
(configurable) and `apply_text_normalization` (default `"auto"`), and is
model-aware about inline `[bracket]` tags: **v3** keeps them (performed), **v2**
strips them before the read. Chunking, pauses, and pacing never reach providers —
they live in the orchestrator and `core/text_processor.py`.

### Sample-rate normalization

Providers have different native rates (ElevenLabs up to 44.1kHz, locals 24kHz).
The disk stitcher (`ffmpeg_stitch.segment_to_wav_file`) normalizes every chunk to
the target rate + channel count before writing it, so a single episode can freely
mix providers. (The legacy in-memory `stitcher.stitch` does the same for the old
synchronous path and the tests that still use it.)

### Lazy heavy imports

`KokoroProvider` / `F5Provider` / `CosyVoiceProvider` constructors and
`list_voices()` do **not** import torch/kokoro/f5/mlx_audio. Those imports happen
only inside `synthesize()` (and the model is cached on the instance as a lazy
singleton). Consequences:

- The app always boots; Kokoro/F5/CosyVoice voices populate the dropdowns
  immediately (Kokoro from a static list, F5/CosyVoice from a filesystem scan) —
  even on non-Apple-Silicon hosts where `mlx_audio` isn't installed.
- A missing/broken ML install only fails at generate time, surfaced as a
  `ProviderError` and as a per-provider `error` in `/api/voices`.

## Providers

### ElevenLabs (cloud)
REST via httpx. `list_voices()` → `GET /v1/voices` (optionally filtered by
`VOICE_CATALOG`). `synthesize` → `POST /v1/text-to-speech/{voice}` with
`output_format`, decoded to an `AudioSegment`. Needs `ELEVENLABS_API_KEY`.

`_prepare` tailors each call to **two axes** — the selected model and the content
type — both supplied via `voice_settings`:

- **v2** (`eleven_multilingual_v2`): numeric `stability/similarity_boost/style`.
  A tone tag maps to `EMOTION_PROFILES`; otherwise a per-content-type base
  profile (`V2_CONTENT_BASE`) — expressive-but-unforced (style 0.0) for podcasts,
  calm at the research sweet spot (stability 0.70) for sleep. Native `speed` is
  clamped to 0.7–1.2. Inline `[bracket]` tags are **stripped** (v2 can't perform
  them, so they're never spoken).
- **v3** (`eleven_v3`, the default): discrete `stability` (Creative 0.0 / Natural
  0.5 / Robust 1.0) — Natural for podcasts (Creative when `[excited]`), Robust for
  sleep — the recognized tone tag is **performed inline** via `V3_AUDIO_TAGS`, and
  any other `[bracket]` cue in the text is **kept** for the model to perform.

Both paths always send `use_speaker_boost` and (top-level) `apply_text_normalization`,
plus `previous_text`/`next_text`/`seed` when supplied. The model is chosen from
`model_id` (per speaker / per sleep story) or, when unset, the provider's
per-content default (`ELEVENLABS_PODCAST_MODEL` / `ELEVENLABS_SLEEP_MODEL`, both
**`eleven_v3`**). `ELEVENLABS_CHUNK_CHARS=1000` stays under v3's 5k cap.

### Kokoro (local)
`kokoro.KPipeline(lang_code, repo_id="hexgrad/Kokoro-82M", trf=True, device)`.
CPU on Apple Silicon (MPS causes bus errors), CUDA if available. American voices
use `lang_code="a"`, British (`bf_*`/`bm_*`) use a second `lang_code="b"`
pipeline. 11 built-in named voices (static list in `kokoro_provider.VOICES`).
Output 24kHz.

### F5 (local, voice cloning)
`f5_tts.api.F5TTS(model="F5TTS_v1_Base", device)`. **Runtime is config-driven**
(`F5_DEVICE`/`F5_DTYPE`) and defaults to **CPU + float32** — on Apple Silicon,
float16-on-MPS is the documented cause of garbled output and unsupported
flow-matching ops bounce to CPU (so MPS is opt-in: set `F5_DEVICE=mps`, which also
sets `PYTORCH_ENABLE_MPS_FALLBACK=1`). `_resolve_device` honours `cpu`/`mps`/`cuda`
and `auto` (CUDA if present, else CPU); the CPU path also `set_num_threads`.
Inference runs under `torch.inference_mode()`. Defaults: `nfe_step=16` (was 32,
~halves latency), `cfg_strength=2.0`, `sway_coef=-1.0`, and a tighter
`F5_CHUNK_CHARS=250` to stay well under F5's ~30s/pass garble edge. Each reference
is preprocessed once with F5's `preprocess_ref_audio_text` (clips to ≤12s) and
cached. `synthesize` → `model.infer(...)`. Output 24kHz.

`scripts/bench_f5.py` times CPU-fp32 vs MPS-fp32 on the host so the default device
can be set from whichever wins.

Voices are discovered from the assets folder (`reference_voice_registry.scan`):

```
assets/speakers/reference_audio/<slug>.wav   (≤30s, mono, any rate)
assets/speakers/reference_text/<slug>.txt    (verbatim transcript)
```

Both files required; the slug is the filename stem; display name is the slug
title-cased. This registry is **shared** with CosyVoice3 (below);
`f5_voice_registry` remains as a thin re-export for back-compat.

### CosyVoice3 (local, MLX, voice cloning + Instruct Mode)
`mlx-audio-plus` (imports as `mlx_audio`; **Apple Silicon only**, install via
`uv sync --extra mlx`). Model `mlx-community/Fun-CosyVoice3-0.5B-2512-4bit`
(~1.1 GB, downloaded on first synthesis, loaded once via
`mlx_audio.tts.utils.load_model` and cached). A flow-matching DiT model: more
drift-stable than autoregressive models over long outputs, and its **Instruct
Mode** decouples the cloned *timbre* from the *delivery*. `synthesize` calls
`mlx_audio.tts.generate.generate_audio(...)` with `file_prefix` set to a full path
inside a temp dir (the function writes `{file_prefix}.wav` relative to CWD — it
has no output-dir param) and `join_audio=True`, then reads the 24 kHz WAV back as
an `AudioSegment`. **Mode selection matters:** CosyVoice3's `generate` branches
zero-shot (`ref_text`) *before* instruct (`instruct_text`), so the two are
mutually exclusive in practice — with a delivery directive we pass `instruct_text`
and **omit** `ref_text` (the model skips Whisper when instructing); without one we
pass `ref_text` for zero-shot cloning (which also skips the ~1.5 GB Whisper
auto-transcription). Pacing rides the directive, not numeric speed
(`consumes_local_speed=False`, `accepts_instruct=True`). `CHUNK_CHARS=300` keeps
chunks under the ~30 s reference window. Shares the F5 clone-voice assets.
Opt-in for sleep stories; `scripts/bench_cosyvoice.py` renders an A/B sample.

> The installed `mlx-audio-plus` API can differ between versions — the `0.1.8`
> `generate_audio` has no `output_path`/`seed` params and keys instruct mode off
> `instruct_text` (not `instruct`). The provider targets the installed contract.

**Apple-Silicon perf hardening (long-form).** Two controls keep 30–90 min jobs
healthy. `MLX_CACHE_MB` caps MLX's Metal buffer cache (`CosyVoiceProvider.cache_mb`
→ `_cap_mlx_cache()`, run once at model load, best-effort across MLX releases) so
the cache can't grow until the box tips into SSD swap. `WARMUP_PROVIDERS=true` runs
`CosyVoiceProvider.warmup()` (a silent dummy synthesis) at bootstrap to pre-compile
Metal kernels, moving the ~5× first-inference JIT cost off the first real generate.
Both default off; warmup is best-effort (no MLX / no voices → no-op).
`scripts/bench_longform.py` measures RTF + peak RSS per local provider across
increasing lengths to validate that performance stays bounded.

## Long-form quality control (opt-in)

`core/qc.py` checks a finished render for the two long-form failure modes:
hallucinated/dropped words and cloned-voice drift. It runs from `orchestrator.run`
*after* the master is written (`_attach_qc`), only when `ENABLE_QC=true` — it
roughly doubles a job's wall-clock, so it's off by default.

- **WER** — transcribe the master with a local Whisper (`mlx_whisper` preferred,
  `faster_whisper` CPU fallback) and compute word error rate vs the source text
  (inline `[...]` markup stripped first). Pure scoring (`normalize_words`,
  `word_error_rate`) has no deps and is unit-tested directly.
- **Speaker similarity (SIM)** — embed the reference clip and the master's windows
  with `resemblyzer`; windows whose cosine similarity falls below
  `QC_SIM_THRESHOLD` are flagged (drift that develops late in a story surfaces
  here). Runs only when exactly one cloned voice (f5/cosyvoice) is in play — sleep
  stories always qualify; a podcast does when it uses a single distinct cloned voice.

Results land in `GenerateResult.qc` (`QCReport`: `wer`, `transcript`, `sim_mean`,
`sim_min`, `sim_flagged`, `notes`). Like the providers, the heavy libs are imported
lazily and a missing `qc` extra degrades to a `None` metric plus a note in
`qc.notes` — a QC failure never fails an otherwise-good render. Deps: `uv sync
--extra qc`.

## Reference-clip upload + hygiene

`POST /api/voices/reference` (multipart: `name`, `audio`, optional `transcript`)
lets a user clone a voice from the UI. `core/ref_clean.clean_clip` cleans the
upload — mono downmix, resample to `REFERENCE_CLIP_SAMPLE_RATE`, energy-based
silence trim, optional `noisereduce` denoise, length cap — then
`reference_voice_registry.save()` writes it into the existing
`assets/speakers/reference_audio/<slug>.wav` + `reference_text/<slug>.txt` layout.
Because F5 and CosyVoice3 already discover voices by scanning that layout, the new
clip appears in both with **no provider changes**. A transcript is required (the
cloners condition on it); when omitted, the route reuses the Phase 2 local Whisper
(`qc.transcribe`) and returns a clear 422 if no Whisper backend is installed. The
baseline hygiene uses only pydub (a base dep), so upload works out of the box;
denoising needs `uv sync --extra clean`. The frontend `AddVoice` panel posts the
form and re-fetches `/api/voices` so the voice populates every dropdown.

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
(`KOKORO_CHUNK_CHARS=400`, `F5_CHUNK_CHARS=350`, `ELEVENLABS_CHUNK_CHARS=1000`)
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

## Podcast pacing (conversational realism)

For `kind: "podcast"` with `pacing=True` (the default), `_run_podcast` drives
planning through `core/text_processor.plan_turn` instead of `chunker.chunk_turn`.
Each turn becomes an ordered list of `Speech`/`Pause` items:

- **sentence splitting** with a *randomized* intra-sentence micro-pause
  (`PODCAST_INTRA_SENTENCE_GAP_MS_MIN..MAX`, default 80–220 ms);
- **explicit `[pause:600]` / `[pause:600ms]`** tags → exact silence at that point;
- **breath / SFX tags** (`[breath]`/`[deep_breath]`/`[sigh]`, durations in
  `emotion.SFX_PAUSE_MS`): for a provider that can perform them inline
  (`accepts_inline_sfx`, passed into `plan_turn`) the tag stays in the text;
  otherwise it's rewritten to a short `[pause:N]` so the beat lands and no model
  speaks the literal tag. No current provider sets the flag → short-pause mapping;
- a **leading tone tag** (`[excited]`/`[calm]`/`[soothing]`/`[reflective]`/`[warm]`/
  `[sad]`/`[whispering]`/`[neutral]`) lifted off the text and attached as `emotion`
  (stripped before synthesis; any other `[...]` passes through unchanged);
- byte-budget splitting still delegated to `chunker.chunk_text`.

The orchestrator also replaces the flat inter-turn gap with a **variable** one
(`INTER_TURN_GAP_MS` ± `PODCAST_TURN_GAP_JITTER`) and builds per-chunk
`voice_settings={"emotion", "speed"}` (speed jitter for local providers only).
All randomness comes from a single `random.Random(job_id)`, so a job renders
**deterministically**. This is timing + how-words-are-spoken at conversational
scale only — podcasts never call `sleep_post`/`ambient` (no loudnorm/EQ/fades).
`pacing=False` reproduces the legacy flat render (one block per turn, fixed gap,
no emotion).

## Sleep-story pipeline (the sanctioned processing exception)

For `kind: "sleep_story"` the orchestrator: spells standalone numbers to words
(`sleep_text.spell_numbers`) → sentence-chunks the prose → synthesizes each chunk
with a **per-chunk ramped** `speed`/continuity (see below) → inserts a ramped
`pause_ms` silence between sentences → concats to a raw narration WAV →
`sleep_post.process` (ffmpeg: `acompressor` → `lowpass` → `loudnorm` EBU R128 at
−18 LUFS / −2 dBTP → `afade` in/out → 44.1 kHz **stereo**) → if an ambient bed is
chosen, `ambient.mix` loops/trims the bed to length, pulls it ~22 dB under the
voice, fades it, and `amix`es it under the narration → exports WAV + MP3. None of
this touches the podcast path.

**Progressive ramp-down** (`SleepStoryRequest.ramp`, default on, `_sleep_ramp`):
per chunk, `speed` eases linearly from the baseline to
`baseline × SLEEP_RAMP_SPEED_END_FACTOR` and the inter-sentence pause grows to
`× SLEEP_RAMP_PAUSE_SCALE` over the story — a pure function of chunk position, so
it's deterministic. With `ramp` off, a single fixed speed/pause is used.

Both pipelines write chunk WAVs with a short equal-power **edge fade**
(`CHUNK_EDGE_FADE_MS`, default 8 ms) in `ffmpeg_stitch.segment_to_wav_file`, so the
hard concat-demuxer boundary doesn't click. This is a click-removal nicety, not the
overlapping crossfade the research describes (which would break constant-memory
concat and smear conversational turns / sleep pauses).

Ambient beds are discovered from `assets/ambient/*.{wav,mp3}` via
`ambient_registry.scan` and listed at `GET /api/ambient`.

## Podcast series & branded intro/outro

A **series** is a branded podcast show with a consistent intro, outro, and
signature music across episodes. Series configs live as JSON files in
`assets/series/<slug>.json` and are discovered by `series_registry.scan`, listed
at `GET /api/series`.

Scripts can include optional **section markers** — `[INTRO]`, `[BODY]`, `[OUTRO]`
on their own line — which the parser recognizes and annotates each `ScriptTurn`
with (`section` field). When a series is selected in the request
(`PodcastRequest.series`) and section markers are present, the orchestrator:

1. Renders all chunks as usual (same synthesis loop), tracking section per chunk.
2. Groups rendered files by section.
3. Stitches each section to a separate WAV.
4. Mixes music with a multi-stage volume envelope per section:
   - **Intro** (`podcast_music.mix_intro`): 10 s music-only pre-roll at full
     volume, music fades to background as speech begins, stays quiet under speech,
     fades out when speech ends. Uses `adelay` + `apad` + `volume` eval=frame.
   - **Outro** (`podcast_music.mix_outro`): quiet music under speech, music swells
     to full when speech ends, plays solo for 15 s post-roll, fades out. Uses
     `apad` + `volume` eval=frame.
5. Concatenates intro_mixed + body + outro_mixed → master.

Each series has separate intro and outro music files (~30 s each) in
`assets/podcast_music/`. The volume envelope adapts to variable speech length
(the prompting guide targets ~20 s intro / ~15 s outro but the system doesn't
enforce it). Without a series or without section markers, behavior is identical
to the original flat stitch (backward compatible).

## Data flow (both content types)

1. Frontend loads `GET /api/voices`, `GET /api/ambient` (sleep), and
   `GET /api/series` (podcast) → populates dropdowns.
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
`ELEVENLABS_MODEL_ID`, `ELEVENLABS_PODCAST_MODEL`, `ELEVENLABS_SLEEP_MODEL`,
`VOICE_CATALOG`, `SEGMENT_OUTPUT_FORMAT`, `FINAL_FORMAT`,
`ALSO_EXPORT_MP3`, `INTER_TURN_GAP_MS`, `OUTPUT_DIR`, `TARGET_SAMPLE_RATE`,
`ASSETS_DIR`, `KOKORO_SPEED`, `F5_SPEED`, `F5_DEVICE`, `F5_DTYPE`, `F5_NFE_STEP`,
`F5_CFG_STRENGTH`, `F5_SWAY_COEF`. **Chunking:** `KOKORO_CHUNK_CHARS`, `F5_CHUNK_CHARS`,
`ELEVENLABS_CHUNK_CHARS`. **Podcast pacing:** `PODCAST_DEFAULT_SPEED`,
`PODCAST_SPEED_JITTER`, `PODCAST_INTRA_SENTENCE_GAP_MS_MIN`,
`PODCAST_INTRA_SENTENCE_GAP_MS_MAX`, `PODCAST_TURN_GAP_JITTER`. **Sleep stories:**
`SLEEP_DEFAULT_SPEED`,
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

### Design system

The UI runs on a single token-driven stylesheet, `src/styles/index.css`. All
color, spacing (4/8 rhythm), radius, elevation, motion, and typography values are
CSS custom properties under `:root` — components reference tokens (e.g.
`var(--surface-1)`, `var(--grad-brand)`), never raw hex. The look is a dark-first
"Calm Studio": layered surfaces, a lavender→indigo brand ramp with a mint accent,
Lora (display) + Raleway (UI) from Google Fonts, soft elevation, and animated
progress. `prefers-reduced-motion` is honored globally and the grid collapses to
one column under 560px. Iconography is a single stroke-based SVG set in
`components/Icon.tsx` (`<Icon name=… />`, inheriting `currentColor`) — there are
no emoji glyphs in the UI. To restyle, edit the tokens; to add an icon, add an
entry to `Icon.tsx`.

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
`assets/speakers/reference_text/<name>.txt` (same stem), restart the backend —
the voice appears under the F5 provider. See `assets/README.md`.

**Reference contract (clone quality depends on it):**

- The `.wav` is a **clean, single-speaker** clip, mono, ~10–15 s. F5 takes the
  voice *identity and prosody* from this clip — a slow/rushed/noisy reference
  produces a slow/rushed/noisy clone.
- The `.txt` must be the **exact words spoken** in that clip (normal
  punctuation). F5 aligns acoustic features to this transcript; a mismatch
  degrades the clone and can cause slurring.
- Multiple voices **may share the same transcript** if they read the same script
  — identity comes from the audio, not the text. (The shipped David/Lily/Max/
  Riley voices do exactly this.)
- On Apple Silicon, expect F5 to run on **CPU + float32** by default; if the
  bench (`scripts/bench_f5.py`) shows MPS wins, set `F5_DEVICE=mps`.

## Runbook: add an ambient bed (sleep stories)

Drop `assets/ambient/<name>.wav` (or `.mp3`), restart the backend — the bed
appears in the Sleep Story ambient picker and at `GET /api/ambient`. A short
seamless loop works for a long story (it is looped/trimmed automatically). See
`assets/ambient/README.md`.

## Runbook: add a podcast series

1. Create `assets/series/<slug>.json` with the series config (see
   `assets/series/the-shared-space.json` for the format).
2. Drop the intro/outro music file(s) into `assets/podcast_music/`. A short
   seamless loop works (it is looped/trimmed automatically by `podcast_music.py`).
3. Restart the backend — the series appears in the Podcast panel's Series
   dropdown and at `GET /api/series`.
4. In your script, use `[INTRO]`, `[BODY]`, `[OUTRO]` section markers. When the
   series is selected in the app, music is mixed under the intro and outro.

## Runbook: add intro/outro music

Drop two files in `assets/podcast_music/` — one for intro, one for outro (~30 s
each). Reference them in the series JSON config as `intro_music` and
`outro_music`. The system applies a multi-stage volume envelope: full volume
when music plays solo (pre-roll / post-roll), quiet under speech. Tune
`music_full_gain_db` (solo, default −12 dB) and `music_bg_gain_db` (under
speech, default −22 dB) in the config. Adjust `intro_preroll_s` (default 10 s),
`intro_fade_start_s` (default 8 s), `outro_postroll_s` (default 15 s), and
`music_crossfade_s` (default 2 s) to change timing.
