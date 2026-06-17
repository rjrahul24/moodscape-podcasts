# Podcast script prompting guides

These guides are **prompts you hand to an LLM** (ChatGPT, Claude, etc.) to write a
complete, paste-ready Moodscape podcast script. Each guide is fully self-contained:
copy one whole file into the LLM, fill in the inputs block at the top, and it will
return a script you can paste straight into the app's **Script** box.

## Which guide do I use?

Pick by the **TTS model you'll assign to your speakers** in the app's Speaker panel:

| Your model | Use this guide | Why it differs |
| --- | --- | --- |
| **ElevenLabs** (cloud) | [`elevenlabs.md`](elevenlabs.md) | Most expressive; tone tags map to real voice-setting changes. Handles long, complex sentences. Pick **v2** (best normalization) or **v3** (performs inline audio tags like `[laughs]`) per speaker. |
| **Kokoro** (local, built-in voices) | [`kokoro.md`](kokoro.md) | Fixed-character voices; tone only nudges speaking rate. Prefers shorter sentences. |
| **F5** (local, voice cloning) | [`f5.md`](f5.md) | Voice cloned from a reference clip; tone nudges rate; emotion is anchored to the reference. Shortest sentence budget. |

### Mixing models across speakers

The app lets each speaker use a different model. If your podcast mixes models
(e.g. Speaker 1 = ElevenLabs, Speaker 2 = Kokoro), follow the **most constrained**
guide for the whole script — that's [`kokoro.md`](kokoro.md) or [`f5.md`](f5.md)
(use F5's guide if any speaker is F5). Conservative phrasing always renders well on
the more expressive models too.

## What every guide already knows (shared format)

All three guides produce the **same script format** — they only differ in style
advice and which tags do something audible. The format the app parses:

- Each turn starts with `[Speaker N]:` at the **start of a line**. Labels must be
  exactly `Speaker 1`, `Speaker 2`, … up to `Speaker 6` (they must match the
  speakers you set up in the UI, or the app refuses to generate).
- One turn per block; a turn may wrap across multiple lines until the next
  `[Speaker N]:` marker.
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
    [`elevenlabs.md`](elevenlabs.md) for the v3 audio-tag note.
- The app's **Natural pacing** toggle (on by default) already adds sentence
  micro-pauses, slight speed variation, and varied gaps between turns — so the
  scripts don't need to over-punctuate to sound human.

> **Scope:** Moodscape podcasts are *mindfulness-themed conversations*, not guided
> meditations. The guides aim for warm, natural dialogue — not slow, breathy
> meditation reads.

## How to use a guide

1. Open the guide for your model and copy the **entire file**.
2. Paste it into your LLM.
3. Replace the `INPUTS` block at the top (topic, number of speakers, length, who
   the speakers are, desired tone).
4. Send. The LLM returns only the script.
5. Paste the script into the app, assign each `Speaker N` the matching model +
   voice, and generate.
