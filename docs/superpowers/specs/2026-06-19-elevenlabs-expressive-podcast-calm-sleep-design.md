# ElevenLabs Improvement: Expressive Podcasts + Calm Sleep Stories

**Date:** 2026-06-19
**Status:** Approved, in implementation
**Scope:** ElevenLabs provider path only. Local providers (Kokoro, F5, CosyVoice3) and the
sanctioned sleep-vs-podcast processing boundary are untouched.

## Context & motivation

The app already has a mature ElevenLabs integration (v2/v3 per speaker, a tone-tag system,
native speed, conversational pacing, sleep mastering). Two research docs — *ElevenLabs Sleep
Story Optimization* and *AI Mindfulness Podcast Generation* — recommend concrete upgrades the
current code lacks. The goal is **more expressive multi-speaker podcasts** and **calmer, more
soothing sleep stories**, without violating any existing convention.

## Design decisions (confirmed with user)

1. **Default model → `eleven_v3`** for both content types; `eleven_multilingual_v2` stays
   selectable in the UI as a stable fallback.
2. **Audio tags: passthrough + expanded curated set.** Arbitrary `[bracketed]` tags pass through
   to v3 verbatim (writers can use `[warmly]`, `[soft laugh]`, `[exhales softly]`, …); v2 strips
   them (it cannot perform them). The curated emotion→profile map is expanded to cover every
   label in `emotion.EMOTIONS`.
3. **Continuity + boundary smoothing.** `previous_text`/`next_text` give the model cross-chunk
   prosodic context; short edge micro-fades remove zero-crossing clicks at chunk boundaries.
4. **Sleep ramp-down + number normalization.** Speed gently decelerates and pauses lengthen across
   the story; numbers are spelled out.

## Architecture

All new per-job parameters ride the existing `voice_settings` dict — the `synthesize` signature is
**not** changed (per CLAUDE.md). The orchestrator continues to branch on provider **capability
flags**, never on provider names.

### Provider (`elevenlabs_provider.py`)
- `_prepare_v2` / `_prepare_v3` always set `use_speaker_boost` (configurable default `True`).
- `synthesize_bytes` adds `apply_text_normalization` (default `"auto"`) and optional `seed` to the
  request body.
- `previous_text` / `next_text` hints are popped from `voice_settings` and forwarded as top-level
  request-body fields.
- **Model-aware tags:** v3 keeps inline `[...]` tags (performed); v2 strips all bracket tokens from
  the text via `_strip_bracket_tags`. The recognized leading emotion still maps to a v2 numeric
  profile / v3 inline tag.
- `EMOTION_PROFILES` (v2) and `V3_AUDIO_TAGS` (v3) cover every `emotion.EMOTIONS` label; a test
  guards against drift.
- Tuned base profiles: podcast `style → 0.0`; sleep `stability → ~0.70`.

### Capability flags (`base.py`)
- `accepts_continuity: bool = False` → `True` on ElevenLabs (drives `previous_text`/`next_text`).
- `accepts_inline_sfx: bool = False` → `True` on ElevenLabs (keeps breath/SFX tags in text for v3).

### Orchestrator (`orchestrator.py`)
- Builds `previous_text`/`next_text` from adjacent **speech** chunks (≤200 chars, bracket tags
  stripped) and injects them only when `provider.accepts_continuity`. Podcast path adds the fields
  to `_Speech` in a post-pass over the ops list; sleep path reads neighbors in the render loop.
- Passes `inline_sfx=provider.accepts_inline_sfx` into `text_processor.plan_turn`.
- Sleep **ramp-down** (when `request.ramp`): per-chunk
  `speed = baseline * lerp(1.0, sleep_ramp_speed_end_factor, frac)` and
  `pause = round(pause_ms * lerp(1.0, sleep_ramp_pause_scale, frac))`, `frac = i/max(1, total-1)`.
  Pure function of index — deterministic, no RNG. `ramp=False` reproduces today's fixed values.
- Threads optional `seed` from the request into voice_settings.

### Boundary smoothing (`ffmpeg_stitch.py`)
The literal 500 ms pydub crossfade from the research overlaps adjacent audio and loads the whole
episode into RAM — incompatible with this app's constant-memory ffmpeg-concat path, wrong for
conversational turns (muddies speaker boundaries), and moot for sleep (chunks are separated by
intentional pauses). Instead, `segment_to_wav_file` applies a short equal-power edge fade
(`chunk_edge_fade_ms`, default 8 ms; 0 = off) to each chunk WAV, eliminating the click artifacts a
crossfade targets while preserving streaming concat. Silence WAVs are unaffected.

### Number normalization (`core/sleep_text.py`, new)
Dependency-free helper spells standalone integers to words, applied to `prose_text` before chunking
in `_run_sleep`. Complements the server-side `apply_text_normalization="auto"`. Punctuation-for-
prosody stays an authoring concern (documented in the prompting guide), not a pipeline rewrite.

### Models (`models.py`)
- `SleepStoryRequest.ramp: bool = True`.
- `seed: int | None = None` on `PodcastRequest` and `SleepStoryRequest`.

### Config (`config.py`)
- `elevenlabs_podcast_model` / `elevenlabs_sleep_model` default → `"eleven_v3"`.
- `elevenlabs_use_speaker_boost: bool = True`, `elevenlabs_text_normalization: str = "auto"`.
- `chunk_edge_fade_ms: int = 8`.
- `sleep_target_lufs: -18.0`, `sleep_true_peak_db: -2.0`.
- `sleep_ramp_speed_end_factor: float = 0.94`, `sleep_ramp_pause_scale: float = 1.6`.

### Frontend
- `types.ts`: `eleven_v3` first in `ELEVENLABS_MODELS` (UI default); add `ramp` + optional `seed`.
- `SleepStoryConfig.tsx` + `App.tsx`: "Progressive ramp-down" checkbox (default on).

## Testing
- Unit (fakes, no model downloads): provider body fields, v2 tag-strip / v3 tag-keep, continuity
  forwarding, expanded emotion maps, tuned profiles; orchestrator continuity gating, `inline_sfx`
  passthrough, deterministic monotonic sleep ramp, `ramp=False` legacy; new `sleep_text` cases.
- E2E (needs `ELEVENLABS_API_KEY`): expressive v3 podcast with rich tags; calm v3 sleep with
  ramp + ambient; v2 fallback confirming tags aren't spoken.

## Out of scope (YAGNI)
WebSocket/streaming, biometric loops, `text_to_dialogue` endpoint (sequential stitching already
avoids the #677 speaker-mixing bug), literal overlapping crossfade, pronunciation-dictionary
subsystem.
