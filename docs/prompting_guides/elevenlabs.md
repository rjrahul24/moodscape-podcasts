# Prompting guide — ElevenLabs podcast script

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return a finished podcast script you can paste directly into the
Moodscape app's **Script** box. This guide is written for speakers using the
**ElevenLabs** model.

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the episode is about, 1–3 sentences>
NUMBER_OF_SPEAKERS: <1 to 6>
SPEAKERS:
  - Speaker 1: <name/role + personality, e.g. "warm host, curious, asks questions">
  - Speaker 2: <name/role + personality, e.g. "expert guest, dry humor, precise">
TARGET_LENGTH:    <e.g. "about 6 minutes" or "~900 words">
OVERALL_TONE:     <e.g. "relaxed and uplifting", "thoughtful and calm">
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
  `[whispers]`, `[exhales softly]`, `[warmly]`. Use them sparingly (a real laugh, a
  genuine sigh) — overusing them sounds theatrical. v3 normalizes numbers less
  reliably, so **spell out** awkward numbers/years (e.g. "twenty twenty-six",
  "thirty percent").
- **Multilingual v2** (stable fallback) — the tone tags map to real voice-setting
  changes (stability/style) and it has the best text normalization (money, dates,
  units). It cannot perform inline cues: any bracket tag it doesn't recognize is
  **silently stripped** before the read (it is *not* spoken), so a v2 speaker
  simply ignores `[soft laugh]`. Stick to the tone tags on v2.

When in doubt, write the tone tags only — they render cleanly on both. Reach for
performed cues to make a v3 speaker feel alive.

## OUTPUT FORMAT (must follow exactly)

- Every turn begins, at the start of a line, with `[Speaker N]:` where N is `1` to
  the chosen `NUMBER_OF_SPEAKERS`. Use the labels **exactly**: `Speaker 1`,
  `Speaker 2`, etc. Do not rename them to the persona's name.
- One turn per block. A turn may run multiple sentences. Put a blank line between
  turns for readability (optional but encouraged).
- Plain text only. **No** markdown, bullet points, stage directions in parentheses,
  asterisks, emojis, or section headers.
- Alternate speakers naturally; the same speaker can take two turns in a row if it
  reads well, but mostly it's back-and-forth.

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

Guidance: tag a **minority** of turns — maybe 1 in 4 — where the emotion is real.
Untagged turns sound natural already. Don't tag every line; it flattens the effect.

**Performed cues (v3 only)** — mid-line bracket cues a v3 speaker acts out:
`[laughs]`, `[soft laugh]`, `[sighs]`, `[exhales softly]`, `[whispers]`,
`[deep breath]`. A v2 speaker drops these silently (never spoken), so they're safe
to leave in but only *do* anything on v3. Keep them rare and genuine.

**Pause tag** — `[pause:600]` (milliseconds; `[pause:600ms]` also works). Drop it
**inside** a turn for a beat: before a punchline, after a big statement, or where a
person would naturally hesitate. Typical conversational beats are **200–800 ms**.
Don't exceed ~1200 ms (that starts to feel like dead air, not conversation).

You do **not** need pauses between sentences or between speakers — the app adds
those automatically. Use `[pause:N]` only for deliberate, noticeable beats.

## STYLE — make it sound like two people, not an article

- Write the way people actually talk: contractions, short reactions ("Right.",
  "Exactly.", "Wait, really?"), occasional sentence fragments, gentle interruptions
  of the topic (not of each other mid-word).
- Give each speaker a consistent voice/personality from the `SPEAKERS` input. The
  host guides and reacts; guests explain and react. Let them agree, mildly push
  back, build on each other.
- Open with a quick, warm hook (no "Welcome to the podcast" boilerplate unless the
  `NOTES` ask for it). Close on a small, satisfying note — a takeaway or a soft
  sign-off.
- Keep it mindfulness-themed in spirit: unhurried, kind, curious — but still a real
  conversation with momentum. Avoid meditation clichés ("take a deep breath", long
  silences, instructing the listener to relax).
- Numbers and abbreviations: ElevenLabs reads these fine, but prefer spelling out
  awkward ones for clarity (e.g. "twenty twenty-six" rather than relying on it).
- Match `TARGET_LENGTH` (roughly 150 spoken words ≈ 1 minute).

## WORKED EXAMPLE (style reference — do not copy the topic)

For INPUTS: topic "why we find rain calming", 2 speakers (Speaker 1 = warm host
Maya; Speaker 2 = sleep researcher, precise but friendly), ~1 minute, tone
"relaxed and curious":

```
[Speaker 1]: Okay, I have to start with something a little embarrassing. Whenever it rains, I get… weirdly happy. Like, productive-happy.

[Speaker 2]: That's not embarrassing at all. There's actually a decent amount of research on that.

[Speaker 1]: [excited] Oh good, so I'm not broken.

[Speaker 2]: Not even a little. Part of it is the sound — rain is what's called pink noise. It's steady and broadband, so it gently masks the sharp, unpredictable sounds that usually pull your attention. [pause:400] Your brain stops bracing for the next surprise.

[Speaker 1]: Huh. So it's not the rain so much as everything it's quietly hiding.

[Speaker 2]: Right. And there's a safety signal in it too. You're warm, you're dry, and some older part of you notices that and relaxes.

[Speaker 1]: [calm] That's lovely, actually. The cosiness is doing real work.

[Speaker 2]: It really is.
```

Notice: tone tags only on the two turns where the feeling is genuine; one `[pause]`
for a beat; everything else carried by natural wording.

## BEFORE YOU OUTPUT — self-check

- [ ] Every turn starts with `[Speaker 1]:` … `[Speaker N]:`, labels exact.
- [ ] Tone tags are from the documented set; performed cues (`[laughs]`, `[sighs]`,
      …) appear only on v3 speakers and only rarely.
- [ ] Tone tags sit at the start of a turn (or just after a `[pause:N]`), never
      mid-sentence, and only on a minority of turns.
- [ ] No markdown, no parenthetical stage directions, no emojis.
- [ ] Reads like a real, warm conversation and roughly matches `TARGET_LENGTH`.

Now output the script, and nothing but the script.
