# M4A Default Export

**Date:** 2026-06-20
**Status:** Approved

## Problem

WAV output files are too large (a 30-min stereo episode is ~300 MB). The user's
iPhone app renders M4A files, so the app should produce M4A as the primary
download format while keeping WAV quality throughout the generation pipeline.

## Design

### Approach

Keep the entire generation pipeline in WAV (lossless). Convert to M4A only at
the finalization step, after all mixing and post-processing is complete. Replace
MP3 as the secondary format with WAV (lossless backup).

### Backend: `ffmpeg_stitch.py`

Add `transcode_m4a()`:

- **Codec:** AAC-LC (`-c:a aac`) — native iPhone codec, universally compatible
- **Bitrate:** 256 kbps CBR (`-b:a 256k`) — highest practical quality for
  AAC-LC, transparent on iPhone speakers and AirPods
- **Container:** `.m4a` (MPEG-4 audio)
- **`-movflags +faststart`** — relocates moov atom to file start for instant
  playback without full-file buffering
- **Sample rate:** preserved from input (44.1 kHz)

Update `transcode()` to route `"m4a"` format to the new function.

### Backend: `_finalize()` + config

- Change `Settings.final_format` default: `"wav"` → `"m4a"`
- Replace `Settings.also_export_mp3: bool` with `also_export_wav: bool = True`
- Update `_finalize()`: primary = `episode.m4a`, secondary = `episode.wav`
- Sleep story finalization (hardcoded `final_format="wav"`) updated to use
  `settings.final_format` / `settings.also_export_wav`

### Frontend: `ResultPlayer.tsx`

No changes needed. M4A plays natively in `<audio>` on all modern browsers.
The download list and inline player pick up whatever files the API returns.

### File size comparison (30-min stereo, 44.1 kHz)

| Format        | Size    | Quality          |
|---------------|---------|------------------|
| WAV (PCM 16)  | ~300 MB | Lossless         |
| M4A (AAC 256) | ~56 MB  | Transparent      |
| MP3 (320k)    | ~69 MB  | Near-transparent |

### What does NOT change

- Generation pipeline (providers return AudioSegment, chunks are WAV)
- Sleep post-processing (`sleep_post.py`, `ambient.py`)
- Podcast music mixing (`podcast_music.py`)
- Provider interface, chunking, orchestrator synthesis loop
- Frontend UI structure

## Files to modify

1. `backend/app/core/ffmpeg_stitch.py` — add `transcode_m4a()`, update `transcode()`
2. `backend/app/config.py` — change defaults
3. `backend/app/core/orchestrator.py` — update `_finalize()` signature + both call sites
4. `backend/app/core/models.py` — if `also_export_mp3` is referenced in models (verify)
5. Tests — update any tests referencing `also_export_mp3` or expecting MP3 output
