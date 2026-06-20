# Changelog

Append-only log of notable changes and the decisions behind them. Newest first.
Every change should add an entry (see `CLAUDE.md` → Documentation discipline).

## 2026-06-20 — Sleep UX: bare [pause] support + ambient pre-roll

**What changed** (sleep stories only; podcasts untouched):
- **Bare `[pause]` tags now work.** The pause-marker regex was tightened to
  `[pause:N]` only — a bare `[pause]` (without `:N`) was silently stripped on v2
  and left verbatim for v3 to garble. The regex now accepts `[pause]` and uses a
  configurable default duration (`sleep_pause_default_ms`, default 1000 ms). On
  v2 it becomes `<break time="1.00s"/>`; on v3 and local engines it splices 1 s
  of silence. Both `sleep_text.split_pauses` and the ElevenLabs provider's
  `_pause_markers_to_breaks` are updated.
- **Ambient pre-roll** (`sleep_preroll_s`, default 3.0 s). When an ambient bed is
  selected, the orchestrator prepends a silent pre-roll to the mastered narration
  before mixing, so the ambient bed plays alone for 3 seconds before the first
  word. Gives listeners a gentle entry rather than an abrupt start. Only applies
  when an ambient bed is selected; 0 disables.

**Why:** users reported (1) `[pause]` tags not being honoured by ElevenLabs
(the regex required a numeric duration; bare tags were common in hand-written
prose) and (2) sleep stories starting too abruptly (narration began on the
first sample, with no musical lead-in).

---

## 2026-06-20 — ElevenLabs sleep quality: lossless pipeline + anti-drift tagging

**What changed** (sleep stories + ElevenLabs only; podcasts untouched):
- **Higher-quality intermediate.** `elevenlabs_segment_format` stays at
  `mp3_44100_192` (the best format the Creator tier offers). Lossless `pcm_44100`
  is supported by the pipeline (`bytes_to_segment` decodes raw `pcm_*`) but
  **requires an ElevenLabs Pro plan**, so it's documented as an opt-in rather than
  the default. Set `ELEVENLABS_SEGMENT_FORMAT=pcm_44100` on Pro for a truly
  lossless intermediate.
- **Per-chunk loudness normalization before stitching** (`sleep_chunk_normalize`,
  default on). New `ffmpeg_stitch.normalize_loudness` normalizes each speech chunk
  to `sleep_chunk_norm_lufs` (−21 LUFS) before the concat; the −18 LUFS master
  pass then sets the absolute level. Chunks under `sleep_chunk_norm_min_ms`
  (400 ms) are skipped. Output rate is re-pinned because `loudnorm` upsamples to
  192 kHz internally (would otherwise break the concat demuxer).
- **v3 pacing-tag reassertion** (`elevenlabs_sleep_v3_pacing_tag`, default `""` =
  off). When set to e.g. `[slowly]`, `_prepare_v3` prepends it after the emotion
  tag on every sleep chunk so v3 holds its slow, calm register.
- **Sentence-boundary ellipsis injection** (`sleep_sentence_ellipsis`, default
  off). `sleep_text.inject_sentence_pauses` adds a soft `…` at sentence breaks.

**Why:** ported from the reference meditation project (`moodscape-mix-lib`),
which gets noticeably better ElevenLabs output. The base settings already matched
(v3, stability 0.5, speaker boost); the reference's edge was pipeline hygiene
(lossless, per-chunk level consistency) and reasserting a pacing tag to stop v3
drifting toward an audiobook read on long stories.

**Trade-offs / decisions:** the two character-altering knobs (pacing tag,
ellipsis) ship **defaults-off** so existing renders are byte-identical until opted
into for A/B. A heavyweight overlapping crossfade was considered and rejected: the
sleep path already splices real silence between chunks, so seams are mostly
silence-separated, and a crossfade would fight the constant-memory concat design
for little gain — the existing 8 ms edge fade is kept.

## 2026-06-20 — F5 performance: the real fix (nfe_step + reference clip)

Sleep stories still took ~53 min for a 10-min render after the MPS/fp16 change
below. Benchmarking on the host (MPS + fp16) found the actual cost drivers, which
were **not** device/dtype:

| config (MPS+fp16)            | RTF  |
|-----------------------------|------|
| nfe=32, ref 13s (old sleep) | 5.32 |
| nfe=16, ref 13s             | 2.35 |
| nfe=12, ref 13s             | 1.75 |
| nfe=16, ref 6s              | 1.42 |
| nfe=8,  ref 6s              | 0.69 |

Two roughly-multiplicative levers dominate; device (MPS vs CPU ≈ 1.6x) and dtype
(fp16 vs fp32 ≈ 8%) are minor by comparison.

**What changed:**
- **Sleep `f5_sleep_nfe_step` 32 → 16.** F5 runtime scales ~linearly with
  `nfe_step`; with sway sampling, 16 holds quality (the reference meditation
  project uses 16 as its working default, 32 only for final renders). ~2x faster.
- **New `f5_ref_clip_seconds` (default 8.0).** F5 recomputes the *reference +
  generated* sequence every chunk, so the reference length is a direct per-chunk
  multiplier. References are clipped to 8s in `_get_reference` **before** Whisper
  transcription (so the derived `ref_text` still matches the audio — clipping
  after would reintroduce leakage). New `_clip_audio_file` helper. ~1.6x faster.
- Combined: a 10-min sleep story now renders at **RTF ~1.5 (~15 min)** vs the
  previous RTF ~5.3 (~53 min) — measured end-to-end.
- Fixed a regression from the change below: `_apply_silero_vad` lost its
  `import torch` when VAD loading was refactored into `_get_vad`, so VAD silently
  failed on every chunk. Restored.

**Trade-offs:** nfe=16 is marginally lower fidelity than 32 on paper; in practice
sway sampling makes it indistinguishable for narration, and both remain tunable
(`F5_SLEEP_NFE_STEP`, `F5_NFE_STEP`). An 8s reference is ample for F5 voice
cloning; `F5_REF_CLIP_SECONDS=0` disables clipping.

## 2026-06-20 — F5 performance: MPS + float16 + VAD caching

**What changed:**
- `_resolve_device()` now falls through to MPS on Apple Silicon (was CPU-only for
  the `auto` path). Measured ~1.6x faster than CPU here (not the 5-10x first
  assumed — see the entry above for the real cost drivers).
- float16 is auto-selected when device is MPS. ~8% on top of the MPS win.
  Explicit `F5_DTYPE=float32` overrides.
- Silero VAD model is cached at module level (`_vad_cache`) instead of calling
  `torch.hub.load()` on every chunk.
- Updated config.py comments and ARCHITECTURE.md.

