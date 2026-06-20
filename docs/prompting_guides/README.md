# Podcast & sleep story prompting guides

These guides are **prompts you hand to an LLM** (ChatGPT, Claude, etc.) to write a
complete, paste-ready Moodscape script or prose. Each guide is fully self-contained:
copy one whole file into the LLM, fill in the inputs block at the top, and it will
return content you can paste straight into the app.

## Which guide do I use?

Pick by **content type** and **TTS model**:

### Podcasts

| Your model | Use this guide | Why it differs |
| --- | --- | --- |
| **ElevenLabs** (cloud) | [`elevenlabs_podcast.md`](elevenlabs_podcast.md) | Most expressive; tone tags map to real voice-setting changes. Handles long, complex sentences. Includes `[INTRO]`/`[BODY]`/`[OUTRO]` section markers for branded series with music. Pick **v3** (performs inline audio tags) or **v2** (best normalization) per speaker. |
| **Kokoro** (local, built-in voices) | [`kokoro.md`](kokoro.md) | Fixed-character voices; tone only nudges speaking rate. Prefers shorter sentences. |
| **F5** (local, voice cloning) | [`f5.md`](f5.md) | Voice cloned from a reference clip; tone nudges rate; emotion is anchored to the reference. Shortest sentence budget. |

### Sleep stories

| Your model | Use this guide | Why it differs |
| --- | --- | --- |
| **ElevenLabs** (cloud) | [`elevenlabs_sleep.md`](elevenlabs_sleep.md) | Calming prose for single-narrator sleep stories. Tone tags (`[soothing]`, `[calm]`) genuinely shift the voice. Guidance on rhythm, imagery, and progressive winding down. |
| **Other models** | No dedicated guide yet | Write plain, gentle prose. The app's sleep post-processing (loudness normalization, compression, fades) does the heavy lifting regardless of model. |

### Mixing models across speakers (podcasts only)

The app lets each speaker use a different model. If your podcast mixes models
(e.g. Speaker 1 = ElevenLabs, Speaker 2 = Kokoro), follow the **most constrained**
guide for the whole script — that's [`kokoro.md`](kokoro.md) or [`f5.md`](f5.md)
(use F5's guide if any speaker is F5). Conservative phrasing always renders well on
the more expressive models too.

## What every guide already knows (shared format)

All podcast guides produce the **same script format** — they only differ in style
advice and which tags do something audible. The format the app parses:

- Each turn starts with `[Speaker N]:` at the **start of a line**. Labels must be
  exactly `Speaker 1`, `Speaker 2`, … up to `Speaker 6` (they must match the
  speakers you set up in the UI, or the app refuses to generate).
- One turn per block; a turn may wrap across multiple lines until the next
  `[Speaker N]:` marker.
- **Section markers** (optional, for branded series): `[INTRO]`, `[BODY]`,
  `[OUTRO]` on their own line. When a series is selected in the app, the system
  mixes music under intro and outro sections. Without markers, all turns are
  treated as body (no music). See
  [`elevenlabs_podcast.md`](elevenlabs_podcast.md) for full section guidance.
- **Inline tags** (all optional, all handled by the app regardless of model):
  - `[pause:600]` or `[pause:600ms]` — insert a silence of that many milliseconds
    at that exact spot in the turn.
  - `[excited]` `[calm]` `[sad]` `[whispering]` `[neutral]` — set the tone for the
    rest of that turn (or until the next `[pause:N]`). **Only recognized at the
    very start of a turn or immediately after a `[pause:N]`** — never mid-sentence.
  - Any **other** bracketed text (e.g. `[laughs]`, `[sighs]`) is **not** understood
    by the app and is passed through to the model untouched. On most models that
    means it's read aloud literally — so the guides avoid inventing tags. The one
    exception is an **ElevenLabs v3** speaker, which *performs* such cues; see
    [`elevenlabs_podcast.md`](elevenlabs_podcast.md) for the v3 audio-tag note.
- The app's **Natural pacing** toggle (on by default) already adds sentence
  micro-pauses, slight speed variation, and varied gaps between turns — so the
  scripts don't need to over-punctuate to sound human.

> **Scope:** Moodscape podcasts are *mindfulness-themed conversations*, not guided
> meditations. Sleep stories are *calming prose narratives*, not guided meditation
> scripts. The guides aim for natural content — not slow, breathy meditation reads.

## How to use a guide

1. Open the guide for your content type and model, and copy the **entire file**.
2. Paste it into your LLM.
3. Replace the `INPUTS` block at the top (topic, speakers/length/tone, etc.).
4. Send. The LLM returns only the script or prose.
5. Paste into the app:
   - **Podcast**: paste into the **Script** box, assign each `Speaker N` the
     matching model + voice, optionally select a Series for branded music, and
     generate.
   - **Sleep story**: paste into the **Story** box, pick a voice and optional
     ambient bed, and generate.
