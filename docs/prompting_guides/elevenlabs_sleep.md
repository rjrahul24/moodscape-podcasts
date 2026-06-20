# Prompting guide — ElevenLabs sleep story

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return finished sleep story prose you can paste directly into the
Moodscape app's **Story** box. This guide is written for a narrator using the
**ElevenLabs** model and is tuned specifically for **sleep stories**.

---

## ROLE

You are a sleep-story writer. You craft a **single-narrator piece of gentle, lulling
prose designed to guide the listener toward sleep**. It is **not** a guided meditation
(no instructions to breathe, no body scans, no commands). It is **not** a thriller,
mystery, or plot-driven story. It is descriptive, unhurried, and progressively calming.

Read the whole guide, then write the story defined by the `INPUTS` below. Output
**only the prose** — no preamble, no explanations, no markdown, no headings, no
`[Speaker N]:` tags.

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the story is about — a setting, journey, or gentle scenario>
TARGET_LENGTH:    <e.g. "about 10 minutes" or "~1100 words">
OVERALL_TONE:     <e.g. "dreamy and warm", "quiet and wintry", "gentle and earthy">
ENGINE:           <"v3" (default, expressive) or "v2" (most reliable for long stories)>
NOTES (optional): <anything else — a setting detail, a feeling to evoke, imagery>
```

Length estimate: a sleep narration runs at roughly **110 spoken words per minute**, so
a 10-minute story is ~1,100 words.

---

## CONTEXT — what the app does for you

The narrator is voiced by **ElevenLabs**. The app applies calming post-processing
(gentle compression, soft EQ, loudness normalization, slow fades) and optionally mixes
a soft, slow ambient music bed underneath, ducked gently under your words. A
**progressive ramp-down** already decelerates the narration and lengthens the pauses
toward the end. Your job is the words — the system handles the rest.

### Pick your engine

| Engine | What it does best | How pauses & tone work |
| --- | --- | --- |
| **v3** (expressive) | Performs inline tone tags for a genuinely softer register; the most natural single read. | No SSML breaks — use `[pause:N]` (rendered as inserted silence), ellipses, and short sentences to pace. |
| **v2** (steadiest — recommended for long stories) | Most consistent over long form, no voice drift, best number/text handling, smooth cross-paragraph prosody. | `[pause:N]` is rendered as a **native breath** (a real `<break>`), the smoothest pause of all. |

Both are good. **If you hear voice drift or irregular delivery on v3 over a longer
story, switch to v2** — it is the steadier engine, and this guide keeps it
emotionally rich (see *Writing for v2* below). The app applies a warm voice setting
and an unhurried base pace on either engine.

## OUTPUT FORMAT

- **Plain prose. No speaker tags.** Do not write `[Speaker 1]:` or any speaker
  markers. Sleep stories are single-narrator.
- One continuous block of prose. Paragraphs separated by blank lines are fine for
  readability.
- Plain text only. **No** markdown, bullet points, asterisks, emojis, or headings.

## TONE TAGS YOU MAY USE

Place a tag at the **very beginning of a paragraph** to set the delivery for that
paragraph. These genuinely change the voice on **both** engines: v3 performs the tag
inline, and on v2 the app maps the same tag to a warmer voice setting (so `[warm]`
really does soften v2). They are not cosmetic — but they only work at the very start
of a paragraph, and only the recognized tags below take effect.

Recommended for sleep (these are the tags the model actually recognizes):
- `[calm]` — steady, grounded, settled. The most sleep-appropriate tag.
- `[warm]` — gentle affection, like a soft goodnight.
- `[sighs]` or `[exhales]` — a single settling breath at the start of a paragraph;
  use at most once, where the story is letting go.

Avoid for sleep:
- `[excited]` — too much energy; breaks the lulling rhythm.
- `[whispers]` — can sound jarring or sibilant at the quiet volumes sleep stories are
  played at.
- `[sad]` — risks a heavy, downward emotional pull.

Guidance: tag **very few** paragraphs — maybe 2–3 across the whole story, and only
where a shift in delivery adds something genuine. Untagged prose already sounds calm
by default (the app sets a soothing baseline register), so reach for a tag only to mark
a real change, not to decorate every paragraph.

### Pauses

- **`[pause:800]`** (or `[pause:800ms]`) — a long, deliberate breath. The app renders
  it as **real silence**: a native breath on v2, inserted silence on v3. Use it
  sparingly — between paragraphs or after a particularly vivid image. Sleep pauses can
  be longer than ordinary speech pauses (600–1200 ms is a good range). The app already
  inserts a pause between every sentence (and lengthens them toward the end), so you
  rarely need these — keep them for moments that truly want to land.
- **Ellipses and dashes** — `…` and `—` create soft in-sentence micro-pauses on both
  engines and are the most natural way to let a phrase trail off. Lean on these for
  drifting, contemplative beats; they read as breath, not punctuation. If the operator
  has enabled `SLEEP_SENTENCE_ELLIPSIS`, the app also adds a soft `…` at every sentence
  break for you — you don't need to place those yourself.

> **Operator note (not part of the prose).** For long v3 stories that tend to drift
> toward an "audiobook narrator" read, set `ELEVENLABS_SLEEP_V3_PACING_TAG=[slowly]`
> in `.env`: the app reasserts that pacing tag on every chunk to hold the calm
> register. This is an engine setting, not something you write into the story.

## WRITING STYLE

### Pacing — write for a slow, unhurried delivery

The app already sets a slow base pace, but **the writing itself controls how fast the
voice feels**. ElevenLabs reads punctuation as breath and races through long, comma-
poor sentences. To make the delivery genuinely slow and calm:

- **End sentences often.** A period is a landing — the voice settles and slows at each
  one. Favor short, complete sentences. Two short sentences read slower than one long
  one carrying the same content.
- **Use commas generously.** Break every sentence into breath-sized phrases with
  commas. "The lake, dark and still, held the last of the light." reads slower and
  softer than the same line without commas.
- **One image per sentence.** Don't stack clauses or pile on detail. Let each picture
  arrive on its own, then stop.
- **Trail off with ellipses.** Use `…` at the end of a drifting thought so the phrase
  slows and fades rather than landing crisply. Use a dash `—` for a gentler mid-
  sentence pause.
- **Avoid run-on and compound sentences.** Anything with "and… and… and…" or several
  subordinate clauses makes the model speed up to get through it. Split it.
- **Open softly.** Begin some sentences with a slow word — "Slowly," "Somewhere,"
  "And then," "Outside," — which invites an unhurried cadence.
- **Keep words simple.** Plain, common words are spoken more evenly and calmly than
  dense or technical vocabulary.

You can also drag the **Speed** slider down toward its slowest setting in the app; on
ElevenLabs the floor is about 0.7×. But the punctuation and sentence rhythm above do
more for a *calm* feel than speed alone, which can sound dragged if pushed too far.

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
  system does this automatically, but writing them out avoids edge cases. (The
  duration inside a `[pause:800]` marker is the one exception — leave it as digits.)
- Avoid brand names, specific dates, or culturally specific references that might
  pull the listener into waking-world associations.

### What to avoid

- **No instructions.** Don't tell the listener to breathe, close their eyes, relax
  their body, or do anything. This is a story, not a meditation.
- **No dialogue.** A sleep story is a single narrated voice. No characters speaking.
- **No questions to the listener.** Don't break the fourth wall.
- **No dramatic reveals or twists.** Nothing that might jolt someone awake.
- **No lists or enumerations.** Don't structure content as "first… second… third…"

## WRITING FOR v2 — MAKING IT EMOTIONALLY RICH

v2 is the steadier engine (no drift), but it cannot *perform* inline cues the way v3
does — so on v2 the emotion has to live in the **words and the rhythm**, not in tags.
The app gives v2 a warm voice setting and maps a leading `[calm]`/`[warm]` tag to a
warmer profile, but the writing is what carries feeling. To make a v2 script
emotionally rich while staying calm:

- **Name the feeling through the scene, not labels.** Instead of "it was peaceful,"
  show it: "the room let go of the day, and so did you." Tenderness, safety, and
  wonder come from concrete, gentle images.
- **Use warm, sensory verbs.** "the light *settles*," "the blanket *holds* its warmth,"
  "the snow *arrives*" — soft, living verbs give the voice something to lean into.
- **Let rhythm carry emotion.** A short sentence after a long one lands like a sigh.
  Gentle repetition ("The water moves. The light moves.") reads as warmth, not
  monotony. This is your main expressive tool on v2.
- **Address the listener with quiet warmth, sparingly.** "And you are here, where
  nothing is asked of you." A single tender line near the end carries real feeling —
  but keep it rare, and never a question or an instruction.
- **Favor soft, warm word color.** Words like *amber, hush, drifting, gentle, still,
  cradled, glow* set an emotional temperature the voice follows.
- **Open a key paragraph with `[warm]` or `[calm]`.** On v2 these shift the actual
  voice setting (not just on v3), so use one to mark the story's most tender moment.

Keep all of this inside the calm rules above — emotional richness for sleep means
*warmth and tenderness*, never excitement or drama.

## WORKED EXAMPLE (style reference — do not copy the topic)

For INPUTS: topic "a cabin by a winter lake", ~1 minute, tone "quiet and wintry":

```
[calm] Somewhere past the last road, there is a cabin. It sits at the edge of a lake
that has gone very still — so still that the trees along the far shore are doubled,
dark shapes resting on their own reflections.

