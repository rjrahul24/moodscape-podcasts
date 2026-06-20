# F5 Sleep Story Quality Improvement

**Date:** 2026-06-20
**Status:** Approved
**Scope:** Critical + High priority fixes for F5 TTS sleep story generation

## Problem

Three issues with F5 sleep story generation:

1. **Reference text leaking** — F5-TTS has no duration predictor. On short
   generations it pads the required mel length with leftover reference audio,
   causing stray syllables from the reference clip to bleed into output.
2. **Poor quality / script adherence** — No F5-specific text normalization
   (colons, ellipses, dashes confuse F5's G2P). No post-processing to trim
   trailing silence or attenuate non-speech. nfe_step=16 trades quality for
   speed.
3. **Slow rendering** — Reference preprocessing runs per-synthesis call instead
   of once at load time. nfe_step tuning is one-size-fits-all.

## Approach

Port the reference project's (`moodscape-guided-meditations`) battle-tested F5
fixes into the current provider/orchestrator architecture. All existing contracts
preserved: single-text `synthesize()`, pydub `AudioSegment` return, disk-based
ffmpeg stitching.

## Design

### 1. Reference Audio Conditioning (`f5_provider.py`)

Add `_condition_reference_audio(audio_path, sr) -> str` — returns a temp WAV
path with conditioned audio. Called once per voice during `_get_reference()`,
result cached on the instance.

Three operations:

**1a. RMS normalization** — Normalize to -20 dBFS for consistent model input
levels. Opt out via `MOODSCAPE_F5_REF_PRESERVE_DYNAMICS=1`.

**1b. Trailing noise pad** — Append ~1s of low-level noise (-55 dBFS) to the
reference audio's end. This noise is above F5's internal -42 dBFS edge-trimmer
(survives preprocessing) but well below speech. When F5 pads with leftover
reference, it leaks *silence* instead of words. Disable via
`MOODSCAPE_F5_REF_PAD=0`. Tunable: `MOODSCAPE_F5_REF_PAD_SEC` (default 1.0),
`MOODSCAPE_F5_REF_PAD_DBFS` (default -55.0).

**1c. Whisper-verified ref_text** — Pass empty string `""` to F5's
`preprocess_ref_audio_text()` so Whisper auto-transcribes the clipped audio.
This guarantees ref_text matches exactly what F5 internally uses, preventing
ref/audio misalignment — the primary cause of reference leakage. The Whisper
call runs once per voice per session (cached).

New dependency: `soundfile` (already transitive via F5-TTS).

### 2. Post-Processing — Silence Trimming + VAD (`f5_provider.py`)

Two new functions applied inside `synthesize()` after `model.infer()`, before
converting to `AudioSegment`. Applied to all F5 output (podcasts and sleep).

**2a. `_trim_trailing_silence(audio, sr) -> np.ndarray`** — Find last sample
exceeding -45 dBFS, keep 50ms natural decay tail. Pure numpy.

**2b. `_apply_silero_vad(audio, sr) -> np.ndarray`** — Two-pass Silero VAD:
1. **Crop** — Find last speech endpoint + 100ms safety tail, slice. Removes
   diffusion-generated room tone F5 appends after last spoken word.
2. **Attenuate** — Reduce interior non-speech to 15% amplitude via gaussian-
   smoothed gain envelope. Preserves natural breath/resonance.

Silero VAD runs at 16kHz (resample from 24kHz, scale timestamps back). Uses
`torch`, `torchaudio` (already installed), `scipy` (new dep for
`gaussian_filter1d`).

**Graceful degradation:** If Silero fails, falls back to trimmed-but-unprocessed
audio with a warning log.

### 3. F5 Text Normalization (`core/f5_text.py`)

New module with `normalize_for_f5(text: str) -> str`. Pure regex, no
dependencies.

| Input pattern | Output | Why |
|---------------|--------|-----|
| Colons `:` | Comma `,` | F5 ignores colons, producing no pause |
| Ellipses `...` / `…` | Period `.` | F5 doesn't differentiate |
| Em/en-dashes `—` `–` `--` | Comma `,` | Not reliably handled by F5 |
| Compound hyphens `well-being` | `wellbeing` | Hyphens between letters cause mispronunciation (F5 issue #89) |
| ALL_CAPS `BREATHE` | `breathe` | Prevents letter-by-letter spelling by G2P |

Does NOT handle number expansion — that's already done by
`sleep_text.spell_numbers()` upstream.

Called by the orchestrator after chunking, before synthesis, when provider is F5.
Applied in both sleep and podcast paths.

### 4. Short-Phrase Pacing + Sleep Speed Defaults

**4a. Short-phrase speed override** (`f5_provider.py`) — When a chunk's
non-space character count is ≤12, override speed to 0.5. Gives F5 more mel
frames to land cleanly on tiny fragments like "Breathe in." Only in
natural-rhythm mode (not when fix_duration is active).

Env var tuning:
- `MOODSCAPE_F5_SHORT_PHRASE_PACING=1` (default on)
- `MOODSCAPE_F5_SHORT_PHRASE_MAX_CHARS=12`
- `MOODSCAPE_F5_SHORT_PHRASE_SPEED=0.5`

Lives in the provider (F5-specific model behavior workaround).

**4b. nfe_step=32 for sleep** — Orchestrator passes `nfe_step=32` via
`voice_settings` when `content_type="sleep"`. Provider reads it, falling back to
`self._nfe_step` (16). New setting: `f5_sleep_nfe_step` in `config.py`.

**4c. Sleep default speed 0.88** — ~95-100 WPM meditation pace. New setting:
`f5_sleep_speed` in `config.py`. Orchestrator uses it as the starting speed for
F5 sleep stories, which then ramps down further via `_sleep_ramp()`.

### 5. Orchestrator Integration (`orchestrator.py`)

Minimal wiring changes:

**5a. F5 text normalization in sleep path** — After `spell_numbers()` and
chunking, before synthesis. Provider-name check (exception to capability-flag
pattern; text normalization is inherently model-specific).

**5b. F5 text normalization in podcast path** — Same treatment after emotion tag
extraction, before synthesis.

**5c. Sleep voice_settings enrichment** — `_sleep_voice_settings()` gains two
keys for F5: `nfe_step` (from `settings.f5_sleep_nfe_step`) and `content_type`
(`"sleep"`).

**5d. Provider reads new keys** — `synthesize()` reads `nfe_step` from
`voice_settings` if present, falling back to constructor default.

**Unchanged:** chunker (already 250 chars for F5), stitching (ffmpeg concat +
8ms edge fades), sleep post-processing, `synthesize()` signature.

### 6. Config + Dependencies

**New settings in `config.py`:**

| Setting | Env var | Default | Purpose |
|---------|---------|---------|---------|
| `f5_sleep_nfe_step` | `F5_SLEEP_NFE_STEP` | `32` | Higher quality for sleep |
| `f5_sleep_speed` | `F5_SLEEP_SPEED` | `0.88` | Meditation pace start |

**New dependency in `pyproject.toml`:** `scipy` — for `gaussian_filter1d` in VAD
smoothing.

**No changes to `bootstrap.py`** — new settings are orchestrator concerns passed
via `voice_settings`, not provider constructor params.

### 7. F5 Sleep Story Prompting Guide (`docs/prompting_guides/f5_sleep.md`)

Self-contained LLM prompt for writing F5 sleep story prose. Key guidance:

- Sentences under 15 words (F5 garbles long runs, worse at sleep speed)
- Periods and commas are the only reliable prosodic cues; colons/ellipses/dashes
  are normalized away
- `[pause:N]` is the primary pacing tool; 400–1200ms typical for sleep
- No ALL_CAPS, no abbreviations, numbers as words
- Tone lives in word choice (F5 voice anchored to reference clip)
- Progressive structure: active imagery → passive → body → breath → release
- Avoid compound-hyphenated words (F5 mispronunciation issue)

## Files Changed

| File | Change |
|------|--------|
| `backend/app/providers/f5_provider.py` | Reference conditioning, silence trimming, VAD, short-phrase pacing, read nfe_step from voice_settings |
| `backend/app/core/f5_text.py` | **New** — F5 text normalization |
| `backend/app/core/orchestrator.py` | Wire F5 normalization, pass sleep nfe_step + content_type |
| `backend/app/config.py` | Add `f5_sleep_nfe_step`, `f5_sleep_speed` |
| `backend/pyproject.toml` | Add `scipy` dependency |
| `docs/prompting_guides/f5_sleep.md` | **New** — F5 sleep story prompting guide |
| `docs/prompting_guides/README.md` | Add F5 sleep row to table |
| `docs/ARCHITECTURE.md` | Document F5 conditioning pipeline |
| `docs/CHANGELOG.md` | Dated entry |

## Not In Scope

- Equal-power cosine crossfading between chunks (future enhancement)
- Microprosody / pitch declination (reference project has it, off by default)
- Multi-phase voice registry (single reference voice per slug is sufficient)
- WPM-based `fix_duration` pacing (reference project has it; current
  orchestrator's speed + ramp approach is adequate)
- Changes to the `synthesize()` method signature

## Research Sources

- [F5-TTS official repo](https://github.com/SWivid/F5-TTS)
- [F5-TTS reference audio best practices (issue #965)](https://github.com/SWivid/F5-TTS/issues/965)
- [F5-TTS speech speed consistency (issue #876)](https://github.com/SWivid/F5-TTS/issues/876)
- [F5-TTS compound hyphen mispronunciation (issue #89)](https://github.com/SWivid/F5-TTS/issues/89)
- [F5-TTS long text speed acceleration (issue #811)](https://github.com/SWivid/F5-TTS/issues/811)
- [F5-TTS conversational speech transcription (discussion #1194)](https://github.com/SWivid/F5-TTS/discussions/1194)
- [F5-TTS noisy reference robustness (issue #1204)](https://github.com/SWivid/F5-TTS/issues/1204)
- Reference implementation: `moodscape-guided-meditations/core/f5_tts/engine.py`
