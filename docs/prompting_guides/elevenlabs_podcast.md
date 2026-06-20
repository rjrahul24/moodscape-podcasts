# Prompting guide — ElevenLabs podcast script

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return a finished podcast script you can paste directly into the
Moodscape app's **Script** box. This guide is written for speakers using the
**ElevenLabs** model and is tuned specifically for **podcast** episodes.

---

## INPUTS — edit these, then send everything below to the LLM

```
SERIES_NAME:      <e.g. "The Shared Space">
SPEAKER_NAMES:    <e.g. "Maya and Kai" — persona names used in the intro/outro>
TOPIC:            <what the episode is about, 1–3 sentences>
NUMBER_OF_SPEAKERS: <1 to 6>
SPEAKERS:
  - Speaker 1: <name/role + personality, e.g. "Maya — warm host, curious, asks follow-ups">
  - Speaker 2: <name/role + personality, e.g. "Kai — thoughtful co-host, dry humor, precise">
TARGET_LENGTH:    <e.g. "about 6 minutes" or "~900 words">
OVERALL_TONE:     <e.g. "relaxed and uplifting", "thoughtful and calm">
INTRO_STYLE:      <e.g. "warm, brief, branded" — how the opening should feel>
NOTES (optional): <anything else — facts to include, a hook, an ending beat>
```

---

## YOUR TASK

You are a scriptwriter for a **mindfulness-themed conversational podcast** — a warm,
natural discussion between real-sounding people, **not** a guided meditation and not
a lecture. Using the `INPUTS` above, write a complete episode script in the exact
format defined below. Output **only the script** — no preamble, no explanations, no
markdown, no headings.

The speakers are voiced by **ElevenLabs**, the most expressive engine available
here. Lean into that: vary energy, let people react to each other, use the tone
tags meaningfully. ElevenLabs handles long, complex sentences and normal
punctuation well, so you can write naturally.

### Which ElevenLabs model? (v3 vs v2)

In the app you pick a model per ElevenLabs speaker. The script format is the
same; only how expressive the read gets differs:

- **v3 (expressive — the default)** — performs **inline audio tags** the model
  acts out. In addition to the tone tags below, on a v3 speaker you may sprinkle a
  *few* performed cues **mid-line**, e.g. `[laughs]`, `[soft laugh]`, `[sighs]`,
  `[exhales softly]`, `[whispers]`, `[warmly]`. Use them sparingly — a real laugh, a
  genuine sigh — overusing them sounds theatrical. Aim for **2–4 performed cues
  across the entire episode**, no more. v3 normalizes numbers less reliably, so
  **spell out** awkward numbers/years (e.g. "twenty twenty-six", "thirty percent").
- **Multilingual v2** (stable fallback) — the tone tags map to real voice-setting
  changes (stability/style) and it has the best text normalization (money, dates,
  units). It cannot perform inline cues: any bracket tag it doesn't recognize is
  **silently stripped** before the read (it is *not* spoken), so a v2 speaker
  simply ignores `[soft laugh]`. Stick to the tone tags on v2.

When in doubt, write the tone tags only — they render cleanly on both. Reach for
performed cues to make a v3 speaker feel alive.

## OUTPUT FORMAT (must follow exactly)

### Section markers

The script has three sections. Mark each with a standalone line:

- `[INTRO]` — the branded opening (show name, speaker names, topic tease)
- `[BODY]` — the main conversation
- `[OUTRO]` — the branded closing (takeaway, sign-off)

These markers must appear **on their own line**, with no colon and no text after
them. They are consumed by the app and do not produce audio themselves.

### Speaker turns

- Every turn begins, at the start of a line, with `[Speaker N]:` where N is `1` to
  the chosen `NUMBER_OF_SPEAKERS`. Use the labels **exactly**: `Speaker 1`,
  `Speaker 2`, etc. Do not rename them to the persona's name.
- One turn per block. A turn may run multiple sentences. Put a blank line between
  turns for readability (optional but encouraged).
- Plain text only. **No** markdown, bullet points, stage directions in parentheses,
  asterisks, emojis, or section headers.
- Alternate speakers naturally; the same speaker can take two turns in a row if it
  reads well, but mostly it's back-and-forth.

## SECTION STRUCTURE

### Intro — branded, consistent, brief

The intro is the signature opening of `SERIES_NAME`. It should feel **warm and
repeatable** — the same bones every episode, only the topic changes. Think of how
real branded podcasts open: a recognizable greeting, both speakers introduce
themselves by their persona names from `SPEAKER_NAMES`, and a brief tease of
today's topic.

