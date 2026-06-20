# Perfecting ElevenLabs Sleep Stories

**Date:** 2026-06-20
**Status:** Approved, implemented (Phase 8)
**Scope:** Sleep-story path only — ElevenLabs tuning, pause handling, the ambient
bed, and the sleep prompting guide. The podcast path and the sanctioned
sleep-vs-podcast processing boundary are untouched.

## Context & motivation

Sleep stories should be **expressive yet calming** and reliably guide a listener to
sleep over a **light, slow** music bed. The pipeline already existed, but a code
read + ElevenLabs research surfaced concrete defects:

1. **v3 contradiction.** Sleep ran v3 at **Robust** stability (1.0), which largely
   *ignores* the inline audio tags that are the only reason to use v3 — so the
   "expressive" default was neither expressive nor maximally reliable.
2. **`[pause:N]` was dead.** The guide documented it, but v2 stripped it and v3 sent
   the literal, unrecognized tag to the model. The deliberate breath was always lost.
3. **Bed wasn't "light and slow."** It looped with `-stream_loop` (hard seam/click),
   gain + fade only — no band-limiting to sit it behind the voice, no ducking.
4. **Guide drift.** Recommended `[soothing]` inline (not a tag v3 recognizes when an
   author types it), and omitted the ellipsis/dash micro-pause technique.

## Design decisions (confirmed with user)

1. **Hybrid engines.** Make **both v2 and v3 first-class, well-tuned, and selectable**
   (the UI already exposes the Engine selector). v3 stays the default.
2. **Real pauses.** Implement `[pause:N]` as real silence — a **native `<break>` on
   v2**, spliced silence on v3/local.
3. **Full bed polish.** Band-limit + seamless crossfaded loop + tuned gain + optional
   sidechain ducking.

## Architecture

All per-job params continue to ride the existing `voice_settings` dict; the
`synthesize` signature is unchanged (per CLAUDE.md). The orchestrator branches on
**capability** (resolved engine), not provider names where avoidable.

### Engine tuning (`elevenlabs_provider.py`, `config.py`)
- `V3_STABILITY["sleep"]` → 0.5 (Natural), sourced from
  `elevenlabs_sleep_v3_stability` (threaded through the constructor). Natural keeps
  `[calm]`/`[warmly]` responsive while staying steady.
- `EMOTION_PROFILES["soothing"]` reconciled to warm-steady (`stability 0.72`), so the
  injected default tone doesn't over-stabilize v2.

### Default calm tone (`orchestrator.py`)
- `_sleep_emotion_for(text)` returns `sleep_default_tone` (default `soothing`) unless
  the segment already opens with an author tag — fed to `_sleep_voice_settings` as
  `emotion`. v3 → inline `[calm]`; v2 → the numeric `soothing` profile.

### Pause handling (`sleep_text.py`, `orchestrator.py`, `elevenlabs_provider.py`)
- `sleep_text.split_pauses(text, max_ms)` → `[(segment, pause_ms_after)]`, clamped.
- `spell_numbers` skips digits inside a `[pause:N]` marker so the duration survives.
- Orchestrator resolves the engine (`request.model_id or elevenlabs_sleep_model`) and
  `_supports_native_breaks` is true **only** for EL v2 with
  `elevenlabs_v2_native_breaks`. Native path keeps the marker inline (provider
  rewrites `[pause:800]` → `<break time="0.80s"/>`, capped at 3 s); the splice path
  splits the chunk and inserts silence via `ffmpeg_stitch.silence_wav`.

### Ambient bed (`ambient.py`, `config.py`, `orchestrator.py`)
- `build_looped_bed` extends the bed past the story length by crossfading `n` copies
  pairwise (`acrossfade`), trimmed to length — a seamless, click-free loop. Falls back
  to a plain stream-loop when the bed already covers the story or is too short to
  crossfade.
- `build_filter_complex` band-limits the bed (`highpass` + `lowpass`), gains/fades it,
  and — when `ambient_duck` is on — splits the voice as a sidechain key and
  `sidechaincompress`es the bed under speech (threshold converted from dB to linear),
  then `amix=duration=first` keeps output at exactly the narration length.

### Prompting guide (`docs/prompting_guides/elevenlabs_sleep.md`)
- Role/system frame; explicit v2/v3 engine branch; corrected tag vocabulary
  (`[calm]`, `[warm]`, `[sighs]`/`[exhales]`); accurate `[pause:N]` docs; the
  ellipsis/dash micro-pause technique.

## Trade-offs

- Natural v3 is slightly less locked-down than Robust, but the ramp-down + default
  tone + mastering keep it steady; v2 remains the pick for maximum long-form
  consistency. Both are exposed so the user chooses.
- Ducking and native breaks are config-gated (default on) so the behavior can be
  reverted without code changes.

## Tests

`split_pauses` + marker-safe number spelling; v2 `<break>` translation (+ 3 s clamp,
flag-off fallback); v3 Natural stability (+ configurable); ambient graph
(band-limit + duck toggling); orchestrator splice-vs-native-break routing; default
tone injection. Ambient ffmpeg graphs additionally validated end-to-end.
