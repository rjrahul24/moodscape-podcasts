# ElevenLabs Sleep-Story TTS Quality — Design

**Date:** 2026-06-20
**Status:** Implemented
**Scope:** Sleep stories + ElevenLabs only. Podcasts are untouched.

## Problem / motivation

The reference meditation project `moodscape-mix-lib` produces noticeably better
ElevenLabs output than the sleep path here. A side-by-side review showed the two
already share the strong fundamentals — `eleven_v3`, stability `0.5` ("Natural",
which keeps inline tags responsive), and speaker boost. The reference's edge is
**pipeline hygiene** and **anti-drift tagging**, not the base voice settings.

Two reference techniques were absent here and are ported:

1. **Lossless pipeline** — pull PCM from ElevenLabs instead of a lossy MP3
   intermediate, and LUFS-normalize each chunk *before* stitching so v3's
   cross-chunk loudness drift doesn't survive into the master.
2. **Anti-drift tagging** — reassert a `[slowly]` pacing tag on every v3 chunk
   (the reference's biggest fix against v3 drifting toward an "audiobook
   narrator" read on long stories) and optionally inject sentence-boundary
   ellipses for breathing room.

### Decisions
- **Rollout:** character-altering changes (pacing tag, ellipsis) ship
  **config-gated, defaults preserved** — new knobs default to today's behavior;
  the operator flips them on to A/B. Pure-quality changes (PCM, per-chunk
  normalization) default on.
- **No overlapping crossfade engine.** The sleep path already splices real
  silence between consecutive chunks (`orchestrator._run_sleep`), so seams are
  mostly silence-separated. A crossfade would fight the constant-memory concat
  demuxer for little gain. The existing `chunk_edge_fade_ms` (8 ms) seam fade is
  kept; per-chunk normalization is the higher-value seam fix (level drift is
  audible even across silence).
- v3 already correctly withholds `previous_text`/`next_text` (only v2 sends
  them) — no continuity bug to fix.

## Changes

### 1. Higher-quality intermediate (PCM gated by plan tier)
`elevenlabs_segment_format` stays at `mp3_44100_192` (the best format the Creator
tier offers). Lossless `pcm_44100` (matches `sleep_sample_rate`, no resample) is
fully supported — `bytes_to_segment` already decodes raw `pcm_*` — but **requires
an ElevenLabs Pro plan**, so it's an opt-in (`ELEVENLABS_SEGMENT_FORMAT=pcm_44100`)
rather than the default. The target account is on Creator tier, so the default
stays MP3.

### 2. Per-chunk LUFS normalization before stitching (default on)
`ffmpeg_stitch.normalize_loudness(in, out, *, target_lufs, sample_rate,
true_peak_db)` — single-pass `loudnorm`. The orchestrator normalizes each speech
chunk (to `sleep_chunk_norm_lufs`, −21 LUFS) before the concat; the −18 LUFS
master pass then sets the absolute level. Chunks under `sleep_chunk_norm_min_ms`
(400 ms) are skipped so near-silent fragments aren't amplified. Output is
re-pinned to the sleep sample rate because `loudnorm` upsamples to 192 kHz
internally (would otherwise break the concat demuxer — caught during verification).

New config: `sleep_chunk_normalize` (bool, on), `sleep_chunk_norm_lufs` (−21.0),
`sleep_chunk_norm_min_ms` (400).

### 3. v3 pacing-tag reassertion (default OFF)
`elevenlabs_sleep_v3_pacing_tag` (empty = off). `_prepare_v3` builds the inline
prefix as emotion-tag-then-pacing-tag (`[calm] [slowly] …`) for `content_type ==
"sleep"`, reasserted on every chunk. Threaded through `bootstrap.py` as a provider
field, mirroring `sleep_v3_stability`.

### 4. Sentence-boundary ellipsis injection (default OFF)
`sleep_text.inject_sentence_pauses(text)` inserts `…` at sentence boundaries that
lack one, never inside a `[…]` cue, leaving existing ellipses/em-dashes alone.
`orchestrator._run_sleep` applies it after `spell_numbers`, before chunking, only
for `provider == "elevenlabs"` when `sleep_sentence_ellipsis` is on.

## Files
- `backend/app/config.py` — new knobs + PCM default.
- `backend/app/core/ffmpeg_stitch.py` — `normalize_loudness`.
- `backend/app/core/orchestrator.py` — `_run_sleep` (per-chunk normalize, ellipsis).
- `backend/app/providers/elevenlabs_provider.py` — `_prepare_v3` pacing tag.
- `backend/app/providers/bootstrap.py` — pass pacing-tag setting.
- `backend/app/core/sleep_text.py` — `inject_sentence_pauses`.
- `backend/.env.example`, `README.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`, `docs/prompting_guides/elevenlabs_sleep.md`.

## Testing
- `test_sleep_text.py` — `inject_sentence_pauses` boundary/skip/no-op cases.
- `test_elevenlabs_provider.py` — pacing tag off by default, reasserted after
  emotion tag for sleep, never on podcasts.
- `test_ffmpeg_stitch.py` — `normalize_loudness` returns a WAV at the pinned rate.
- `test_orchestrator.py` — ellipsis wired (on/off), per-chunk normalization runs
  for long chunks and is skipped under the min-ms guard.

## Verification (manual A/B, real key)
Generate a 6+ chunk sleep story on `provider=elevenlabs`:
- Defaults: output unchanged except PCM intermediate + steadier inter-chunk levels.
- Pacing tag on (`[slowly]`): narration holds its slow register to the end.
- Ellipsis on: softer breathing pauses at sentence breaks.
Inspect a chunk WAV (`ffmpeg -af ebur128`) for ~−21 LUFS pre-master, ~−18 LUFS
final. Confirm `mp3_44100_192` still works end-to-end (non-Pro path).