**Why:** the initial hypothesis was that `auto` resolved to CPU on Apple Silicon.
That was true and worth fixing, but on this host MPS+fp16 still left RTF ~5.3 at
the old nfe=32 — unusable. The follow-up entry above is the fix that actually made
it sustainable.

**Trade-offs:** float16 on MPS was previously avoided over garbled-output
concerns; it runs cleanly here. `F5_DTYPE=float32` remains an escape hatch.

## 2026-06-20 — F5 sleep story quality improvement

**What changed:**
- F5 reference audio is now conditioned at load time: RMS-normalized to -20 dBFS
  and padded with ~1s trailing noise at -55 dBFS. This prevents F5's duration
  heuristic from leaking reference syllables into generated output.
- Reference transcripts are now Whisper-verified (auto-transcribed from the clipped
  audio) instead of read from .txt files, eliminating ref_text/audio misalignment.
- Post-synthesis: trailing silence trimming (-45 dBFS threshold, 50ms decay tail)
  and Silero VAD (crop trailing non-speech, attenuate interior gaps to 15%).
- Short-phrase pacing: chunks with ≤12 non-space characters use speed 0.5 to
  prevent reference leakage on tiny fragments like "Breathe in."
- New `core/f5_text.py` module normalizes text for F5's G2P: colons→commas,
  ellipses→periods, dashes→commas, compound hyphens removed, ALL_CAPS lowered.
- Orchestrator wires F5 normalization into both sleep and podcast paths.
- F5 sleep stories now use nfe_step=32 (vs 16 for podcasts) and speed=0.88
  (~95-100 WPM meditation pace) as defaults.
- New `docs/prompting_guides/f5_sleep.md` — dedicated LLM prompting guide for
  writing F5 sleep story prose.
- Added `scipy` as a dependency (for Silero VAD gaussian smoothing).

**Why:** F5 sleep stories had three issues: reference text leaking into output
(no duration predictor workaround), poor quality (no text normalization, no
post-processing, nfe_step too low), and slow rendering (reference preprocessing
per-call). All fixes ported from the meditation reference project's battle-tested
F5 engine.

**Trade-offs:** Silero VAD adds ~0.5s per chunk but significantly improves output
cleanliness. nfe_step=32 doubles inference time per chunk vs 16, but sleep stories
prioritize quality over speed. scipy added as a base dependency (~30MB).

## 2026-06-20 — Remove CosyVoice3 provider

Removed the CosyVoice3 (MLX) Apple-Silicon-only provider entirely: provider
implementation, config settings, the `mlx` optional-dependency group, benchmark
script, design spec, Instruct Mode plumbing (`accepts_instruct` capability flag,
`_sleep_voice_settings` instruct branch), frontend Delivery style field, and all
documentation references. Three providers remain: ElevenLabs, Kokoro, F5.

## 2026-06-20 — Phase 10c: Fix punctuation-to-pause quality regression

The Phase 10b conversion removed punctuation from the text, stripping prosodic
cues Kokoro uses for intonation contour even though it doesn't audibly pause.
This caused flat voice, too-long comma pauses, and voice drift at boundaries.

- **Keep punctuation, insert pauses after it.** `punctuation_to_pauses()` now
  inserts `[pause:N]` markers *after* each punctuation mark instead of replacing
  it. Kokoro gets `"cool, "` (with the comma for prosody) then silence, then the
  next fragment — instead of `"cool "` (comma stripped, no prosodic anchor).
  (`sleep_text.py`)
- **Reduced comma pause.** 150 ms → **80 ms** — a subtle micro-breath, not a
  full gap. (`config.py` `kokoro_pause_comma_ms`)

## 2026-06-20 — Phase 10b: Kokoro punctuation-to-pause conversion

Kokoro TTS ignores punctuation marks entirely for pausing — commas, ellipses,
semicolons, and dashes produce no audible gap. The previous `enhance_pacing()`
approach (inserting more commas/ellipses) was ineffective.

- **Punctuation-to-pause conversion.** Replaced `enhance_pacing()` with
  `punctuation_to_pauses()` in `sleep_text.py`. For Kokoro sleep stories only,
  commas → `[pause:150]`, ellipses → `[pause:350]`, semicolons → `[pause:200]`,
  dashes → `[pause:250]`, paragraph breaks → `[pause:400]`. Periods left intact
  (chunker handles sentence boundaries). The orchestrator's existing
  `split_pauses` machinery splices real silence at each marker.
  (`sleep_text.py`, `orchestrator.py`, `config.py` `kokoro_pause_*`)
- **Gated to Kokoro only.** Other providers (ElevenLabs, F5) handle
  punctuation natively and get unmodified text.
- **Updated prompting guide.** `kokoro_sleep.md` now explains that punctuation is
  automatically converted to pauses — authors write with natural commas/ellipses
  and the app handles the rest.

## 2026-06-20 — Phase 10: Kokoro sleep quality refinement (8/10 → 10/10)

Targeted refinements to Kokoro TTS sleep story quality across four areas:

- **Wider inter-sentence gaps.** `sleep_default_pause_ms` 900 → **1050** ms. With
  the ramp, pauses now reach ~1680 ms by the story's end (was 1440). A subtle
  increase that gives the listener more breathing room without breaking flow.
  (`config.py`)
- **Automated pacing enhancement.** New `sleep_text.enhance_pacing()` inserts
  commas at long unpunctuated clause boundaries (>80 chars), converts ~25 % of
  paragraph-internal periods to ellipses for a driftier rhythm, and adds
  `[pause:400]` at paragraph breaks. Deterministic (seeded RNG). Runs after
  `spell_numbers()`, before chunking — sleep stories only, never podcasts.
  (`sleep_text.py`, `orchestrator.py`)
- **Consistent ambient bed volume.** Added EBU R128 loudness normalization
  (`loudnorm I=-24 LUFS`) to the ambient bed filter chain *before* band-limiting
  and gain reduction. Different ambient files now start at the same perceived
  level, so the `-18 dB` pull-down produces consistent results regardless of
  source material. (`ambient.py`, `config.py` `ambient_bed_target_lufs`)
- **New sleep emotion tags.** Added `dreamy` (0.90× speed) and `tender` (0.96×)
  to the shared emotion vocabulary, with matching ElevenLabs v2 profiles and v3
  inline tags. Gives script-writers finer pacing control for different story
  moments. (`emotion.py`, `elevenlabs_provider.py`)
- **Kokoro sleep prompting guide.** New `docs/prompting_guides/kokoro_sleep.md` —
  comprehensive guide for writing Kokoro sleep stories: punctuation-based pacing
  toolkit, `[pause:N]` usage with recommended durations, tone tag reference,
  techniques for writing emotion into words (sensory imagery, repetition-as-rhythm,
  progressive relaxation), story structure guidance, and a worked example.
  (`kokoro_sleep.md`, `README.md`)