Guidelines for the intro:
- **Target ~20 seconds of spoken words** (roughly 50 words at podcast pace). The
  app adds 10 seconds of music-only pre-roll before speech begins, so the total
  intro is ~30 seconds — but you only write the spoken part.
- **2–4 turns total** (not longer). Quick and inviting.
- Speaker 1 opens with a greeting that names the show: e.g. "Welcome to
  [SERIES_NAME]" or "Hey, you're listening to [SERIES_NAME]."
- Each speaker introduces themselves by persona name (from `SPEAKER_NAMES`).
- One speaker teases the topic — a single sentence or question, not a summary.
- Tone: warm and welcoming. Use `[warm]` or leave untagged. Keep it light.
- **Music plays underneath** the spoken intro (added by the app), so keep
  sentences clear and not too fast. The music is quiet but present — speak
  naturally, not over it.

### Body — the real conversation

This is the meat of the episode. No music plays here — just voices.

- Write the way people actually talk: contractions, short reactions ("Right.",
  "Exactly.", "Wait, really?"), occasional sentence fragments, gentle redirections.
- Give each speaker a consistent voice/personality from the `SPEAKERS` input. Let
  them agree, mildly push back, build on each other.
- Follow an **emotional arc**:
  - **Opening third**: curious, exploratory — questions, gentle probing, "I've been
    thinking about this…"
  - **Middle third**: engaged, substantive — the deepest content, genuine reactions,
    maybe a light disagreement or a surprising fact
  - **Final third**: reflective, settling — drawing threads together, softening the
    energy, noting what resonated
- Avoid meditation clichés ("take a deep breath", long silences, instructing the
  listener to relax). This is a conversation, not a guided exercise.
- Match `TARGET_LENGTH` (roughly 150 spoken words per minute).

### Outro — branded sign-off, consistent

The outro mirrors the intro: a recognizable closing that feels like the same
show. The app will add **music underneath** this section too.

Guidelines for the outro:
- **Target ~15 seconds of spoken words** (roughly 35–40 words). After the last
  word, 15 seconds of music plays alone as the show fades out — you don't write
  anything for that part, the app handles it.
- **2–3 turns total.** Don't drag it out.
- A soft takeaway or reflection — one sentence that captures the heart of this
  episode's topic.
- A sign-off that names the show: e.g. "Thanks for spending this time in
  [SERIES_NAME]" or "That's it for this episode of [SERIES_NAME]."
- Optionally: "Until next time", "Be kind to yourselves", or similar — a
  warm, repeatable closer.
- Tone: `[warm]` or `[soothing]`. Gentle energy.
- **Music plays underneath** and continues after the last word, so end cleanly
  — don't trail off mid-sentence.

## TAGS YOU MAY USE

**Tone tags** — place at the **very start of a turn**, or immediately after a
`[pause:N]`. The tone colors the rest of that turn. On ElevenLabs these change the
actual voice settings (v2) or pick a performed delivery (v3), so they're genuinely
expressive:

- `[excited]` — higher energy, animated (revelations, enthusiasm, good news)
- `[calm]` — steady, grounded (reassurance, settling a point)
- `[sad]` — softer, slower, heavier (somber or tender moments)
- `[whispering]` — hushed, intimate (a secret, a gentle aside)
- `[warm]` — gentle affection, encouraging
- `[soothing]` — slow and softening (winding down a thread)
- `[reflective]` — thoughtful, considered (mulling something over)
- `[neutral]` — plain, even (default; you rarely need to write it)

Guidance: tag a **minority** of turns — roughly 1 in 4 in the body — where the
emotion is real. Untagged turns sound natural already. Don't tag every line; it
flattens the effect. The intro and outro may have 1–2 tags each (typically `[warm]`).

**Performed cues (v3 only)** — mid-line bracket cues a v3 speaker acts out:
`[laughs]`, `[soft laugh]`, `[sighs]`, `[exhales softly]`, `[whispers]`,
`[deep breath]`. A v2 speaker drops these silently (never spoken), so they're safe
to leave in but only *do* anything on v3.

Best practices for performed cues:
- **2–4 total per episode.** Less is more.
- Place them where a real person would genuinely react — after a surprising fact, a
  fond memory, a joke that lands.
- `[laughs]` and `[soft laugh]` are the most natural. `[sighs]` works for wistful
  or heavy moments. `[exhales softly]` for settling or relief.
- Don't stack them (no `[laughs] [sighs]` in sequence).
- Don't put them at the very start of a turn — that's where tone tags go.

