# Kokoro Punctuation-to-Pause Conversion — Design Spec

**Date:** 2026-06-20
**Status:** Draft
**Scope:** Kokoro TTS sleep stories only — no changes to other providers or podcasts

## Context

Kokoro TTS produces essentially no pause at punctuation marks (commas, ellipses,
semicolons, dashes). The speech runs together as if they weren't there. The
previous `enhance_pacing()` approach (inserting more commas and converting periods
to ellipses) was ineffective because Kokoro ignores these marks entirely.

The `[pause:N]` marker, on the other hand, works perfectly — the orchestrator
splits the text on these markers and splices real silence between the segments.
This spec replaces the punctuation-based approach with a **punctuation-to-pause
conversion** that strips within-sentence punctuation and inserts `[pause:N]`
markers, giving us full control over pause timing.

## Design

### Punctuation mapping

| Punctuation | Replacement | Duration |
|---|---|---|
| `...` or `…` (ellipsis) | `[pause:350]` | Gentle drift |
| `—` or `–` (em/en dash) | `[pause:250]` | Contemplative mid-thought |
| `;` (semicolon) | `[pause:200]` | Longer breath between related ideas |
| `,` (comma) | `[pause:150]` | Brief breath beat |

**Processing order matters:** Ellipses (`...`) must be matched before periods to
avoid treating them as three separate sentence-endings. Dashes before hyphens
for the same reason.

**Periods are NOT converted.** Sentence boundaries are already handled by the
chunker (which splits on sentences) and the orchestrator (which inserts the
inter-sentence gap of 1050 ms, ramped). Converting periods would double-pause.

**Paragraph breaks** still get `[pause:400]` inserted at double-newline
boundaries (carried forward from the previous implementation).

### Gating

The conversion runs **only for Kokoro** (`provider_name == "kokoro"`). Other
providers (ElevenLabs, F5, CosyVoice3) handle punctuation natively and should
not have their text modified. The orchestrator already knows the provider name
and passes it to the preprocessing step.

### Pipeline flow

```
Input prose
  ↓ spell_numbers()          — as before
  ↓ punctuation_to_pauses()  — Kokoro only: commas/ellipses/semicolons/dashes → [pause:N]
  ↓ chunk_prose()            — splits on sentence boundaries
  ↓ for each chunk:
      split_pauses()         — splits on [pause:N] markers
      → each piece synthesized separately
      → silence spliced between pieces
      → inter-sentence gap (1050 ms, ramped) between chunks
```

### Example

Input:
```
The air is cool, and very still... a whisper of wind; barely there — just enough.
```

After `punctuation_to_pauses()`:
```
The air is cool [pause:150] and very still [pause:350] a whisper of wind [pause:200] barely there [pause:250] just enough.
```

After `split_pauses()`:
```
[("The air is cool ", 150), ("and very still ", 350), ("a whisper of wind ", 200),
 ("barely there ", 250), ("just enough.", 0)]
```

Each piece is synthesized as a separate Kokoro call. Silence is spliced between
them. The 8 ms edge-fade on each chunk WAV handles click artifacts at boundaries.

### Existing `[pause:N]` markers

Author-placed `[pause:N]` markers in the original text are preserved — the
conversion does not touch them. They stack naturally: a comma before an author
pause becomes two consecutive pauses (the comma's 150 ms + the author's
explicit pause).

### Configuration

Add pause durations to `Settings` in `config.py` so they're tunable without
code changes:

```python
kokoro_pause_comma_ms: int = 150
kokoro_pause_ellipsis_ms: int = 350
kokoro_pause_semicolon_ms: int = 200
kokoro_pause_dash_ms: int = 250
kokoro_pause_paragraph_ms: int = 400
```

## Files modified

| File | Change |
|---|---|
| `backend/app/config.py` | Add `kokoro_pause_*` settings |
| `backend/app/core/sleep_text.py` | Replace `enhance_pacing()` with `punctuation_to_pauses()` |
| `backend/app/core/orchestrator.py` | Pass `provider_name` to pacing function, gate on `"kokoro"` |
| `backend/tests/test_sleep_text.py` | Replace `enhance_pacing` tests with `punctuation_to_pauses` tests |
| `docs/prompting_guides/kokoro_sleep.md` | Update pacing toolkit to reflect explicit pause conversion |
| `docs/ARCHITECTURE.md` | Update sleep pipeline description |
| `docs/CHANGELOG.md` | Append entry |

## Tests

- Comma → `[pause:150]` in output
- Ellipsis (`...`) → `[pause:350]`, matched before periods
- Semicolon → `[pause:200]`
- Dash (`—`/`–`) → `[pause:250]`
- Periods NOT converted (left intact for chunker)
- Author `[pause:N]` markers preserved
- Paragraph breaks get `[pause:400]`
- Non-Kokoro providers get unmodified text (function is a no-op)

## Verification

1. `cd backend && uv run pytest` — all tests pass
2. Generate a Kokoro sleep story and listen for reliable, consistent pauses at
   every comma, ellipsis, semicolon, and dash position
3. Verify ElevenLabs sleep stories are unaffected (no text modification)
