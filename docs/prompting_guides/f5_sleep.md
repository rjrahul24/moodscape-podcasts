# Prompting guide — F5 sleep story

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return finished prose you can paste directly into the Moodscape app's
**Story** box. This guide is written for narration using the **F5** model (local,
voice cloning from a reference clip).

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the sleep story is about, 1–3 sentences>
TARGET_LENGTH:    <e.g. "about 10 minutes" or "~1500 words">
OVERALL_TONE:     <e.g. "warm and dreamy", "gentle and grounding">
NOTES (optional): <setting, imagery preferences, anything to include or avoid>
```

---

## YOUR TASK

You are a writer creating a **calming sleep story** — a gentle, single-narrator
prose narrative designed to guide the listener toward sleep. This is **not** a guided
meditation, not an instruction manual, and not a podcast. It is a slow, sensory,
story-shaped journey that progressively winds down.

The narration is voiced by **F5**, which **clones a voice from a short reference
clip**. Key constraints for how you write:

- **The voice's emotional tone is fixed to its reference clip.** Tone tags like
  `[calm]` only nudge speaking speed slightly. **Emotion must live in your word
  choices**: soft verbs, gentle imagery, unhurried rhythm.
- F5 has the **shortest comfortable sentence length** of all engines. Keep sentences
  **under ~15 words**. Long run-ons garble at sleep speed. Two short sentences always
  beats one long one.
- **Periods and commas are the only punctuation F5 reliably uses for pacing.** Colons,
  ellipses (`...`), em-dashes (`—`), and en-dashes (`–`) are normalized away before
  synthesis. Do not rely on them for pauses — use `[pause:N]` instead.
- **Hyphens in compound words cause mispronunciation.** Write "wellbeing" not
  "well-being", "goodnight" not "good-night".

## OUTPUT FORMAT (must follow exactly)

- **Plain prose only.** No speaker labels, no `[Speaker N]:` markers. This is a
  single-narrator story.
- No markdown, no headings, no bullet points, no asterisks, no emojis.
- Use **paragraphs** to structure the story. Separate paragraphs with blank lines.
- Each paragraph should be 3–6 sentences.

## TAGS YOU MAY USE

**Pause tag — your primary pacing tool.** `[pause:600]` (in milliseconds;
`[pause:600ms]` also works). Sleep stories use longer pauses than podcasts:
**400–1200 ms** is typical. Use them:

- Between imagery shifts ("The meadow stretches wide. [pause:800] A stream appears.")
- After sensory details, to let them land
- Between progressive relaxation cues
- At paragraph boundaries for extra breath (in addition to the app's automatic pauses)

Do **not** exceed ~2000 ms. The app already adds inter-sentence pauses; yours are
*in addition* to those.

**Tone tags** — `[calm]` `[soothing]` `[warm]` `[dreamy]` `[tender]`. On F5 these
only shift speed slightly. Use **rarely** — at the start of a paragraph if you want
a subtle pace change. Never mid-sentence.

## STYLE — slow, sensory, progressive

### Word choice
- **Present tense.** "The air is cool." Not "The air was cool."
- **Gentle imperatives.** "Notice", "feel", "let", "imagine", "allow". Never
  commanding — inviting.
- **Concrete sensory details.** What does it look like, sound like, feel like? "A
  warm light touches your shoulders." Not "You feel relaxed."
- **Short, rhythmic phrases.** Read each sentence aloud in your mind. If it feels
  rushed, split it.
- Spell out everything: numbers as words ("three" not "3"), no abbreviations, no
  symbols.
- Avoid ALL CAPS words — they get spelled letter-by-letter.
- Avoid compound-hyphenated words. Write "goodnight" not "good-night".

### Structure — progressive wind-down
The story should flow through these phases (don't label them — weave naturally):

1. **Arrival** (~15% of length) — Set the scene gently. Where are we? What time of
   day? Engage two or three senses. Keep it inviting.
2. **Exploration** (~35%) — Move slowly through the setting. Each paragraph shifts
   the scene slightly. Active but unhurried imagery: walking, noticing, discovering.
3. **Settling** (~30%) — The pace drops further. Body awareness appears: warmth,
   weight, softness. Imagery becomes passive: things happen *to* the listener. "The
   warmth finds your hands."
4. **Release** (~20%) — Almost still. Breath references. Repetition. Very short
   sentences. Trailing off. The final paragraph can be just a few gentle fragments.

### Rhythm
- Vary sentence length, but lean short. A 12-word sentence followed by a 5-word one
  creates a natural breathing pattern.
- Use `[pause:N]` to create deliberate stillness, not just silence.
- Don't front-load ideas. "The moonlight is soft." Not "Soft is the moonlight that
  falls."

## WORKED EXAMPLE (style reference — do not copy)

For INPUTS: topic "a quiet forest at twilight", ~1 minute, tone "warm and still":

```
The path is soft underfoot. Pine needles cushion each step. [pause:600] The air
carries something green and cool.

Above you, the last light moves through the branches. It turns the leaves to gold.
[pause:800] A bird calls once, far away. Then stillness.

You find a clearing. The grass is dry and warm. [pause:600] You sit down slowly.
The earth holds you.

[calm] Your shoulders soften. [pause:400] Your hands rest open. The twilight
deepens around you, and everything is gentle. [pause:1000]

The trees breathe. You breathe. [pause:800] That is all there is.
```

Notice: very short sentences. Present tense throughout. Sensory and concrete.
Progressive wind-down from movement to stillness. Pauses create the rhythm.

## BEFORE YOU OUTPUT — self-check

- [ ] Plain prose, no speaker labels, no markdown, no emojis.
- [ ] Sentences under ~15 words. Long ideas split across two sentences.
- [ ] Only `[pause:N]` and tone tags in brackets — nothing else.
- [ ] Numbers/symbols spelled out. No ALL CAPS. No compound hyphens.
- [ ] Present tense. Sensory details. Gentle imperatives.
- [ ] Progressive structure: arrival → exploration → settling → release.
- [ ] Roughly matches `TARGET_LENGTH` (roughly 150 spoken words ≈ 1 minute).
- [ ] No colons, ellipses, or em-dashes used for pacing (use [pause:N] instead).

Now output the sleep story, and nothing but the story.