**Pause tag** — `[pause:600]` (milliseconds; `[pause:600ms]` also works). Drop it
**inside** a turn for a beat. Use these calibrated ranges:

| Duration | Feel | When to use |
| --- | --- | --- |
| 200–400 ms | Quick beat, like a comma | Between related clauses, collecting a thought |
| 400–600 ms | Emphasis | After a key point, before a reveal |
| 600–800 ms | Topic shift or dramatic | Changing direction, letting something land |

Don't exceed ~1000 ms (that starts to feel like dead air, not conversation). You do
**not** need pauses between sentences or between speakers — the app adds those
automatically. Use `[pause:N]` only for deliberate, noticeable beats.

## STYLE — make it sound like two people, not an article

- Write the way people actually talk: contractions, short reactions ("Right.",
  "Exactly.", "Wait, really?"), occasional sentence fragments, gentle interruptions
  of the topic (not of each other mid-word).
- Give each speaker a consistent voice/personality from the `SPEAKERS` input. The
  host guides and reacts; guests explain and react.
- Numbers and abbreviations: ElevenLabs reads these well, but prefer spelling out
  awkward ones for clarity (e.g. "twenty twenty-six" rather than "2026").
- Keep it mindfulness-themed in spirit: unhurried, kind, curious — but still a real
  conversation with momentum.

## WORKED EXAMPLE (style reference — do not copy the topic)

For INPUTS: series "The Shared Space", speakers "Maya and Kai", topic "why we
find rain calming", 2 speakers (Speaker 1 = Maya, warm host; Speaker 2 = Kai,
thoughtful co-host), ~2 minutes, tone "relaxed and curious":

```
[INTRO]
[Speaker 1]: [warm] Hey, welcome to The Shared Space. I'm Maya.

[Speaker 2]: And I'm Kai. Today we're asking a question that might sound too simple — why does rain make everything feel… better?

[BODY]
[Speaker 1]: Okay so I have to start with something a little embarrassing. Whenever it rains, I get weirdly happy. Like, productive-happy.

[Speaker 2]: That's not embarrassing at all. There's actually a decent amount of research on that.

[Speaker 1]: [excited] Oh good, so I'm not broken.

[Speaker 2]: Not even a little. Part of it is the sound — rain is what's called pink noise. It's steady and broadband, so it gently masks the sharp, unpredictable sounds that usually pull your attention. [pause:500] Your brain stops bracing for the next surprise.

[Speaker 1]: Huh. So it's not the rain so much as everything it's quietly hiding.

[Speaker 2]: Right. And there's a safety signal in it too. You're warm, you're dry, and some older part of you notices that and relaxes.

[Speaker 1]: [reflective] That's lovely, actually. The cosiness is doing real work.

[Speaker 2]: It really is. There's even a Japanese word for it — komorebi isn't quite it, but the feeling of sheltered comfort while nature does its thing — that's hardwired.

[Speaker 1]: I love that. Next time it rains I'm going to sit there and feel very scientifically validated. [soft laugh]

[Speaker 2]: [warm] As you should.

[OUTRO]
[Speaker 1]: [warm] So maybe the takeaway is — let yourself enjoy the simple things. They're doing more than you think.

[Speaker 2]: Thanks for spending this time in The Shared Space. Until next time — be kind to yourselves.
```

Notice: tone tags on ~4 turns where the feeling is genuine; one `[pause]` for a
dramatic beat; one `[soft laugh]` performed cue; `[INTRO]`, `[BODY]`, `[OUTRO]`
section markers on their own lines; intro names the show and both speakers; outro
signs off with the show name.

## BEFORE YOU OUTPUT — self-check

- [ ] Script begins with `[INTRO]`, has `[BODY]`, and ends with `[OUTRO]` — each
      on its own line with no colon.
- [ ] Every turn starts with `[Speaker 1]:` … `[Speaker N]:`, labels exact.
- [ ] Intro names the series (from `SERIES_NAME`) and both speakers introduce
      themselves by persona name (from `SPEAKER_NAMES`).
- [ ] Outro includes the series name and a consistent sign-off.
- [ ] Tone tags are from the documented set; performed cues (`[laughs]`, `[sighs]`,
      …) appear only rarely (2–4 total) and only on v3 speakers.
- [ ] Tone tags sit at the start of a turn (or just after a `[pause:N]`), never
      mid-sentence, and only on a minority of turns.
- [ ] No markdown, no parenthetical stage directions, no emojis.
- [ ] Body follows an emotional arc (curious → engaged → reflective).
- [ ] Reads like a real, warm conversation and roughly matches `TARGET_LENGTH`.

Now output the script, and nothing but the script.
