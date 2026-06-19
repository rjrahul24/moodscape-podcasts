# Reference-clip upload + hygiene — design

Date: 2026-06-19
Status: Implemented

## Context

Voice cloning (F5, CosyVoice3) already works, but reference clips were
filesystem-only: a user had to manually place `reference_audio/<slug>.wav` +
`reference_text/<slug>.txt` pairs under `assets/speakers/`. The research (Doc A)
recommends cleaning user clips before cloning (denoise + trim) since the cloners
faithfully reproduce whatever they're given. This feature makes "clone from a short
clip" an end-to-end UI action with hygiene.

## Goals

- Upload a short clip from the UI → it becomes a usable cloned voice for F5 and
  CosyVoice3 with no provider changes.
- Clean the clip first: mono, resample, trim dead air, optional denoise, cap length.
- Require a transcript (the cloners condition on it); auto-transcribe when omitted.
- Keep the lazy/degrade contract: baseline works with no extra; heavy denoise is
  optional and degrades to a no-op + note.

## Non-goals

- Speaker diarization or multi-speaker clip splitting.
- A learned VAD (energy-based silence trim is the baseline; DeepFilterNet3 / silero
  can slot in later behind the same contract).
- Managing/deleting voices from the UI (manual filesystem still works).

## Design

- **`core/ref_clean.clean_clip(src, dst, *, settings)`** — pydub baseline (mono →
  resample → `detect_leading_silence` head/tail trim → length cap → WAV), with an
  optional `noisereduce` denoise step. Returns per-step notes. Only raises if the
  source can't be decoded.
- **`reference_voice_registry`** gains `slugify()` and `save()` (it owns the on-disk
  layout). `save` copies the cleaned WAV + writes the transcript, overwriting an
  existing slug.
- **`POST /api/voices/reference`** (multipart `name`, `audio`, optional
  `transcript`) — slugify name → write upload to temp → `clean_clip` → resolve
  transcript (provided, else `qc.transcribe`; 422 if neither) → `save`. Returns
  `ReferenceVoiceCreated` (`id`, `name`, `providers`, `transcript`, `replaced`,
  `notes`).
- **Frontend `AddVoice`** panel: name + file + optional transcript; shows hygiene
  notes on success; `App.loadVoices()` re-fetches `/api/voices` so the voice
  appears everywhere.
- Settings: `REFERENCE_CLIP_SAMPLE_RATE` (24 kHz), `REFERENCE_CLIP_MAX_SECONDS`
  (30 s). Optional extra: `uv sync --extra clean` (`noisereduce`).

## Key decisions / trade-offs

- **Persist into the existing registry layout** rather than a new store — F5 and
  CosyVoice3 discover voices by scanning it, so the feature needs zero provider
  changes and one code path owns the layout.
- **Transcript required, auto-transcribe as fallback** — reuses the Phase 2 Whisper
  so we don't add a second ASR path; a clear 422 when unavailable beats a silent
  bad clone.
- **noisereduce over DeepFilterNet3 for now** — reliable and light; DeepFilterNet3
  (Doc A) is a future drop-in behind the same degrade contract.

## Testing

`tests/test_ref_clean.py` unit-tests the hygiene helpers on in-memory segments (no
ffmpeg), fakes `noisereduce` for the denoise path and its absence, and covers
`slugify`/`save`/`scan`. `tests/test_api.py` covers the route: upload-with-transcript
persists to the configured assets dir; upload-without-transcript-or-Whisper → 422.
Frontend type-checks and the panel was verified rendering in the preview.

## Verification

- `uv run pytest` green without the `clean`/`qc` extras (lazy degrade).
- Upload a clip in the UI → it appears under F5 + CosyVoice3 → generate with it.
