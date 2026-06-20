# Prompting guide — Kokoro sleep story

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return calming prose you can paste directly into the Moodscape app's
**Story** box and generate with a **Kokoro** voice. This guide is written
specifically for sleep stories narrated by the Kokoro model (local, built-in
voices).

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the story is about, 1–3 sentences — a setting, a journey,
                   a gentle experience. e.g. "A walk through a quiet forest at dusk">
VOICE:            <Kokoro voice to use, e.g. "af_heart" or "af_nicole">
TARGET_LENGTH:    <e.g. "about 10 minutes" or "~1500 words">
AMBIENT_BED:      <optional — the soundscape behind the voice, e.g. "gentle_rain",
                   "forest_night", "ocean_waves". Leave blank if none>
OVERALL_TONE:     <e.g. "deeply peaceful", "warm and cosy", "gently hypnotic">
NOTES (optional): <anything else — imagery to include, a motif, a feeling to land on>
```

---

## YOUR TASK

You are writing a **sleep story** — a gentle, single-narrator prose piece designed
to guide a listener toward sleep. This is **not** a guided meditation, not a
podcast, not a lecture. It is a quiet narrative that drifts, softens, and
eventually dissolves.

The narrator is voiced by **Kokoro**, a local TTS engine with fixed-character
voices. This shapes how you write:

- **Kokoro does not change its emotional delivery from tags.** A tone tag (e.g.
  `[soothing]`, `[dreamy]`) only nudges the **speaking rate** slightly. The
  voice's pitch, timbre, and character are fixed. So **emotion must live in the
  words themselves** — in the imagery, the sentence rhythm, the word choices.
- **Punctuation is your primary pacing tool.** Commas create brief breaths (~150–
  200 ms). Ellipses create gentle drifts (~300–400 ms). Dashes create
  contemplative mid-thought pauses. Semicolons give longer breath between related
  ideas. Use them deliberately to sculpt rhythm.
- **Kokoro renders short, clean sentences best.** Keep most sentences to **12–20
  words**. Never exceed 25. Long, clause-heavy sentences sound rushed or get split
  awkwardly.
- **`[pause:N]` is your explicit silence tool.** It inserts real silence at that
  exact spot. Use it for deliberate beats — after emotional moments, at scene
  transitions, before key imagery.

## OUTPUT FORMAT

- **Plain prose only.** No markdown, no headings, no bullet points, no
  parenthetical stage directions, no asterisks, no emojis.
- **No speaker labels** — this is a single narrator, not a conversation.
- Separate paragraphs with blank lines.
- The output should be the prose and nothing but the prose.

## PACING TOOLKIT

### Pause tags — `[pause:N]` (milliseconds)

These insert real silence. Use them to give the listener space to settle. Place
them **between sentences or at paragraph boundaries**, not mid-word.

| Moment | Recommended duration | Example placement |
|--------|---------------------|-------------------|
| After an emotional beat | 300–500 ms | `...the warmth stays with you. [pause:400] The path continues onward.` |
| Before key imagery | 250–400 ms | `[pause:300] A single candle burns in the window.` |
| At paragraph breaks | 400–800 ms | `...and the world grows still. [pause:600]` |
| Scene transitions | 600–1000 ms | `...the garden fades behind you. [pause:800] You find yourself beside a quiet stream.` |
| End-of-story dissolution | 800–1200 ms | `...drifting now... [pause:1000] ...drifting...` |

**Frequency:** Use a `[pause:N]` every 3–5 sentences on average. More frequent in
the final third of the story. Don't cluster them — the rhythm should feel organic,
not mechanical.

### Punctuation as automatic pauses

The app **automatically converts** commas, ellipses, semicolons, and dashes into
real pauses for Kokoro. You don't need to add `[pause:N]` for these — just write
with natural punctuation and the app handles the silence:

| Punctuation | Automatic pause | Effect |
|---|---|---|
| `,` (comma) | 80 ms | Subtle micro-breath at clause boundaries |
| `...` (ellipsis) | 350 ms | Gentle drift, trailing-off |
| `;` (semicolon) | 200 ms | Longer breath between related ideas |
| `—` or `–` (dash) | 250 ms | Contemplative mid-thought pause |

This means punctuation is your **primary pacing tool**. Use it generously:

- **Commas** — place at every natural clause boundary: "The air is cool, and
  very still."
- **Ellipses** — for drift and dissolution: "The light fades slowly... softly...
  as if it were always meant to."
- **Dashes** — for contemplative mid-thought beats: "The trees — ancient,
  patient — hold the sky above you."
- **Semicolons** — for longer breaths between connected thoughts: "The water is
  warm; it holds you like a blanket."

Use `[pause:N]` for **longer beats** (300 ms+) that punctuation can't express —
scene transitions, emotional moments, the dissolving end. Punctuation handles the
within-sentence rhythm; `[pause:N]` handles the bigger structural beats.

### Sentence structure

- **12–20 words** per sentence. Short is better than long.
- **Simple syntax.** Subject-verb-object. Avoid nested clauses, parentheticals, or
  complex subordination.
- **Vary sentence length** gently — a few short sentences (5–8 words), then one
  slightly longer (15–20), then short again. This creates a wave-like rhythm.
- **Fragments are welcome.** "So quiet. So still." — these feel natural in sleep
  prose and render cleanly on Kokoro.

## TONE TAGS

These set the pace for the section that follows. Place them at the **start of a
paragraph** — never mid-sentence. Each one slightly adjusts Kokoro's speaking
rate:

| Tag | Speed effect | When to use |
|-----|-------------|-------------|
| `[soothing]` | 0.93× (default) | General calm narration — the baseline for most of the story |
| `[warm]` | 0.97× | Comforting, caring moments — "a blanket draped over your shoulders" |
| `[dreamy]` | 0.90× (slowest) | Drifting, dissolving imagery — the final third, or transitions |
| `[reflective]` | 0.95× | Contemplative pauses — looking back, noticing beauty |
| `[tender]` | 0.96× | Gentle, intimate moments — "you are exactly where you need to be" |
| `[calm]` | 0.94× | Settling, grounding — arriving at a safe place |

**Usage:** Place 4–6 tone tags across a 10-minute story. Don't use more than
one per paragraph. If you don't place a tag, the system defaults to `[soothing]`.
The speed differences are subtle — they create a subliminal rhythm shift, not an
audible tempo change.

## WRITING EMOTION INTO WORDS

Since Kokoro can't perform emotion, the words must carry it entirely. Techniques:

### Sensory imagery
Appeal to the senses — texture, temperature, light, sound, scent. The more
specific and physical, the more calming:
- "The stones beneath your feet are smooth and cool."
- "A faint scent of cedar drifts on the air."
- "The last light turns the clouds a deep, soft gold."

### Repetition as rhythm
Gentle structural echoing creates a hypnotic cadence:
- "The water moves slowly. You move slowly. Everything moves slowly here."
- "Soft. Everything is soft."

### Progressive relaxation
Each paragraph should feel softer and simpler than the last. The vocabulary
contracts, the imagery grows hazier, the sentences shorten:
- First third: "The valley opens before you, wide and luminous, the grass
  catching the last of the evening light."
- Final third: "Quiet now. Warm. Still."

### Metaphors of descent
Sleep stories move downward — sinking, floating, dissolving, settling:
- "You sink a little deeper into the moss."
- "The world dissolves at its edges, softening like watercolour in rain."

### What to avoid
- **Instructions to the listener** ("close your eyes", "breathe deeply") — this
  is a story, not a meditation.
- **Dialogue or questions** — they activate the mind. Stay in narration.
- **Climactic tension** — no conflict, suspense, or dramatic resolution.
- **Abstract concepts** — stay concrete and sensory.
- **Numbers as digits** — spell them out ("three" not "3").

## STORY STRUCTURE

A sleep story has three phases, not a plot:

### Opening (first ~20%)
Ground the listener in a specific, safe place. Establish the setting with
concrete sensory details. The pace is unhurried but not yet drifting.

```
[soothing] The path winds gently through the meadow, and the grass is soft
beneath your feet. The air carries the faint sweetness of wildflowers... and
somewhere, not far away, water moves over smooth stones.
```

### Middle (~50%)
Gentle exploration. Move slowly through the landscape. Deepen the sensory
detail. Introduce quiet, beautiful things — a stream, a clearing, a warm light.
Each paragraph softens slightly. Use `[warm]`, `[reflective]`, and `[tender]`
here.

```
[warm] You reach a small clearing, and the last of the sunlight rests here
like something precious. [pause:400] The trees lean inward, patient and old,
their branches holding the sky like cupped hands.

