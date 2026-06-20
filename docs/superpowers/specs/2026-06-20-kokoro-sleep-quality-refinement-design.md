# Kokoro Sleep Story Quality Refinement — Design Spec

**Date:** 2026-06-20
**Status:** Draft
**Scope:** Kokoro TTS sleep stories only — no changes to podcasts or other providers

## Context

Kokoro TTS sleep story output is already solid (~8/10). This spec describes
targeted refinements to push it to 10/10 across four areas: pacing, emotional
delivery, ambient bed consistency, and prompting guidance. All changes are
small, additive, and confined to the sleep path.

Kokoro's fundamental constraints inform every decision: it has no native SSML,
no emotion performance, no prosody tags, and no continuity context. The only
model-level levers are the `speed` parameter and how the input text is
formatted (punctuation, sentence length). Emotion must live in the words.

---

## 1. Pacing — Slower, Calmer Delivery

### 1a. Inter-sentence gap increase

**File:** `backend/app/config.py`

Change `sleep_default_pause_ms` from `900` → `1050`.

With the existing ramp (`sleep_ramp_pause_scale: 1.6`):
- Start of story: 1050 ms gaps
- End of story: ~1680 ms gaps (was 1440 ms)

This is a one-line config change. The ramp, chunker, and orchestrator are
unaffected — they read this value dynamically.

### 1b. Within-sentence rhythm — automated punctuation enhancement

**File:** `backend/app/core/sleep_text.py` (new function `enhance_pacing`)

A light text transform applied after `spell_numbers()` and before chunking in
`_run_sleep()`. Three rules:

1. **Long-clause comma insertion.** If a clause runs >~80 characters without
   internal punctuation (comma, semicolon, colon, dash, ellipsis), insert a
   comma before the first conjunction or subordinating word (`and`, `but`, `as`,
   `while`, `where`, `when`, `which`, `because`, `before`, `after`, `until`,
   `although`, `though`, `since`). Regex-based — no NLP dependency.

2. **Ellipsis softening.** At paragraph-internal sentence boundaries (`.` →
   next sentence in the same paragraph), convert ~25% of periods to ellipses
   (`...`). Use `random.Random(hash(text))` so the same input always produces
   the same output (deterministic, no cross-render drift). Skip sentence
   boundaries that already have a `[pause:N]` marker within 20 characters.

3. **Paragraph-break pause markers.** Insert `[pause:400]` at double-newline
   paragraph breaks (where no `[pause:N]` already exists) to add a beat
   between narrative sections.

**Orchestrator change** (`backend/app/core/orchestrator.py`, `_run_sleep`):
call `sleep_text.enhance_pacing(prose)` after `spell_numbers()`, before
`chunker.chunk_prose()`.

**Guard:** Only runs for sleep stories. Podcasts never call this function.

---

## 2. Emotional Delivery Refinement

### 2a. New sleep-oriented emotion tags

**File:** `backend/app/core/emotion.py`

Add two tags to `EMOTIONS` and `EMOTION_SPEED`:

| Tag        | Speed multiplier | Use case                              |
|------------|------------------|---------------------------------------|
| `dreamy`   | 0.90×            | Drifting, dissolving imagery          |
| `tender`   | 0.96×            | Gentle, caring, comforting moments    |

These join the existing sleep-relevant tags (`soothing` 0.93×, `warm` 0.97×,
`reflective` 0.95×, `calm` 0.94×). No provider changes needed — the tags ride
the existing `emotion_map.speed_multiplier()` path that Kokoro already uses.

### 2b. Prompting guide emphasis

The bulk of emotional improvement comes from teaching script-writers how to
embed feeling through word choice, sentence rhythm, and pause placement. This
is documented in the new prompting guide (Section 4 below).

---

## 3. Ambient Bed Loudness Normalization

### Problem

Different ambient source files have different inherent loudness. The flat
`-18 dB` gain reduction produces inconsistent perceived volume — a loud ocean
track overpowers the voice while a quiet rain track nearly disappears.

### Solution

**File:** `backend/app/core/ambient.py` (`build_filter_complex`)

Add an EBU R128 `loudnorm` pass at the start of the bed processing chain,
before band-limiting and gain. The chain becomes:

```
[before]  highpass → lowpass → volume(-18dB) → fades
[after]   loudnorm(I=-24, TP=-2, LRA=11) → highpass → lowpass → volume(-18dB) → fades
```

**Target: -24 LUFS.** Every bed is normalized to -24 LUFS integrated loudness
before the gain pull-down. This means any ambient file — regardless of its
original level — starts at the same perceived loudness. The existing -18 dB
gain then applies predictably.

Why -24 LUFS: the voice targets -18 LUFS. Starting the bed 6 LUFS below that
*before* the gain drop ensures it sits well behind the voice consistently.

**Config addition** (`backend/app/config.py`):

```python
ambient_bed_target_lufs: float = -24.0  # normalize bed loudness before gain
```

