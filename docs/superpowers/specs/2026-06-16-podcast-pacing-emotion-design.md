# Design: Lifelike conversational pacing & emotion for podcasts

**Date:** 2026-06-16
**Status:** Implemented (Phase 1 + 2)

## Problem

Podcast output was technically correct but robotic. Every turn was synthesized as
one flat block; the only silence was a fixed `INTER_TURN_GAP_MS=400` between
speaker turns; `voice_settings` was always `None` for podcasts. Real conversation
has micro-pauses between sentences, slight pace variation, varied gaps at
hand-offs, and tonal shifts. Goal: make podcasts feel like genuine multi-person
dialogue without turning them into sleep-story-style meditation tracks.

## Decisions (from brainstorming)

1. **Providers:** mixed — ElevenLabs (cloud) + Kokoro/F5 (local). Emotion handled
   per-provider.
2. **Control model:** automatic pacing baseline (no script changes) **plus**
   optional authored inline tags.
3. **Expressions** (laughs/sighs/"hmm"): **out of scope** for now. Pacing + tone
   only. (Clip library deferred — Phase 3.)
4. **Processing scope:** sanctioned exception to the "no podcast processing" rule
   for **pacing + voice-emotion only**. Loudness normalization, EQ, compression,
   fades, and ambient beds remain **sleep-only**.

## Architecture

No `synthesize()` signature change — per-job tuning rides `voice_settings`
(existing repo convention).

- **`core/text_processor.py`** (new, pure): `plan_turn(text, *, provider,
  max_chars, rng, gap_min_ms, gap_max_ms) -> list[Speech | Pause]`. Extracts a
  leading tone tag, splits on `[pause:N]`, sentence-splits each span with a
  randomized intra-sentence gap, and delegates byte-budget splitting to
  `chunker.chunk_text`. Recognized tags are stripped; unknown `[...]` passes
  through. RNG is injected for determinism.
- **`core/emotion.py`** (new, pure): the fixed tone vocabulary
  (`excited/calm/sad/whispering/neutral`) + `EMOTION_SPEED` multipliers +
  `speed_multiplier(emotion)`.
- **`orchestrator._run_podcast`**: when `request.pacing` (default `True`), builds
  an ordered `_Speech`/`_Silence` op list via `_build_podcast_ops`, inserts
  variable inter-turn gaps (`±PODCAST_TURN_GAP_JITTER`) and per-chunk micro-pauses,
  and constructs per-chunk `voice_settings={"emotion", "speed"}` (speed jitter for
  speed-aware providers only). RNG seeded from `job_id` → deterministic renders.
  `pacing=False` keeps the exact legacy flat path.
- **Providers** interpret their own keys: Kokoro/F5 multiply `emotion` into rate
  via `core/emotion.py`; ElevenLabs translates `emotion` → `EMOTION_PROFILES`
  (`stability/similarity_boost/style`) and drops local-only keys.
- **Config** (`config.py` / `.env.example`): `PODCAST_DEFAULT_SPEED`,
  `PODCAST_SPEED_JITTER`, `PODCAST_INTRA_SENTENCE_GAP_MS_MIN/MAX`,
  `PODCAST_TURN_GAP_JITTER`.
- **API/Frontend:** `PodcastRequest.pacing: bool = True`; a "Natural pacing"
  toggle + inline-tag legend under the script box.

## Script tag format

```
[Speaker 1]: That's a great point. [pause:500] I hadn't thought of it that way.
[Speaker 2]: [excited] Right?! The data totally surprised me too.
```

- `[pause:600]` / `[pause:600ms]` — explicit silence.
- `[excited]` `[calm]` `[sad]` `[whispering]` `[neutral]` — tone for the rest of
  the line (rate offset for local; native voice settings for ElevenLabs).

## Why tone via `voice_settings`, not performed inline tags

ElevenLabs only *performs* inline tags like `[laughs]`/`[excited]` on `eleven_v3`;
the app defaults to `eleven_multilingual_v2`. So tone is delivered through
voice-settings profiles (which work on v2) and recognized tags are stripped from
the spoken text. `ELEVENLABS_MODEL_ID` already exists for a future v3 opt-in.

## Out of scope (Phase 3, future)

- `eleven_v3` opt-in for performed inline expressions.
- F5 emotional reference-clip swapping (per-emotion reference voices).
- Pre-recorded expression-clip library (`assets/expressions/`) for laughs/sighs,
  spliced provider-agnostically in the stitcher.

## Verification

- Unit tests: `text_processor` (tag extraction/stripping, `[pause:N]`, sentence
  gaps in range, budget delegation, determinism), provider emotion mapping
  (Kokoro speed multiplier, ElevenLabs profile), orchestrator podcast path
  (emotion + jittered speed in `voice_settings`, determinism per `job_id`,
  `pacing=False` legacy parity). All via network-free fakes.
- Manual: a 2-speaker script (one ElevenLabs + one Kokoro voice) with `[pause:800]`
  and `[excited]`/`[calm]` — confirm audible sentence pauses, varied turn gaps, and
  tone shift, and that it is not mastered/meditative. Toggle pacing off for parity.