## 2026-06-20 — Phase 9: Sleep tuning — slower pace, expressive v2, audible bed

Follow-up to Phase 8 from listening feedback:

- **Slower default delivery.** `sleep_default_speed` 0.85 → **0.78** (ElevenLabs
  honours 0.7–1.2; this leans toward the slow floor) and the frontend Speed default
  matches. The rewritten prompting guide adds a **"Pacing the voice"** section:
  punctuation- and rhythm-based techniques (short sentences, generous commas,
  ellipses, one image per sentence, no run-ons) that genuinely slow the read — the
  biggest lever for a *calm* feel, since speed alone sounds dragged if pushed too far.
  (`config.py`, `App.tsx`, `elevenlabs_sleep.md`)
- **Expressive, drift-free v2.** For users seeing v3 voice drift, the guide now
  recommends v2 for long stories and adds a **"Writing for v2"** section (emotion via
  words/rhythm, since v2 can't perform inline cues). Code: the `soothing` default tone
  profile gets more `style` (0.08 → 0.22) for warmth (`warm`/`reflective` are shared
  with podcast v2, so they're unchanged); a **leading author tone tag**
  (`[calm]`/`[warm]`) is now extracted and honored on
  *both* engines — v3 performs it, v2 maps it to a warmer numeric profile — and
  stripped from the text so it's never spoken or double-tagged. (`orchestrator.py`
  `_sleep_tone`, `elevenlabs_provider.py`)
- **Audible ambient bed.** `ambient_bed_gain_db` -22 → **-18** and the duck softened
  (`ambient_duck_ratio` 4 → 2, threshold -30 → -28) so the near-continuous narration
  no longer keeps the bed ducked into inaudibility. Still low and behind the voice,
  just present. (`config.py`)

## 2026-06-20 — Phase 8: Perfecting ElevenLabs sleep stories

Focused pass to make ElevenLabs sleep-story generation the best version possible:
expressive-yet-calm narration, author-controlled breaths, and a soft, slow music
bed. Research (ElevenLabs audiobook/best-practice docs + v3-vs-v2 comparisons)
surfaced an internal contradiction and a dead documented feature.

- **v3 sleep stability: Robust → Natural.** Sleep ran v3 at Robust (1.0), which
  largely *ignores* the inline audio tags that are the whole reason to use v3.
  Switched to Natural (0.5, `elevenlabs_sleep_v3_stability`) so `[calm]`/`[warmly]`
  actually shape delivery while staying steady. Both engines are now well-tuned and
  selectable (v3 expressive default; v2 most reliable for long stories — native
  breaks, best normalization, continuity). (`elevenlabs_provider.py`, `config.py`)
- **Default calm tone injection.** A configurable `sleep_default_tone` (default
  `soothing`) is applied to every sleep chunk that doesn't already open with an
  author tag, so untagged prose still lands calm (v3 → inline `[calm]`; v2 → numeric
  profile). Reconciled the v2 `soothing` profile to warm-steady (`stability 0.72`),
  not over-stabilized. (`orchestrator.py`, `elevenlabs_provider.py`)
- **`[pause:N]` is now real.** The guide documented `[pause:800]` but the code
  dropped it (v2 stripped it; v3 sent the literal unrecognized tag). Now: v2
  rewrites it to a native `<break time>` (capped at the API's 3 s); v3/local split
  on it and splice real silence (`sleep_text.split_pauses`,
  `sleep_pause_marker_max_ms`). Number-spelling was taught to leave the marker's
  digits alone. (`sleep_text.py`, `orchestrator.py`, `elevenlabs_provider.py`)
- **"Light and slow" ambient bed.** The bed is now band-limited
  (high-pass + low-pass) so it sits softly behind the voice, looped with a
  crossfaded seam (`build_looped_bed`) so loop points don't click, and optionally
  sidechain-**ducked** under the narration so it dips while the voice speaks. New
  `ambient_*` knobs. (`ambient.py`, `config.py`, `orchestrator.py`)
- **Prompting guide rewrite.** Added a role/system frame and an explicit v2/v3
  engine branch; corrected the tag vocabulary to tags v3 actually performs
  (`[calm]`, `[warm]`, `[sighs]`/`[exhales]` — dropped the non-native `[soothing]`
  inline recommendation); documented `[pause:N]` accurately; added the
  ellipsis/dash micro-pause technique (the only in-line pause on v3).
  (`docs/prompting_guides/elevenlabs_sleep.md`, design spec under `specs/`)

Trade-offs: Natural v3 is slightly less locked-down than Robust, but the ramp-down
+ default calm tone + mastering keep it steady; v2 remains the pick for maximum
long-form consistency. Ducking and native breaks are config-gated (default on).

## 2026-06-20 — Phase 7: ElevenLabs podcast quality — v3 continuity, PCM intermediates, tuning

Addressed voice drift, irregular pronunciations, mid-sentence tone changes, and
harshness in ElevenLabs podcast output. Five root-cause fixes:

- **v3 continuity context enabled.** `previous_text`/`next_text` were only
  injected for v2 — v3 (the default podcast model) got no cross-chunk prosody
  context, causing voice drift. Moved continuity injection out of the v2-only
  branch so both generations benefit. (`elevenlabs_provider.py`)
- **Lossless PCM intermediates.** Changed the ElevenLabs segment format from
  `mp3_44100_128` to `pcm_44100` to eliminate double-encode quality loss.
  Added raw-PCM decoding in `stitcher.bytes_to_segment` and a per-provider
  format override (`elevenlabs_segment_format`) so other providers keep their
  defaults. (`stitcher.py`, `config.py`, `orchestrator.py`)
- **Chunk size reduced from 2400 to 1000 chars.** Community consensus and API
  research show >2000 chars causes pacing drift within a single ElevenLabs call.
  Trade-off: ~2.4× more API calls per job (priced per character, not per
  request, so no cost increase). (`config.py`, `chunker.py`)
- **Speed jitter removed for cloud providers.** The ±3% per-chunk speed variance
  was designed for local models; on ElevenLabs each chunk regenerates from
  scratch, so jitter fought the model's own prosody. Cloud providers now use the
  fixed base speed; local models keep jitter. (`orchestrator.py`)
- **v3 similarity_boost tuned from 0.85 to 0.80.** Aligned with the v2
  research-validated podcast baseline; 0.85 was too aggressive and contributed
  to harshness. (`elevenlabs_provider.py`)

## 2026-06-19 — Phase 6: Podcast branding — series, intro/outro music, prompting guides

Added branded podcast series with signature intro/outro music and split the
ElevenLabs prompting guide into podcast and sleep story variants. Spec:
`docs/superpowers/specs/2026-06-19-podcast-branding-intro-outro-design.md`.

- **Series configuration system.** JSON configs in `assets/series/<slug>.json`
  define a branded podcast series (show name, speaker persona names, music
  references, gain/fade settings). Discovered by `series_registry.scan`, listed at
  `GET /api/series`, selectable in the frontend's Speakers panel.
- **Script section markers.** `[INTRO]`, `[BODY]`, `[OUTRO]` on their own line in
  the script. The parser annotates each `ScriptTurn` with a `section` field.
  Without markers, all turns default to "body" — fully backward compatible.
- **Intro/outro music mixing with volume envelopes.** Each series has separate
  intro and outro music files (~30 s). The mixer applies a multi-stage volume
  envelope via `volume` eval=frame: **intro** has a 10 s music-only pre-roll at
  full volume (-12 dB), fading to background (-22 dB) as speech starts; **outro**
  has quiet music under speech that swells to full when speech ends, then plays
  solo for 15 s before fading out. All timing is configurable per series and
  adapts to variable speech duration. Body stays purely vocal.
- **Prompting guide split.** Replaced the unified `elevenlabs.md` with two
  specialized guides: `elevenlabs_podcast.md` (highly tuned for branded podcast
  scripts — section markers, intro/outro structure, emotional arc, v3 tag best
  practices, series-aware INPUTS) and `elevenlabs_sleep.md` (single-narrator sleep
  prose — rhythm, imagery, progressive calm, tone guidance). Updated README routing
  table to distinguish by content type + model.
- **`PodcastRequest.series`** — optional slug field. When set, the orchestrator
  loads the series config and applies music mixing. When unset, identical to
  previous behavior.

## 2026-06-19 — Phase 5: ElevenLabs expressive podcasts + calm sleep

Reworked the ElevenLabs path per two research briefs to make podcasts more
expressive and sleep stories calmer. ElevenLabs-only; local providers and the
sleep-vs-podcast processing boundary are unchanged. Spec:
`docs/superpowers/specs/2026-06-19-elevenlabs-expressive-podcast-calm-sleep-design.md`.

- **v3 is now the default** for both content types (`elevenlabs_podcast_model` /
  `elevenlabs_sleep_model` → `eleven_v3`); v2 stays selectable. The UI model
  dropdown lists v3 first. v3 performs inline audio tags, which drives the rest.
- **Model-aware tags.** Arbitrary `[bracketed]` cues (`[warmly]`, `[exhales
  softly]`, breaths) now pass through to v3 verbatim (performed); v2 strips all
  bracket tags before the read so they are never spoken. ElevenLabs now sets
  `accepts_inline_sfx=True` (superseding Phase 4's "no provider sets it" note), so
  breath/SFX tags stay in the text on the v3 path instead of becoming silences.
- **Cross-chunk continuity.** New `TTSProvider.accepts_continuity` flag (True on
  ElevenLabs). The orchestrator hands each chunk the trailing/leading text of its
  neighbours as `previous_text` / `next_text` (bracket tags stripped) so prosody
  flows across boundaries. An optional request `seed` rides along for reproducible
  re-renders. Both are top-level request-body fields, carried via `voice_settings`
  — no `synthesize` signature change.
- **`use_speaker_boost` + `apply_text_normalization`.** Every request now sends
  `use_speaker_boost` (configurable, default on — intimate proximity) and
  `apply_text_normalization` (default `"auto"` — spells numbers server-side).
- **Boundary smoothing.** `ffmpeg_stitch.segment_to_wav_file` applies a short
  equal-power edge fade (`chunk_edge_fade_ms`, default 8 ms) to each chunk WAV,
  removing concat-boundary clicks. Chosen over the research's 500 ms overlapping
  crossfade, which would break the constant-memory concat and muddy conversational
  turns / sleep pauses.
- **Tuned profiles.** v2 podcast `style` 0.45 → 0.0 (unforced dialogue); v2 sleep
  `stability` 0.88 → 0.70 (research sweet spot — warm, not a robotic drone); v3
  podcast `style` 0.5 → 0.0.
- **Sleep ramp-down + normalization.** New `SleepStoryRequest.ramp` (default on):
  per-chunk speed eases toward `baseline × sleep_ramp_speed_end_factor` (0.94) and
  inter-sentence pauses grow toward `sleep_ramp_pause_scale` (1.6) — a pure,
  deterministic function of chunk position. New `core/sleep_text.py` spells
  standalone integers before synthesis. Loudness retargeted to −18 LUFS /
  −2 dBTP (`sleep_target_lufs`, new `sleep_true_peak_db`). A "Progressive
  ramp-down" toggle was added to the sleep UI.

## 2026-06-19 — Phase 4: richer mindfulness markup (tone words + breath/SFX)

Wellness scripts want a gentler vocabulary than the original five tone tags, plus
a way to mark breaths. Both are now in the sanctioned podcast pacing layer — they
shape *timing and how words are spoken*, never meditation-style audio processing.

- **Tone words** — `core/emotion.py` adds `soothing`, `reflective`, `warm` to the
  recognized set (with speaking-rate multipliers for local models). ElevenLabs
  maps them too: calm-leaning `EMOTION_PROFILES` (v2) and `V3_AUDIO_TAGS` entries
  (v3). They flow through the existing per-provider `voice_settings` routing — no
  new code path.
- **Breath / SFX tags** — `[breath]`, `[deep_breath]`, `[sigh]` (with stand-in
  silence durations in `SFX_PAUSE_MS`). `text_processor.plan_turn` gained an
  `inline_sfx` flag: when False (every current provider) the tag is rewritten to a
  short `[pause:N]` so the beat lands and no model speaks the literal tag; when
  True the tag is left in the text for the model to perform.
- **New capability flag** `TTSProvider.accepts_inline_sfx` (default False) — the
  orchestrator passes it into `plan_turn` per the turn's provider, branching on
  the flag, not a provider name. The frontend `ScriptInput` legend now lists the
  new tags.

Scope note: the plan floated "CosyVoice3 instruct / EL v3 perform tags inline," but
reading the providers showed CosyVoice3's delivery is instruct-driven (no inline
tags) and ElevenLabs' inline-tag support is v3-only (a per-request distinction the
class-level flag can't express, and whose exact tag vocabulary isn't verifiable
against the live API here). So no current provider sets `accepts_inline_sfx`; the
universal short-pause mapping is the shipped behavior, and the flag + pass-through
branch (unit-tested) stand ready for a future provider whose inline vocabulary is
confirmed. Sleep prose isn't markup-processed — these tags apply to podcasts.

## 2026-06-19 — Phase 3: reference-clip upload + hygiene (clone from the UI)

Cloning worked but reference clips were filesystem-only — you had to drop
`.wav`/`.txt` pairs into `assets/speakers/` by hand. Now you can upload a clip from
the UI and it's cleaned before it lands in the registry.

- **`core/ref_clean.py`** — clip hygiene pipeline: mono downmix → resample →
  energy-based silence trim → optional denoise (`noisereduce`) → length cap →
  WAV export. Baseline uses only pydub (a base dep), so upload works without any
  extra; denoise degrades to a no-op + note when the extra isn't installed. Each
  step returns a note for the UI.
- **`POST /api/voices/reference`** (multipart: `name`, `audio`, optional
  `transcript`) — cleans the clip and persists it via
  `reference_voice_registry.save()` to the existing
  `reference_audio/<slug>.wav` + `reference_text/<slug>.txt` layout, so **F5 and
  CosyVoice3 pick it up with no provider changes**. A transcript is required
  (cloners condition on it); if omitted we reuse the Phase 2 local Whisper
  (`qc.transcribe`) and return a clear 422 if that isn't available.
- **Registry** gained `slugify()` and `save()` (it owns the on-disk layout).
  New `ReferenceVoiceCreated` model. New settings `REFERENCE_CLIP_SAMPLE_RATE`
  (24 kHz) and `REFERENCE_CLIP_MAX_SECONDS` (30 s).
- **Frontend** — new `AddVoice` panel ("Clone a voice"): name + file + optional
  transcript, with per-step hygiene notes on success; `App` re-fetches `/api/voices`
  so the new voice appears in every dropdown.
- New optional extra: `uv sync --extra clean` (`noisereduce`).

Scope note: the shipped denoiser is `noisereduce` (reliable, light). DeepFilterNet3
(Doc A's CoreML/ANE suggestion) can slot into `_denoise` later behind the same
graceful-degradation contract; the energy-based silence trim stands in for a
learned VAD for now.

## 2026-06-19 — Phase 2: long-form drift QC (Whisper-WER + speaker similarity)

The two failure modes that creep into 30–90 min local renders — hallucinated/
dropped words and a cloned voice drifting off the reference timbre — are invisible
without listening to the whole thing. New opt-in QC checks both against the
rendered master.

- **`core/qc.py`** — pure WER scoring (markup strip → word normalize → edit
  distance) plus two lazy backends: transcription (prefers `mlx_whisper`, falls
  back to `faster_whisper`) and speaker similarity (`resemblyzer` partial
  embeddings vs the reference clip, windows below `qc_sim_threshold` flagged).
  Missing deps degrade to a `None` metric + a note — never a crash.
- **`QCReport`/`QCWindow`** added to `models.py`; `GenerateResult.qc` populated
  only when enabled. New settings: `ENABLE_QC` (default off), `QC_WHISPER_MLX_REPO`,
  `QC_WHISPER_FASTER_SIZE`, `QC_SIM_THRESHOLD`.
- **Orchestrator hook** — `run()` calls `_attach_qc` after the master is written
  (both content types). Speaker similarity runs only when exactly one cloned voice
  (f5/cosyvoice) is in play — sleep stories always, podcasts when a single distinct
  cloned voice is used. QC failures are caught and recorded in `qc.notes`, never
  failing a good render.
- New optional extra: `uv sync --extra qc` (`faster-whisper`, `resemblyzer`,
  `mlx-whisper` on macOS). Base install and `uv run pytest` stay clean — QC tests
  fake the ASR/encoder imports.

Design note: QC scores the **final master as a whole** (windowed for SIM) rather
than per turn — chunk WAVs are deleted after stitching, and whole-master windowing
catches gradual drift without reconstructing turn boundaries. Cost: it ~doubles a
job's wall-clock, hence opt-in.

## 2026-06-19 — Phase 1: long-form benchmark + Apple-Silicon perf hardening

The three local-TTS research reports all *assert* that 30–90 min local generation
is practical on an M1 Max but none measured it, and Doc A specifically warns about
the MLX buffer cache ballooning over long jobs and the first-inference Metal JIT
penalty. This phase makes both measurable and tunable.

- **`scripts/bench_longform.py`** — new benchmark (mirrors `bench_f5.py` /
  `bench_cosyvoice.py`). For each local provider it builds increasingly long
  narration (default 5/15/30 min; pass `--minutes 30 60`), chunks it exactly like
  the orchestrator, synthesizes every chunk, and reports chunk count, audio length,
  wall-clock, RTF, and peak RSS. ElevenLabs is excluded (cloud — measures nothing
  local, would bill calls). Hardware-gated: per-provider/length failures are
  reported and skipped.
- **MLX cache cap** — `CosyVoiceProvider` gained `cache_mb` and `_cap_mlx_cache()`,
  called once when the model loads. Best-effort across MLX releases (tries
  `mx.set_cache_limit` and `mx.metal.set_cache_limit`). New `MLX_CACHE_MB` setting
  (default `0` = MLX default / no cap).
- **Provider warmup** — `CosyVoiceProvider.warmup()` runs a silent dummy synthesis
  to pre-compile kernels off the first real generate. Wired into `bootstrap` behind
  the new `WARMUP_PROVIDERS` flag (default off). Best-effort: a missing MLX install
  or no reference voices just no-ops.

Decision deferred (hardware-gated): use the captured RTF plus `bench_cosyvoice.py`'s
A/B to decide whether to flip CosyVoice3 to the default sleep provider. Not
auto-flipped — Kokoro stays default until a human confirms the win on Apple Silicon.

## 2026-06-17 — Fix: CosyVoice3 produced no audio (version-mismatch in generate_audio)

`generate` failed with `[cosyvoice] no audio produced for voice 'Riley'`. Root
cause: the provider was written against `mlx-audio-plus`'s GitHub `main`, but the
pinned **0.1.8** release has a different `generate_audio` contract. Read the
installed source to find three mismatches and fixed all:

- **No `output_path` param.** 0.1.8 writes to `{file_prefix}.{audio_format}`
  relative to CWD, so the WAV landed in the working dir, not our temp dir → the
  file-not-found fallback raised "no audio produced". Fix: pass `file_prefix` as a
  full temp-dir path; drop `output_path`.
- **Instruct key is `instruct_text`, not `instruct`.** Our `instruct=` was
  swallowed into `**kwargs` and ignored, so Instruct Mode never activated.
- **`ref_text` outranks `instruct_text`.** `CosyVoice3.generate` branches
  zero-shot before instruct, so passing both ran zero-shot and dropped the
  directive. Fix: instruct mode now passes `instruct_text` and **omits**
  `ref_text`; zero-shot still passes `ref_text`. Also dropped the unsupported
  `seed` param.

Verified against the real model: Riley in instruct mode renders 16.5 s of audio
in 13.8 s (RTF 0.84). Also fixed both `scripts/bench_*.py` to add the backend dir
to `sys.path` so they run as documented (`uv run python scripts/bench_*.py`) — a
pre-existing import bug, not CosyVoice-specific.

## 2026-06-17 — CosyVoice3 (MLX) sleep-story provider with Instruct Mode

Synthesized three local-Apple-Silicon research reports against the codebase: the
app already had the chunking, disk stitching, EBU R128 mastering, ambient beds,
and voice cloning the reports recommend. The one genuine *sleep-quality* gap was
the TTS model — F5/Kokoro clone timbre but carry the reference clip's energy into
the output, so calm delivery isn't guaranteed over 30–90 min. Added **CosyVoice3
(MLX)** as a new opt-in provider whose flow-matching DiT **Instruct Mode**
decouples the cloned *timbre* from the *delivery*.

- **New `cosyvoice` provider** (`providers/cosyvoice_provider.py`). Apple-Silicon
  only via `mlx-audio-plus` (imports as `mlx_audio`), added as a `mlx` optional
  extra (`uv sync --extra mlx`) so non-Mac/CI installs and `uv run pytest` (fakes)
  stay clean. Heavy import is lazy (synthesis only); `list_voices` just scans the
  reference-voice assets, so the app boots and lists voices everywhere —
  failures surface as `ProviderError` + a per-provider error in `/api/voices`.
- **Instruct Mode wired into the sleep path.** New capability flag
  `TTSProvider.accepts_instruct`; `_sleep_voice_settings` injects an `instruct`
  directive (`cosyvoice_sleep_instruct`, overridable per story via
  `SleepStoryRequest.style_prompt`) for instruct-capable providers. Pacing rides
  the directive, **not** a numeric speed multiplier (`consumes_local_speed=False`)
  — the model's strength, no time-stretch artifacts. The Speed slider is ignored
  for CosyVoice3 (noted in the UI).
- **Reuses cloned-voice assets.** CosyVoice3 reads the same
  `reference_audio/*.wav` + `reference_text/*.txt` pairs as F5. Renamed
  `f5_voice_registry` → `reference_voice_registry` (shared), with
  `f5_voice_registry` kept as a thin re-export for back-compat. The transcript is
  always passed to `generate_audio`, which both conditions zero-shot cloning and
  skips mlx_audio's default ~1.5 GB Whisper auto-transcription of the reference.
- **Model:** `mlx-community/Fun-CosyVoice3-0.5B-2512-4bit` (~1.1 GB, 24 kHz),
  downloaded on first synthesis; loaded once and cached across chunks. New chunk
  budget `cosyvoice_chunk_chars=300` keeps chunks under the ~30 s ref window.
- **Opt-in, not default.** Kokoro stays the default sleep provider until
  `scripts/bench_cosyvoice.py` confirms an A/B win vs F5. Frontend adds CosyVoice3
  to the sleep provider dropdown + a "Delivery style" field bound to
  `style_prompt`.
- **Out of scope (sequenced follow-ups from the reports):** LLM script generation,
  full MLX migration of F5/Kokoro, ASR/drift QC, Pedalboard reverb.

## 2026-06-17 — Model-specific TTS: ElevenLabs v2/v3 + content tailoring, F5 runtime fix

The pipeline was provider-agnostic to a fault: one uniform `voice_settings` dict
for every model, no tailoring by content type, ElevenLabs locked to v2 with sleep
stories getting `voice_settings=None`, and F5 running MPS + float16 (18–20 min for
3 min of audio, with slurred/garbled words on this M1 Max). Split each model's
implementation so the backend applies that model's best practices, parameterized
by content type.

- **Provider capability flags (cross-cutting).** `TTSProvider` now declares
  `consumes_local_speed` (Kokoro/F5) and `has_native_speed` (ElevenLabs). The
  orchestrator branches on these instead of the old `_SPEED_AWARE = {"kokoro",
  "f5"}` name set — the structural "split per model" without name checks.
- **ElevenLabs tailored by model AND content type** (`elevenlabs_provider._prepare`).
  **v2:** numeric `stability/similarity_boost/style` — `EMOTION_PROFILES` for a
  tone tag, else a per-content base (`V2_CONTENT_BASE`: expressive podcast vs
  calm/high-stability sleep) — plus native `speed` (clamped 0.7–1.2). **v3:**
  discrete stability (Creative/Natural/Robust) + tone performed *inline*
  (`V3_AUDIO_TAGS`). Model is user-selectable per speaker / per sleep story
  (`SpeakerVoice.model_id`, `SleepStoryRequest.model_id`), defaulting to
  `ELEVENLABS_PODCAST_MODEL`/`ELEVENLABS_SLEEP_MODEL`.
- **Sleep stories on ElevenLabs now sound calm at the model level.** `_run_sleep`
  builds a calm `content_type="sleep"` profile + native slow speed (was `None`),
  so the voice narrates gently *before* the sleep mastering chain runs.
- **F5 runtime fix.** Replaced the hardcoded `device="mps"` + unconditional
  `float16` cast with config-driven `F5_DEVICE`/`F5_DTYPE`, defaulting to **CPU +
  float32** (float16-on-MPS was the documented cause of the garbling; MPS is now
  opt-in and sets `PYTORCH_ENABLE_MPS_FALLBACK=1`). Inference runs under
  `torch.inference_mode()`; CPU path sets thread count. `nfe_step` 32→16 (~halves
  latency), `F5_CHUNK_CHARS` 350→250 (further from the ~30s garble edge).
  `sway_coef=-1.0`/`cfg=2.0` kept (correct F5 defaults). Added `scripts/bench_f5.py`
  to time CPU-fp32 vs MPS-fp32 and pick the host default.
- **Reference transcripts were not a bug.** The four shipped voices intentionally
  read the same script, so identical `reference_text/*.txt` correctly match their
  `.wav`s — documented the contract (identity comes from the audio).
- **Docs/guides:** `elevenlabs.md` gained a v2-vs-v3 section + v3 inline audio-tag
  note; `f5.md` + ARCHITECTURE document the reference contract and local runtime;
  prompting-guides README, `.env.example`, and README updated.

Trade-offs: v3 needs ElevenLabs account access and caps at 5k chars/request
(under our chunk budget). F5 on Apple Silicon is CPU-bound by default — reliable
and far faster than the broken MPS-fp16 path, but a real GPU/MPS win is left to
the per-host benchmark.

## 2026-06-16 — Lifelike podcasts: conversational pacing + voice emotion

Podcasts sounded robotic: each turn was synthesized as one flat block, the only
silence was a fixed 400 ms inter-turn gap, and `voice_settings` was always `None`.
Added a provider-agnostic conversational layer so podcasts breathe and vary like
real dialogue, plus an optional inline tag vocabulary for authored control.

- **New `core/text_processor.py`** turns a parsed turn into ordered `Speech`/`Pause`
  plan items: sentence-boundary splitting with a *randomized* intra-sentence
  micro-pause (default 80–220 ms), explicit `[pause:600]` / `[pause:600ms]` tags,
  and a leading tone tag (`[excited]`/`[calm]`/`[sad]`/`[whispering]`/`[neutral]`)
  lifted off the text and attached as `emotion`. Byte-budget splitting is still
  delegated to `chunker.chunk_text`. Recognized tags are stripped so no provider
  ever speaks them; unknown `[...]` tags pass through unchanged as before.
- **`orchestrator._run_podcast`** now drives planning through `text_processor`,
  inserts variable inter-turn gaps (±`podcast_turn_gap_jitter`) and the per-chunk
  micro-pauses, and builds `voice_settings={"emotion", "speed"}` per chunk (speed
  jitter only for the speed-aware local providers). The RNG is seeded from
  `job_id` so a job renders **deterministically** and tests are stable.
- **Emotion is per-provider, signature unchanged.** New `core/emotion.py` holds
  the shared tag vocabulary + emotion→speed multipliers (Kokoro/F5 multiply it
  into their rate); ElevenLabs maps the same tag to a native
  `stability/similarity_boost/style` profile (`EMOTION_PROFILES`) and drops the
  local-only `speed`/`emotion` keys before calling the API.
- **`PodcastRequest.pacing` (default `True`)** gates the whole thing; `pacing=False`
  reproduces the exact legacy flat render (one block per turn, fixed gap, no
  emotion). New `config.py` knobs: `podcast_default_speed`, `podcast_speed_jitter`,
  `podcast_intra_sentence_gap_ms_min/max`, `podcast_turn_gap_jitter`.
- **Frontend:** a "Natural pacing" toggle and an inline-tag legend under the
  script box (`ScriptInput.tsx`), wired through `App.tsx`/`types.ts`.

Decisions & trade-offs:
- **Sanctioned exception to the "no podcast processing" rule, scoped narrowly:**
  pacing + voice-emotion only. Loudness normalization, EQ, compression, fades, and
  ambient beds stay **sleep-only** — podcasts never touch `sleep_post`/`ambient`.
  CLAUDE.md updated to record the carve-out.
- **Tone via `voice_settings`, not performed inline tags.** ElevenLabs only
  *performs* `[laughs]`/`[sighs]`/`[excited]` on `eleven_v3`; the app defaults to
  `eleven_multilingual_v2`, so tone is delivered through voice-settings profiles
  (which work on v2) and tags are stripped from the spoken text. `eleven_v3`
  opt-in, F5 emotional reference-clip swapping, and a laugh/sigh expression-clip
  library are deferred (see the design spec).

## 2026-06-15 — Frontend redesign: token-driven design system

Rebuilt the frontend's visual layer into a modern, cohesive design system
("Calm Studio") without touching any app logic, state, or API calls. Driven via
the UI/UX Pro Max skill's `--design-system` recommendation (wellness palette:
lavender + mint; Lora/Raleway pairing), adapted to the app's dark-first studio
context.

- **One source of truth for styling.** `src/styles/index.css` is now fully
  token-driven: every color, spacing step (4/8 rhythm), radius, shadow, motion
  curve, and font is a `:root` custom property, and components reference tokens
  rather than raw hex. Restyling the whole app is now a token edit.
- **Real iconography, no emoji.** Added `components/Icon.tsx` — a single
  stroke-based SVG set (Lucide-derived, `currentColor`) — and replaced every
  emoji (🎙️ 🌙 ⬇) used as a structural glyph in the header, content tabs, panel
  headers, CTA, and download links. Emoji render inconsistently across platforms
  and can't be themed; SVG fixes both.
- **Polish + accessibility.** Visible `:focus-visible` rings on all controls,
  custom themed `select` chevrons and range thumbs, an animated progress sheen,
  `role="progressbar"`/`role="alert"` semantics, a responsive single-column
  collapse under 560px, and a global `prefers-reduced-motion` override.
- **Why dark-first, not the skill's light neumorphism.** The skill flagged
  neumorphism's low contrast; the app is a "studio" tool, so we kept the dark
  surface model but folded in the recommended lavender/mint ramp and serif/sans
  pairing for a calmer, more modern feel that still clears 4.5:1 contrast.
- **Scope:** pure presentation. No component contracts, props, or backend calls
  changed; `tsc && vite build` passes and both content-type flows were verified
  in a live preview. Added `.claude/launch.json` so the frontend can be previewed
  with one command.

## 2026-06-15 — Single-command dev launcher (`dev.sh`)

Added a root `dev.sh` so the app starts with one command instead of running the
backend and frontend in two terminals. It launches `uv run uvicorn … --reload`
and `npm run dev` as child processes, streams both logs to one terminal, and on
Ctrl-C tears down the whole process tree.

- **Why a script, not a new dependency.** The repo mixes Python (uv) and Node
  (npm); a plain bash launcher needs nothing installed beyond what's already
  there (no `concurrently`/root `package.json`). The frontend still proxies
  `/api` → `:8000`, so nothing about the runtime topology changed — this is dev
  ergonomics only.
- **Teardown kills descendants, not just the tracked children.** `uvicorn`'s
  `--reload` spawns a worker and `npm` spawns `vite`; neither forwards signals,
  so killing the tracked parent alone orphans them (verified: orphaned listeners
  left holding `:8000`/`:5173`). `dev.sh` recurses with `pgrep -P` and kills
  leaves first. Confirmed clean teardown — no surviving processes, both ports
  freed.
- **macOS bash 3.2 compatibility.** Avoided `wait -n` (bash 4+) in favor of a
  poll loop, and dropped a `set -m` process-group approach that was unreliable
  in non-tty contexts.
- **Note:** Ctrl-C in a real terminal triggers the trap correctly. Launching the
  script with `&` from a non-interactive shell makes SIGINT un-trappable (POSIX
  async-child rule), but that's a background-launch artifact, not the Ctrl-C
  path; the trap also catches SIGTERM.

## 2026-06-15 — Async pipeline overhaul + Sleep Stories content type

Two coordinated changes: a model-agnostic architecture overhaul that fixes
long-content generation, and a net-new **Sleep Stories** content type.

### Architecture overhaul (both content types)

- **Async jobs.** New `POST /api/jobs` (discriminated `podcast`/`sleep_story`
  body) returns a `job_id` immediately; work runs in a single-slot thread pool
  (`max_workers=1`) off the event loop. Progress via SSE
  (`GET /api/jobs/{id}/events`, `sse-starlette`) and polling
  (`GET /api/jobs/{id}`). The legacy synchronous `POST /api/generate` stays as a
  thin adapter over the new orchestrator, so existing callers/tests are unaffected.
- **Per-provider chunking** (`core/chunker.py`): sentence-aware, character-based
  budgets (Kokoro 400 / F5 350 / ElevenLabs 2400) keep each call under Kokoro's
  510 phoneme-token cap and F5's ~30s/pass. Pure module, no ML imports.
- **Disk-based stitching** (`core/ffmpeg_stitch.py`): each chunk is written to a
  temp WAV and concatenated with the ffmpeg concat demuxer — constant memory, no
  `MemoryError` on 30–45 min output. Replaces in-memory pydub concat on the async
  path (`stitcher.stitch` retained for the legacy path + its tests).
- **`engine.generate` is now a shim** over `core/orchestrator.run`, the single
  generation engine for both content types.

### Sleep Stories (single-speaker, plain prose)

- New `SleepStoryRequest`: paste plain prose (no `[Speaker]` tags), one
  provider + voice, with `speed` (default 0.85), inter-sentence `pause_ms`
  (default 900), and an optional ambient bed.
- **Calming post-processing** (`core/sleep_post.py`, ffmpeg): gentle compression
  → low-pass roll-off → EBU R128 `loudnorm` → fade in/out → **44.1 kHz stereo**.
- **Ambient beds** (`core/ambient.py` + `storage/ambient_registry.py`): files in
  `assets/ambient/*.{wav,mp3}` are looped/trimmed to the story length, pulled
  ~22 dB under the voice, faded, and `amix`ed under the narration. Listed at
  `GET /api/ambient`.
- **Per-job speed** rides the existing `voice_settings` dict — `KokoroProvider`
  and `F5Provider` read `voice_settings["speed"]` (one-line change each), so the
  `TTSProvider` signature is unchanged and ElevenLabs never receives the key.

### Frontend

- Content-type toggle (`ContentTypeSelector`); Sleep config (`SleepStoryConfig`:
  single voice, speed/pause sliders, ambient picker, prose textarea with
  word-count/duration hint); live `ProgressBar` driven by the SSE stream
  (`api/jobs.ts`). Podcasts reuse `SpeakerConfig`/`ScriptInput` and now also run
  through the async job flow.

### Decisions / trade-offs

- **Sanctioned exception to "no meditation processing."** The rule still holds
  for podcasts; the calming treatment applies to sleep stories only. CLAUDE.md
  updated to record the boundary.
- **No model-lineup changes** (no Chatterbox, no F5 demotion); Kokoro's
  CPU-on-Apple-Silicon default is kept and documented.
- **Char-based chunk budgets** instead of "tokens": Kokoro's limit is phonemized
  tokens, which track characters, not BPE tokens — char budgets are safe and need
  no tokenizer dependency.
- **Concurrency capped at 1** so two heavy local models never co-load (OOM guard);
  parallel jobs are serialized.
- **In-memory job store** (no DB): single-user local app; jobs clear on restart,
  output files persist for download.

### Docs & testing

- Added `sse-starlette`; new sleep/chunking/ambient config in `config.py` +
  `.env.example`; `assets/ambient/` scaffold + README.
- Tests: 39 → 77 (chunker, job store, orchestrator podcast+sleep, jobs API incl.
  SSE, ambient registry, sleep filtergraph, per-job speed threading). No model
  downloads; real-ffmpeg tests gated on ffmpeg presence.
- Updated `ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, and added a design spec.

## 2026-06-15 — Add Kokoro + F5 TTS providers

Added two local TTS models behind the existing provider abstraction so a user
can pick **any of the three models per speaker** and mix them in one episode.

- **New providers** (core text→audio path only — no meditation processing copied
  from the source repo):
  - **Kokoro** (`kokoro_provider.py`): 11 static built-in voices; lazy
    `KPipeline` (CPU on Apple Silicon, a second pipeline for British voices).
    Validated end-to-end (real 24kHz render).
  - **F5** (`f5_provider.py` + `f5_voice_registry.py`): zero-shot voice cloning;
    voices discovered from `assets/speakers/reference_audio/*.wav` +
    `reference_text/*.txt` pairs; lazy `F5TTS` model with cached per-voice
    reference preprocessing.
- **Interface change:** `TTSProvider.synthesize` now returns a pydub
  `AudioSegment` (was raw `bytes`), unifying cloud encoded-bytes with local numpy
  output. Added `stitcher.numpy_to_segment` and sample-rate normalization in
  `stitch` (default target 44.1kHz) so mixed-provider episodes concatenate cleanly.
- **Voices API** is now provider-grouped and resilient (`list[ProviderVoices]`):
  one provider failing (no ElevenLabs key, empty F5 assets, missing ML lib) no
  longer breaks the others.
- **Frontend:** each speaker row gained a **model** dropdown + a voice dropdown
  filtered to the chosen provider; provider errors show inline.
- **Decisions:**
  - Install all three models by default (no optional extra) — user wants every
    model available at launch.
  - **Pin backend to Python 3.13.** Kokoro/F5 pull in `spacy`, which has no
    cp314 wheels; 3.13 has wheels for the whole stack (torch 2.12, spacy 3.8).
    `requires-python` set to `>=3.11,<3.14`.
  - Heavy ML imports kept lazy (registration + `list_voices` never import torch).
  - F5 references require a matching `.txt` transcript (no Whisper fallback);
    assets mirror the source meditation repo's two-folder layout.
  - Local models default to speed 1.0 (normal podcast pace, not meditation 0.90).
- **Docs:** added `docs/ARCHITECTURE.md`, this changelog, and `CLAUDE.md` with a
  mandatory documentation-discipline rule for future sessions.
- Tests: 26 → 39 (local providers via injected fake modules; mixed-rate
  stitching; resilient grouped voices). README updated for the three models +
  assets.

## 2026-06-15 — Initial scaffold

Greenfield FastAPI + React monorepo to turn a multi-speaker script into a
stitched podcast episode via pluggable TTS providers.

- **Decisions:** full-stack web app; TTS-only scope (script in → audio out);
  FastAPI + React/Vite stack; synchronous generation, minimal persistence
  (files on disk, no DB), single-user, no auth; provider abstraction with
  ElevenLabs as the first implementation; output = lossless-stitched WAV master
  + optional MP3 320 (MP4 deliberately skipped); `audioop-lts` added for
  pydub on Python 3.13+.
- Backend: `TTSProvider` + registry, script parser, audio engine, pydub/ffmpeg
  stitcher, synchronous generate + download API. Frontend: speaker config, voice
  dropdowns, script input, player/download. 26 passing tests.
