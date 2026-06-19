# Long-form Quality Control (WER + speaker drift) — design

Date: 2026-06-19
Status: Implemented

## Context

Three local-TTS research reports motivated a roadmap to harden the app for
30–90 min generation. The reports assert long-form local synthesis is practical
but the strongest concrete gap (Doc C) is **quality control**: over a long render,
local TTS hallucinates or drops words, and a cloned voice can slowly drift off the
reference timbre. Neither is visible without listening to the whole episode. This
feature detects both automatically.

## Goals

- Catch transcript infidelity (hallucination / dropping) via **word error rate**.
- Catch cloned-voice **drift** via windowed **speaker similarity** against the
  reference clip.
- Opt-in and non-fatal: a successful render must never fail because QC couldn't run.
- Honor the existing contracts: heavy libs imported lazily, missing deps degrade to
  a clear note, `uv run pytest` and the default render path stay light.

## Non-goals

- Per-turn alignment / forced alignment (chunk WAVs are deleted after stitching).
- Auto-retrying or auto-regenerating flagged segments (report only).
- MOS / subjective scoring, pronunciation dictionaries.

## Design

`core/qc.py`:

- **Pure scoring** (no deps): `strip_markup`, `normalize_words`,
  `word_error_rate` (word-level Levenshtein / reference length).
- **`transcribe(audio_path, settings)`** — lazy: `mlx_whisper` (Apple Silicon)
  preferred, `faster_whisper` (CPU) fallback. Returns `(text, None)` or
  `(None, note)`.
- **`speaker_similarity(audio_path, reference_audio, settings)`** — lazy
  `resemblyzer`: embed the reference and the master's partial windows, cosine-
  compare each window, flag windows below `qc_sim_threshold`. Returns a partial
  `QCReport` + optional note.
- **`run_qc(...)`** — always WER (vs markup-stripped source), SIM only when a
  reference clip is supplied. Collects skip-notes; never raises.

Surfacing: `QCReport`/`QCWindow` in `models.py`; `GenerateResult.qc` set by
`orchestrator._attach_qc`, called from `run()` after the master is written when
`Settings.enable_qc` is true. SIM reference is resolved from
`reference_voice_registry` for the single-cloned-voice case (sleep stories always;
podcasts when one distinct f5/cosyvoice voice is used).

Settings: `enable_qc` (default `False`), `qc_whisper_mlx_repo`,
`qc_whisper_faster_size`, `qc_sim_threshold`. Deps: `uv sync --extra qc`.

## Key decisions / trade-offs

- **Score the whole master, window for SIM.** Per-turn QC would need turn
  boundaries we discard at stitch time; whole-master windowing catches gradual
  drift without reconstructing them.
- **Opt-in.** QC transcribes the full master and embeds windows — roughly doubling
  wall-clock — so it stays off by default and is a manual quality gate.
- **Two Whisper backends.** mlx-whisper is fast on Apple Silicon but Mac-only;
  faster-whisper keeps QC usable (slower) on any host that installs the extra.

## Testing

`tests/test_qc.py` unit-tests the pure scoring and fakes the ASR/encoder imports
for the lazy paths (including the missing-deps degradation). `test_orchestrator.py`
locks the wiring: `enable_qc` gates `_attach_qc`, which feeds `run_qc` the master
path + source text. All green with no `qc` extra installed.

## Verification

- `uv run pytest` green without the `qc` extra (lazy imports degrade cleanly).
- With `ENABLE_QC=true` and `uv sync --extra qc`, a short real job populates
  `GenerateResult.qc` with a plausible WER and per-window SIM.