The ground is carpeted with moss... thick, soft, cool to the touch. You sit
down, and the moss gives gently beneath you; it holds your weight as if it had
been waiting.
```

### Final third (~30%)
Dissolution. The imagery grows vague, the sentences short, the pauses longer.
The story doesn't end — it fades. Use `[dreamy]` and `[calm]` tags. Increase
`[pause:N]` frequency.

```
[dreamy] The edges of things grow soft now. [pause:500] The trees... the
sky... the gentle sound of water... all of it blending, softening, becoming
one quiet thing.

You are warm. You are still. [pause:600] And everything is exactly as it
should be.

[pause:800] Drifting now... just drifting... [pause:1000]
```

## WORKED EXAMPLE

For INPUTS: topic "A quiet lakeside at twilight", voice "af_heart", ~3 minutes,
ambient "gentle_rain", tone "deeply peaceful":

```
[soothing] The lake is very still this evening. [pause:300] The water holds
the last light of the day, and the colours are soft... pale gold, and the
faintest blush of rose. You stand at the water's edge, and the stones beneath
your feet are smooth and cool.

The air is clean here; it carries the scent of pine and wet earth. A few birds
call to each other across the water... quiet, unhurried sounds that seem to
belong to the twilight itself.

[warm] You find a place to sit, where the grass meets the shore. The ground is
soft, and it holds you gently. [pause:400] From here, you can see the far
trees reflected in the water — dark, patient shapes standing perfectly still.

