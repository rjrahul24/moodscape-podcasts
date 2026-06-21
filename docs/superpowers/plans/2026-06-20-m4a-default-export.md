# M4A Default Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make M4A (AAC-LC 256 kbps) the default output format, with WAV as the secondary export, replacing MP3 entirely.

**Architecture:** The generation pipeline stays WAV internally. A new `transcode_m4a()` in `ffmpeg_stitch.py` converts the final WAV master to M4A at the end of `_finalize()`. Config defaults flip from `final_format="wav"` + `also_export_mp3=True` to `final_format="m4a"` + `also_export_wav=True`.

**Tech Stack:** ffmpeg (AAC-LC encoder), Python/FastAPI, pytest

## Global Constraints

- Python 3.13, managed with `uv`
- ffmpeg must be on PATH (already a project requirement)
- WAV stays the internal format throughout the pipeline — M4A conversion only at finalization
- No changes to providers, chunking, sleep_post, ambient mixing, or podcast_music
- Tests use `also_export_wav=False` (like the old `also_export_mp3=False`) to keep assertions simple

---

### Task 1: Add `transcode_m4a()` to `ffmpeg_stitch.py`

**Files:**
- Modify: `backend/app/core/ffmpeg_stitch.py:140-151`
- Test: `backend/tests/test_ffmpeg_stitch.py`

**Interfaces:**
- Consumes: `run_ffmpeg()` (existing), `silence_wav()` (test helper)
- Produces: `transcode_m4a(in_wav: Path, out_m4a: Path, *, bitrate: str = "256k") -> Path` — used by `transcode()` in this same file, and by Task 2's `_finalize()` changes

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ffmpeg_stitch.py`:

```python
@needs_ffmpeg
def test_transcode_m4a(tmp_path):
    wav = ffmpeg_stitch.silence_wav(tmp_path / "a.wav", duration_ms=300, sample_rate=44100)
    m4a = ffmpeg_stitch.transcode_m4a(wav, tmp_path / "a.m4a")
    assert m4a.exists() and m4a.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/rahul/Downloads/moodscape-podcasts/backend && uv run pytest tests/test_ffmpeg_stitch.py::test_transcode_m4a -v`
Expected: FAIL with `AttributeError: module 'app.core.ffmpeg_stitch' has no attribute 'transcode_m4a'`

- [ ] **Step 3: Implement `transcode_m4a` and update `transcode`**

In `backend/app/core/ffmpeg_stitch.py`, replace lines 140–151 with:

```python
def transcode_mp3(in_wav: Path, out_mp3: Path, *, bitrate: str = "320k") -> Path:
    """Transcode a WAV master to MP3."""
    run_ffmpeg(["-i", str(in_wav.resolve()), "-b:a", bitrate, str(out_mp3.resolve())])
    return out_mp3


def transcode_m4a(in_wav: Path, out_m4a: Path, *, bitrate: str = "256k") -> Path:
    """Transcode a WAV master to M4A (AAC-LC).

    ``-movflags +faststart`` relocates the moov atom so iPhone apps can begin
    playback immediately without buffering the entire file.
    """
    run_ffmpeg([
        "-i", str(in_wav.resolve()),
        "-c:a", "aac",
        "-b:a", bitrate,
        "-movflags", "+faststart",
        str(out_m4a.resolve()),
    ])
    return out_m4a


def transcode(in_path: Path, out_path: Path, *, final_format: str) -> Path:
    """Transcode ``in_path`` to ``out_path`` in ``final_format`` (wav/mp3/m4a/...)."""
    if final_format == "mp3":
        return transcode_mp3(in_path, out_path)
    if final_format == "m4a":
        return transcode_m4a(in_path, out_path)
    run_ffmpeg(["-i", str(in_path.resolve()), str(out_path.resolve())])
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/rahul/Downloads/moodscape-podcasts/backend && uv run pytest tests/test_ffmpeg_stitch.py -v`
Expected: All tests PASS including `test_transcode_m4a`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/ffmpeg_stitch.py backend/tests/test_ffmpeg_stitch.py
git commit -m "feat: add transcode_m4a for AAC-LC encoding with faststart"
```

---

### Task 2: Update config defaults and `_finalize()` in orchestrator

**Files:**
- Modify: `backend/app/config.py:86-87`
- Modify: `backend/app/core/orchestrator.py:365-388` (`_finalize`), line 724-728 (podcast call site), line 938 (sleep story call site)
- Modify: `backend/app/core/stitcher.py:89-114` (`export_master`)
- Test: `backend/tests/test_orchestrator.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `ffmpeg_stitch.transcode_m4a()` from Task 1, `ffmpeg_stitch.transcode()` (updated in Task 1)
- Produces: Updated `_finalize(master_wav, out_dir, *, final_format, also_export_wav)` — same call sites, new parameter name

- [ ] **Step 1: Update config defaults**

In `backend/app/config.py`, change lines 86-87 from:

```python
    final_format: str = "wav"
    also_export_mp3: bool = True
```

to:

```python
    final_format: str = "m4a"
    also_export_wav: bool = True
