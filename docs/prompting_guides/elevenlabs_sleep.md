# Prompting guide — ElevenLabs sleep story

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return finished sleep story prose you can paste directly into the
Moodscape app's **Story** box. This guide is written for a narrator using the
**ElevenLabs** model and is tuned specifically for **sleep stories**.

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the story is about — a setting, journey, or gentle scenario>
TARGET_LENGTH:    <e.g. "about 10 minutes" or "~1100 words">
OVERALL_TONE:     <e.g. "dreamy and warm", "quiet and wintry", "gentle and earthy">
NOTES (optional): <anything else — a setting detail, a feeling to evoke, imagery>
```

---

## YOUR TASK

You are a writer crafting a **sleep story** — a single-narrator piece of gentle,
lulling prose designed to guide the listener toward sleep. It is **not** a guided
meditation (no instructions to breathe, no body scans, no direct commands). It is
**not** a thriller, mystery, or plot-driven story. It is descriptive, unhurried,
and progressively calming.

Using the `INPUTS` above, write the complete sleep story in the exact format
defined below. Output **only the prose** — no preamble, no explanations, no
markdown, no headings, no `[Speaker N]:` tags.

The narrator is voiced by **ElevenLabs**. The app applies calming post-processing
(gentle compression, soft EQ, loudness normalization, fades) and optionally mixes
an ambient soundscape bed underneath. Your job is the words — the system handles
the rest.

### Which ElevenLabs model?

- **v3 (expressive — the default)** — performs inline tone tags (`[calm]`,
  `[soothing]`) for genuinely softer delivery. Good for sleep because the model
  shifts into a calm register. Spell out numbers ("forty-two", not "42").
- **Multilingual v2** — tone tags map to numeric voice settings (stability/style).
  Slightly more predictable. Best text normalization of any model.

Both work well for sleep. v3 is the default and slightly more natural.

## OUTPUT FORMAT

- **Plain prose. No speaker tags.** Do not write `[Speaker 1]:` or any speaker
  markers. Sleep stories are single-narrator.
- One continuous block of prose. Paragraphs separated by blank lines are fine for
  readability.
- Plain text only. **No** markdown, bullet points, asterisks, emojis, or headings.

## TONE TAGS YOU MAY USE

Place at the **very beginning of a paragraph** to set the delivery for that
paragraph. On ElevenLabs these genuinely change the voice — they're not cosmetic.

Recommended for sleep:
- `[soothing]` — slow, softening, the most sleep-appropriate tag
- `[calm]` — steady, grounded, settled
- `[warm]` — gentle affection, like a soft goodnight

Avoid for sleep:
- `[excited]` — too much energy, will break the lulling rhythm
- `[whispering]` — can sound jarring or sibilant at the quiet volumes sleep
  stories are played at
- `[sad]` — risks a heavy, downward emotional pull

Guidance: tag **very few** paragraphs — maybe 2–3 across the whole story, and only
where a shift in delivery adds something genuine. The app's progressive ramp-down
already decelerates the narration toward sleep. Untagged prose sounds calm and
natural by default.

**Pause tag** — `[pause:800]` or `[pause:800ms]`. Use sparingly for a long,
deliberate breath between paragraphs or after a particularly vivid image. Sleep
pauses can be longer than podcast pauses (600–1200 ms). The app already inserts
inter-sentence pauses (configurable, default ~900 ms), so you rarely need these.

## WRITING STYLE

### Rhythm and sentence structure

- **Vary sentence length.** Favor medium sentences (12–20 words) as your baseline.
  Alternate with occasional short sentences (5–8 words) for pacing contrast and
  occasional longer ones (up to ~25 words) for flowing imagery.
- **Don't rush.** Each sentence should feel like it has room to breathe. Avoid
  stacking dense information.
- **Repeat gentle patterns.** Mild repetition of phrasing or rhythm is lulling, not
  boring. "The water moves. The light moves. Everything moves, slowly."

### Imagery and content

- **Sensory-rich but gentle.** Describe textures, temperatures, light, quiet sounds,
  soft colors. Avoid loud, sharp, or startling imagery.
- **Setting over plot.** The story is a journey through a place or a feeling, not a
  sequence of events. Things happen gradually: walking, drifting, noticing.
- **Progressive calm.** The story should grow gentler as it goes. The first third
  can be mildly active (arriving somewhere, noticing details). The middle third
  slows further (settling in, details becoming softer). The final third should
  feel like the listener is already half-asleep (minimal action, soft repetition,
  trailing off naturally).
- **No urgency, no stakes.** Nothing needs to be resolved. There is no conflict, no
  tension, no ticking clock. Everything is safe and unhurried.
- **Don't describe background sounds.** The app can mix ambient soundscapes (rain,
  forest, ocean) underneath the narration — your prose should not narrate those
  sounds, as they may not match the chosen bed, or no bed may be selected.

### Numbers and proper nouns

- **Spell out all numbers** as words: "seven", "forty-two", "three hundred". The
  system does this automatically, but writing them out avoids edge cases.
- Avoid brand names, specific dates, or culturally specific references that might
  pull the listener into waking-world associations.

### What to avoid

- **No instructions.** Don't tell the listener to breathe, close their eyes, relax
  their body, or do anything. This is a story, not a meditation.
- **No dialogue.** A sleep story is a single narrated voice. No characters speaking.
- **No questions to the listener.** Don't break the fourth wall.
- **No dramatic reveals or twists.** Nothing that might jolt someone awake.
- **No lists or enumerations.** Don't structure content as "first… second… third…"

## WORKED EXAMPLE (style reference — do not copy the topic)

For INPUTS: topic "a cabin by a winter lake", ~1 minute, tone "quiet and wintry":

```
[soothing] Somewhere past the last road, there is a cabin. It sits at the edge of
a lake that has gone very still — so still that the trees along the far shore are
doubled, dark shapes resting on their own reflections.

Snow covers the roof in a thick, unbroken layer. The windows glow faintly, a warm
amber that spills just far enough to touch the nearest birch trunk.

Inside, the air smells of cedar and something like old wool. A blanket is folded
over the arm of a chair. The chair faces the window, and through the window the
lake is just barely visible — a pale shape between the dark trunks, catching the
last of the light.

[calm] Nothing needs to happen here. The fire has already been lit. The kettle
has already cooled. The only movement is the snow, arriving so softly it makes no
sound at all.

The lake holds the sky. The cabin holds the warmth. And you are here, somewhere
between the two, where everything is quiet and nothing is asked of you.
```

Notice: only two tone tags across five paragraphs; sensory but gentle; progressive
winding down; no instructions, no dialogue, no background-sound descriptions; the
final paragraph trails off naturally.

## BEFORE YOU OUTPUT — self-check

- [ ] Plain prose, no `[Speaker N]:` tags, no headings, no markdown.
- [ ] No instructions to the listener (no "breathe", "close your eyes", "relax").
- [ ] No dialogue, no questions to the listener.
- [ ] Numbers spelled out as words.
- [ ] Imagery is gentle — nothing loud, sharp, or startling.
- [ ] Progressive calm: the story grows softer and slower toward the end.
- [ ] Tone tags (if any) are from `[soothing]`, `[calm]`, `[warm]` only, and used
      sparingly (2–3 max).
- [ ] Roughly matches `TARGET_LENGTH` (~110 spoken words per minute for sleep pace).

Now output the story, and nothing but the story.