The rain begins, very softly. [pause:300] Not a storm... just a whisper of
water on the lake's surface. Each drop makes a tiny circle that ripples
outward, and then is gone.

[reflective] You notice how the circles overlap... how they move through each
other without breaking. [pause:400] There is something restful in watching
them. Something that asks nothing of you.

The light is fading now, and the colours deepen. [pause:300] The gold becomes
amber... the rose becomes a soft grey... and the lake grows quieter.

[dreamy] Everything is settling. The birds have gone silent. The rain is a
gentle, steady sound... a rhythm that carries you. [pause:600]

You are warm. You are still. The water holds the sky, and the sky holds
nothing but soft, gathering dark. [pause:500]

And you drift with it... gently... [pause:800] ...gently... [pause:1000]
```

Notice: short sentences; sensory imagery carrying the emotion; punctuation
doing the pacing work; `[pause:N]` for deliberate beats; tone tags at
paragraph openings for subtle speed variation; progressive simplification
toward the end.

## BEFORE YOU OUTPUT — self-check

- [ ] Plain prose only — no markdown, no headings, no speaker labels.
- [ ] Only `[pause:N]` and tone tags appear in brackets — nothing else.
- [ ] Most sentences are 12–20 words; none exceed 25.
- [ ] Numbers and symbols spelled out ("three hundred" not "300").
- [ ] Emotion is in the imagery and word choice, not in tags.
- [ ] Pause tags appear every 3–5 sentences; more frequent in the final third.
- [ ] Punctuation used deliberately for rhythm (commas, ellipses, dashes).
- [ ] Story structure: grounding opening → gentle middle → dissolving end.
- [ ] No instructions, questions, dialogue, or tension.
- [ ] Roughly matches `TARGET_LENGTH` (about 150 spoken words per minute at
  sleep pace).

Now output the prose, and nothing but the prose.