```

- [ ] **Step 2: Update `_finalize()` in orchestrator**

In `backend/app/core/orchestrator.py`, replace lines 365-388:

```python
def _finalize(
    master_wav: Path,
    out_dir: Path,
    *,
    final_format: str,
    also_export_wav: bool,
) -> list[Path]:
    """Move/transcode the concat master into ``out_dir`` as episode.<fmt> (+wav)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{files.EPISODE_BASENAME}.{final_format}"
    if final_format == "wav":
        master_wav.replace(master_path)
    else:
        ffmpeg_stitch.transcode(master_wav, master_path, final_format=final_format)
    written.append(master_path)

    if also_export_wav and final_format != "wav":
        wav_path = out_dir / f"{files.EPISODE_BASENAME}.wav"
        master_wav.replace(wav_path)
        written.append(wav_path)

    return written
```

- [ ] **Step 3: Update podcast call site (line ~727-728)**

Change:

```python
        final_format=settings.final_format,
        also_export_mp3=settings.also_export_mp3,
```

to:

```python
        final_format=settings.final_format,
        also_export_wav=settings.also_export_wav,
```

- [ ] **Step 4: Update sleep story call site (line ~938)**

Change:

```python
    written = _finalize(final_wav, out_dir, final_format="wav", also_export_mp3=True)
```

to:

```python
    written = _finalize(final_wav, out_dir, final_format=settings.final_format, also_export_wav=settings.also_export_wav)
```

- [ ] **Step 5: Update `export_master()` in stitcher.py**

In `backend/app/core/stitcher.py`, replace lines 89-114:

```python
def export_master(
    episode: AudioSegment,
    out_dir: Path,
    base_name: str,
    *,
    final_format: str = "m4a",
    also_export_wav: bool = True,
) -> list[Path]:
    """Write the episode to ``out_dir`` and return the created file paths.

    Always writes ``<base_name>.<final_format>``; additionally writes a WAV
    when ``also_export_wav`` is set and the master is not already WAV.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    master_path = out_dir / f"{base_name}.{final_format}"
    episode.export(master_path, format=final_format)
    written.append(master_path)

    if also_export_wav and final_format != "wav":
        wav_path = out_dir / f"{base_name}.wav"
        episode.export(wav_path, format="wav")
        written.append(wav_path)

    return written
```

- [ ] **Step 6: Update test fixtures**

In `backend/tests/test_orchestrator.py`, update the `settings` fixture (line ~18-26):

```python
@pytest.fixture
def settings(tmp_path):
    return Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_wav=False,
        inter_turn_gap_ms=100,
        ambient_dir=tmp_path / "ambient",
    )
```

In `backend/tests/test_engine.py`, update `_settings` (line ~11-18):

```python
def _settings(tmp_path) -> Settings:
    return Settings(
        output_dir=str(tmp_path),
        segment_output_format="wav_44100",
        final_format="wav",
        also_export_wav=False,
        inter_turn_gap_ms=100,
    )
```

Update every other occurrence of `also_export_mp3=False` in `backend/tests/test_orchestrator.py` (lines ~361, ~472, ~508, ~527) to `also_export_wav=False`.

- [ ] **Step 7: Run all tests**

Run: `cd /Users/rahul/Downloads/moodscape-podcasts/backend && uv run pytest tests/test_orchestrator.py tests/test_engine.py tests/test_ffmpeg_stitch.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/core/orchestrator.py backend/app/core/stitcher.py backend/tests/test_orchestrator.py backend/tests/test_engine.py
git commit -m "feat: make M4A the default export format, WAV as secondary"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (docs-only)
- Produces: nothing

- [ ] **Step 1: Update ARCHITECTURE.md**

Add/update the relevant section describing the finalization step to reflect:
- Default output is M4A (AAC-LC, 256 kbps, `-movflags +faststart`)
- Secondary export is WAV (lossless backup)
- MP3 export removed
- Config keys: `final_format` (default `"m4a"`), `also_export_wav` (default `True`)

- [ ] **Step 2: Update CHANGELOG.md**

Append entry:

```markdown
## 2026-06-20 — M4A default export

- **Changed** default output from WAV + MP3 to M4A + WAV.
- **Added** `transcode_m4a()` in `ffmpeg_stitch.py` — AAC-LC at 256 kbps with
  `-movflags +faststart` for instant iPhone playback.
- **Replaced** `also_export_mp3` config with `also_export_wav`.
- **Why:** WAV files are too large for transfer/playback on mobile. M4A (AAC-LC)
  is the native iPhone codec, ~5x smaller than WAV at transparent quality. The
  generation pipeline stays lossless (WAV) throughout; conversion happens only at
  the final export step.
```

- [ ] **Step 3: Update README.md**

Update any references to output formats. The outputs section should reflect that
episodes are exported as `.m4a` (primary) + `.wav` (secondary) by default.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md README.md
git commit -m "docs: update architecture, changelog, and readme with M4A export changes"
```

---

### Task 4: Full test suite verification

**Files:** None (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd /Users/rahul/Downloads/moodscape-podcasts/backend && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Grep for any remaining references to `also_export_mp3`**

Run: `grep -rn "also_export_mp3" /Users/rahul/Downloads/moodscape-podcasts/backend/ --include="*.py" | grep -v __pycache__`
Expected: No results (all references updated)