This is additive — no existing parameters change, no behaviour changes for
the voice path. The bed just gets a loudness-normalization step.

---

## 4. Kokoro Sleep Prompting Guide

**New file:** `docs/prompting_guides/kokoro_sleep.md`

A standalone guide for LLMs writing Kokoro sleep story prose, mirroring the
depth and structure of `elevenlabs_sleep.md` but honest about Kokoro's
constraints and tailored to its strengths.

### Structure

1. **INPUTS block** — topic, voice selection, target length, ambient bed,
   overall tone, optional notes.

2. **YOUR TASK** — context about Kokoro: no emotion performance, speed is the
   only delivery lever, emotion must live in the words. Frame this as a
   strength: Kokoro delivers a consistent, predictable calm.

3. **PACING TOOLKIT** — the core section:
   - `[pause:N]` usage guide with recommended durations:
     - Paragraph breaks: 400–800 ms
     - After emotional beats: 300–500 ms
     - Before key imagery: 250–400 ms
     - Scene transitions: 600–1000 ms
     - End of story dissolution: 800–1200 ms
   - Punctuation rhythm:
     - Commas: brief breath (~150–200 ms in Kokoro)
     - Ellipses: gentle drift (~300–400 ms)
     - Dashes: mid-thought pause, contemplative
     - Semicolons: longer breath between related ideas
   - Sentence length: 12–20 words optimal, never exceed 25
   - Paragraph structure: 2–4 sentences per beat

4. **TONE TAGS** — all available tags with their speed effects:
   `[soothing]` (0.93×), `[warm]` (0.97×), `[dreamy]` (0.90×),
   `[reflective]` (0.95×), `[tender]` (0.96×), `[calm]` (0.94×).
   Guidance on when to use each. Place at paragraph/section openings.

5. **WRITING EMOTION INTO WORDS** — techniques:
   - Sensory imagery (texture, temperature, light, sound)
   - Repetition as rhythm (gentle structural echoing)
   - Progressive relaxation (each paragraph softer/simpler than the last)
   - Metaphors of descent (sinking, floating, dissolving)
   - Avoid: climactic tension, questions, instructions, dialogue

6. **STRUCTURE** — story arc for sleep:
   - Opening: scene-setting, grounding in a place
   - Middle: gentle exploration, sensory deepening
   - Final third: simplification, longer pauses, shorter sentences
   - Ending: dissolution, repetition, fading imagery

7. **WORKED EXAMPLE** — a full annotated excerpt (~200 words) showing pause
   tags, tone tags, punctuation rhythm, and sensory writing in practice.

8. **SELF-CHECK** — bulleted checklist before outputting.

### Update existing files

- `docs/prompting_guides/README.md`: add link to the new Kokoro sleep guide
- Reference the new emotion tags (`dreamy`, `tender`) where applicable

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/config.py` | `sleep_default_pause_ms: 900→1050`, add `ambient_bed_target_lufs: -24.0` |
| `backend/app/core/sleep_text.py` | Add `enhance_pacing()` function |
| `backend/app/core/orchestrator.py` | Call `enhance_pacing()` in `_run_sleep` after `spell_numbers()` |
| `backend/app/core/emotion.py` | Add `dreamy` and `tender` to `EMOTIONS` and `EMOTION_SPEED` |
| `backend/app/core/ambient.py` | Add `loudnorm` step in `build_filter_complex()` |
| `docs/prompting_guides/kokoro_sleep.md` | New file — complete sleep story prompting guide |
| `docs/prompting_guides/README.md` | Add link to new Kokoro sleep guide |
| `docs/ARCHITECTURE.md` | Update sleep pipeline description |
| `docs/CHANGELOG.md` | Append entry |

## Tests

| Area | Test |
|------|------|
| `enhance_pacing` | Unit tests in `backend/tests/test_sleep_text.py`: long clause gets comma, ellipsis insertion is deterministic, paragraph breaks get `[pause:400]`, existing `[pause:N]` not doubled |
| Emotion tags | Update `backend/tests/test_emotion.py` (or wherever emotion tests live): `dreamy` and `tender` return correct speed multipliers |
| Ambient normalization | Update `backend/tests/test_ambient.py`: verify `loudnorm` appears in the filter graph |
| Config | Verify `sleep_default_pause_ms=1050` and `ambient_bed_target_lufs=-24.0` defaults |

## Verification

1. **Run existing tests:** `cd backend && uv run pytest` — all must pass
2. **Generate a Kokoro sleep story** with an ambient bed through the UI and
   listen for:
   - Slightly wider inter-sentence gaps (vs previous renders)
   - Smoother within-sentence rhythm from punctuation enhancement
   - Consistent ambient bed volume across different bed choices
3. **Test with the new prompting guide:** paste `kokoro_sleep.md` into an LLM,
   generate a sleep story, and verify the output uses pause tags, tone tags,
   and punctuation appropriately
4. **Compare before/after** on the same text + same ambient bed to confirm
   the ambient normalization produces more consistent volume
