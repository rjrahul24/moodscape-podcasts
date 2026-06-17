# Prompting guide — Kokoro podcast script

Copy this **entire file** into your LLM, fill in the `INPUTS` block, and send. The
LLM will return a finished podcast script you can paste directly into the
Moodscape app's **Script** box. This guide is written for speakers using the
**Kokoro** model (local, built-in voices).

---

## INPUTS — edit these, then send everything below to the LLM

```
TOPIC:            <what the episode is about, 1–3 sentences>
NUMBER_OF_SPEAKERS: <1 to 6>
SPEAKERS:
  - Speaker 1: <name/role + personality, e.g. "warm host, curious, asks questions">
  - Speaker 2: <name/role + personality, e.g. "expert guest, friendly, clear">
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

The speakers are voiced by **Kokoro**, a local engine with fixed-character voices.
Important consequence for how you write:

- **Kokoro does not change its emotional delivery from tone tags** — a tone tag only
  nudges the **speaking rate** slightly (e.g. excited = a touch faster, sad/calm = a
  touch slower). The voice's pitch and character are fixed per voice. So **emotion
  has to live in the words themselves**, not in tags.
- Kokoro prefers **shorter, cleaner sentences**. Long, comma-heavy sentences can
  sound rushed or get split awkwardly. Keep most sentences under ~25 words.

## OUTPUT FORMAT (must follow exactly)

- Every turn begins, at the start of a line, with `[Speaker N]:` where N is `1` to
  the chosen `NUMBER_OF_SPEAKERS`. Use the labels **exactly**: `Speaker 1`,
  `Speaker 2`, etc. Do not rename them to the persona's name.
- One turn per block. Put a blank line between turns (encouraged).
- Plain text only. **No** markdown, bullet points, parenthetical stage directions,
  asterisks, emojis, or section headers.
- Mostly back-and-forth between speakers.

## TAGS YOU MAY USE

These are the **only** tags the app understands. Anything else in brackets (e.g.
`[laughs]`, `[sighs]`) is read aloud literally — so **don't** use it.

**Pause tag — your main tool on Kokoro.** `[pause:600]` (milliseconds;
`[pause:600ms]` also works) inserts a real silence at that spot. Because Kokoro
can't act emotion, **rhythm is how you make it feel human**: a beat before a
reveal, a short hesitation, a pause after a strong line. Typical beats are
**250–800 ms**; don't exceed ~1200 ms.

**Tone tags** — `[excited]` `[calm]` `[sad]` `[whispering]` `[neutral]`. Allowed,
but on Kokoro they only change rate slightly, so use them **sparingly** and only
where a small pace change helps (e.g. `[excited]` for an animated burst, `[calm]`
to settle). Place them at the **very start of a turn** or right after a `[pause:N]`
— never mid-sentence. Don't rely on them to carry feeling; the wording must.

You do **not** need pauses between sentences or between speakers — the app's
Natural pacing adds those automatically and varies the rate a little per chunk.

## STYLE — emotion through words, not tags

- Carry feeling with **word choice and reactions**, since the voice won't emote:
  "Honestly, that gave me chills." / "Wait — that changes everything." / "Oh, I
  love that."
- Write the way people talk: contractions, short reactions, the occasional
  fragment. Keep sentences short and concrete — easier for Kokoro to render
  cleanly.
- Give each speaker a steady personality from `SPEAKERS`. Host guides and reacts;
  guest explains simply. Let them agree and gently build on each other.
- Spell out anything Kokoro might mangle: write numbers and years as words
  ("twenty twenty-six", "about three hundred"), expand symbols ("percent" not "%",
  "and" not "&"), and avoid abbreviations and stylized punctuation.
- Open with a quick warm hook; close on a small takeaway. Stay mindfulness-themed in
  spirit (unhurried, kind, curious) but keep real conversational momentum — no
  meditation clichés or instructions to the listener.
- Match `TARGET_LENGTH` (roughly 150 spoken words ≈ 1 minute).

## WORKED EXAMPLE (style reference — do not copy the topic)

For INPUTS: topic "why we find rain calming", 2 speakers (Speaker 1 = warm host
Maya; Speaker 2 = friendly researcher), ~1 minute, tone "relaxed and curious":

```
[Speaker 1]: I have a small confession. When it rains, I get weirdly happy. [pause:300] Productive, even.

[Speaker 2]: That's not strange at all. There's real research behind it.

[Speaker 1]: Oh good. So I'm not broken.

[Speaker 2]: Not at all. A lot of it is the sound. Rain is steady and even. [pause:400] It quietly covers the sharp, sudden noises that usually grab your attention.

[Speaker 1]: So my brain stops waiting for the next surprise.

[Speaker 2]: Exactly. And there's comfort in it too. You're warm and dry, and some older part of you notices that. [pause:300] It lets you settle.

[Speaker 1]: That's really lovely. The cosiness is doing the work.

[Speaker 2]: It honestly is.
```

Notice: short sentences; feeling carried by the words; pauses (not tags) doing the
emotional timing.

## BEFORE YOU OUTPUT — self-check

- [ ] Every turn starts with `[Speaker 1]:` … `[Speaker N]:`, labels exact.
- [ ] Only `[pause:N]` and the five tone tags appear in brackets — nothing else.
- [ ] Most sentences are short (~under 25 words); numbers/symbols spelled out.
- [ ] Emotion is in the wording; tone tags used sparingly; pauses used for rhythm.
- [ ] No markdown, no parenthetical directions, no emojis.
- [ ] Reads like a real, warm conversation and roughly matches `TARGET_LENGTH`.

Now output the script, and nothing but the script.