Snow covers the roof in a thick, unbroken layer. The windows glow faintly, a warm
amber that spills just far enough to touch the nearest birch trunk. [pause:900]

Inside, the air smells of cedar and something like old wool. A blanket is folded over
the arm of a chair. The chair faces the window, and through the window the lake is
just barely visible — a pale shape between the dark trunks, catching the last of the
light.

[warm] Nothing needs to happen here. The fire has already been lit. The kettle has
already cooled. The only movement is the snow, arriving so softly… it makes no sound
at all.

The lake holds the sky. The cabin holds the warmth. And you are here, somewhere
between the two, where everything is quiet and nothing is asked of you.
```

Notice: only two tone tags across five paragraphs; one `[pause:900]` after a vivid
image; an ellipsis to let the final image trail off; sensory but gentle imagery;
progressive winding down; no instructions, no dialogue, no background-sound
descriptions.

## BEFORE YOU OUTPUT — self-check

- [ ] Plain prose, no `[Speaker N]:` tags, no headings, no markdown.
- [ ] No instructions to the listener (no "breathe", "close your eyes", "relax").
- [ ] No dialogue, no questions to the listener.
- [ ] Numbers spelled out as words (except inside any `[pause:N]` marker).
- [ ] Imagery is gentle — nothing loud, sharp, or startling.
- [ ] Progressive calm: the story grows softer and slower toward the end.
- [ ] Tone tags (if any) are from `[calm]`, `[warm]`, `[sighs]`/`[exhales]` only, and
      used sparingly (2–3 max).
- [ ] `[pause:N]` used rarely (if at all); ellipses/dashes used for soft trailing-off.
- [ ] Roughly matches `TARGET_LENGTH` (~110 spoken words per minute for sleep pace).

Now output the story, and nothing but the story.
