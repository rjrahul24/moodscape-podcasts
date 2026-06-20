# Podcast Branding: Series Config, Intro/Outro Music & Prompting Guide Split

**Date:** 2026-06-19
**Status:** Design

## Context

Moodscape's ElevenLabs podcast generation produces high-quality conversational
audio, but episodes lack branding consistency. Real podcasts have signature
intros, outros, and music stings that make the show recognizable. Additionally,
the single `elevenlabs.md` prompting guide covers only podcast scripts and
doesn't distinguish between podcast and sleep story content — sleep stories have
no dedicated LLM prompting guide at all.

This design addresses three needs:
1. Split and enhance the ElevenLabs prompting guide (podcast vs sleep story)
2. Add a series/brand system with consistent intro/outro across episodes
3. Mix subtle signature music under intro and outro sections only

## 1. Prompting Guide Split

### Current state

One guide: `docs/prompting_guides/elevenlabs.md` — covers podcast scripts, no
sleep story guide exists.

### New structure

| File | Content type | Purpose |
| --- | --- | --- |
| `elevenlabs_podcast.md` | Podcast | Highly tuned podcast script guide with intro/outro structure, section markers, emotional arc, v3 tag best practices, series-aware INPUTS |
| `elevenlabs_sleep.md` | Sleep Story | Single-narrator prose guide: calming rhythm, number spelling, tone tag use for sleep, ambient bed awareness |
| `README.md` | Both | Updated routing table: by content type + model |

The old `elevenlabs.md` is deleted (replaced by the two new files).

### Podcast guide enhancements

**INPUTS block additions** (beyond existing topic/speakers/length/tone):
- `SERIES_NAME`: e.g. "The Shared Space" (used in intro/outro)
- `SPEAKER_NAMES`: e.g. "Maya and Kai" (persona names for introductions)
- `INTRO_STYLE`: brief guidance on the intro feel (default: "warm, brief, branded")

**New sections in the guide:**
- **Section markers**: Instruct the LLM to use `[INTRO]`, `[BODY]`, `[OUTRO]`
  line-level markers to delimit sections
- **Intro structure guidance**: Welcome line with series name, both speakers
  introduce themselves by persona name, brief topic tease — consistent across
  episodes, only the topic changes
- **Outro structure guidance**: Soft takeaway or reflection, sign-off with series
  name, "until next time" — warm and consistent
- **Emotional arc**: Build energy through the body, tone tags should follow a
  natural conversation arc (curious opening → engaged middle → reflective close)
- **v3 inline tag best practices**: Curated list of tags that work well
  (`[laughs]`, `[soft laugh]`, `[sighs]`, `[exhales softly]`, `[warmly]`);
  guidance to keep them rare (~2-4 per episode) and genuine
- **Pause calibration**: 200-400ms for quick beats (comma-like), 400-600ms for
  emphasis, 600-800ms for topic shifts or dramatic beats
- **Updated worked example**: Full intro → body → outro with section markers

### Sleep story guide (new)

- Prose format (no `[Speaker N]:` markers)
- Tone: unhurried, gentle, lulling — not dramatic, not instructive
- Sentence rhythm: vary length, favor medium sentences (12-20 words), occasional
  short sentence for pacing contrast
- Spell out numbers (the system does this automatically, but guiding the LLM
  avoids edge cases)
- Tone tags for sleep: prefer `[soothing]`, `[calm]`, `[warm]`; avoid
  `[excited]`, `[whispering]` (whispering can sound jarring at sleep volumes)
- Note that the system adds ambient soundscapes separately — prose should not
  describe background sounds
- Worked example of good sleep prose (~1 minute)

## 2. Series Configuration System

### Concept

A **series** is a branded podcast show with consistent identity across episodes:
fixed show name, speaker personas, and music assets.

### Storage

Series configs live as JSON files in `assets/series/<slug>.json`:

```json
{
  "name": "The Shared Space",
  "slug": "the-shared-space",
  "speakers": {
    "Speaker 1": "Maya",
    "Speaker 2": "Kai"
  },
  "intro_music": "shared-space-theme.mp3",
  "outro_music": "shared-space-theme.mp3",
  "music_gain_db": -18,
  "music_fade_s": 2.0
}
```

Fields:
- `name` — display name of the series
- `slug` — filesystem-safe identifier (matches filename stem)
- `speakers` — maps script labels (`Speaker 1`) to persona names (informational,
  not used by synthesis — names appear in the script text itself)
- `intro_music` / `outro_music` — filenames from `assets/podcast_music/`
- `music_gain_db` — how much to pull music under speech (default -18 dB)
- `music_fade_s` — fade in/out duration for music (default 2.0s)

### Registry

`backend/app/storage/series_registry.py` — scans `assets/series/` for `.json`
files, validates and returns `{slug: SeriesConfig}`. Same pattern as
`ambient_registry.py`.

### Music assets

`assets/podcast_music/` — directory for intro/outro music files (`.mp3`,
`.wav`). Parallel to `assets/ambient/`. User adds their own music files here.

### Models

```python
class SeriesConfig(BaseModel):
    name: str
    slug: str
    speakers: dict[str, str]  # "Speaker 1" -> "Maya"
    intro_music: str
    outro_music: str
    music_gain_db: float = -18.0
    music_fade_s: float = 2.0

class SeriesInfo(BaseModel):
    """Surfaced to the frontend via GET /api/series."""
    id: str   # slug
    name: str
```

### API

`GET /api/series` — returns `list[SeriesInfo]` (id + name for dropdown).

### Request change

`PodcastRequest` gets:
```python
series: str | None = None  # series slug; None = no branding/music
```

When set, the orchestrator loads the series config for music mixing. When unset,
behavior is identical to today (no music, no section handling — backward
compatible).

## 3. Script Section Markers

### Format

Three line-level markers recognized by the parser:

```
[INTRO]
[Speaker 1]: Welcome to The Shared Space. I'm Maya.
[Speaker 2]: And I'm Kai. Today we're exploring...

[BODY]
[Speaker 1]: So here's what got me thinking...
...main discussion...

[OUTRO]
[Speaker 1]: [warm] That wraps us up for today.
[Speaker 2]: Thanks for spending time in The Shared Space.
```

### Parser changes

`ScriptTurn` gets a new field:
```python
section: Literal["intro", "body", "outro"] = "body"
```

`parse_script()` changes:
- Recognize `[INTRO]`, `[BODY]`, `[OUTRO]` as standalone line markers (no colon,
  not speaker tags). Regex: `^\s*\[(INTRO|BODY|OUTRO)\]\s*$` (case-insensitive)
- Track current section state; annotate each `ScriptTurn` with its section
- Section markers are consumed (not emitted as turns)
- **Backward compatibility**: if no section markers appear, all turns default to
  `"body"` — existing scripts work unchanged, no music mixing occurs

### Section marker rules

- Markers are optional. A script with no markers is 100% body.
- `[INTRO]` must come before `[BODY]` if both are present.
- `[OUTRO]` must come after `[BODY]` (or after all non-outro turns).
- A script may have intro + body, body + outro, or all three.
- The parser raises `ScriptParseError` if markers appear out of order.

## 4. Orchestrator: Section-Aware Rendering

### Render flow (when `series` is set and section markers are present)

```
1. Parse script → section-annotated turns
2. Load series config
3. Validate intro/outro music files exist
4. Group turns by section: intro_turns, body_turns, outro_turns
5. Render each section:
   a. Intro: synthesize turns → stitch → mix intro_music under → intro_mixed.wav
   b. Body:  synthesize turns → stitch → body.wav (purely vocal, no music)
   c. Outro: synthesize turns → stitch → mix outro_music under → outro_mixed.wav
6. Concatenate: intro_mixed + body + outro_mixed → master.wav
7. Finalize (transcode, export MP3)
```

### Music mixing module

`backend/app/core/podcast_music.py` — thin wrapper around the ffmpeg filter
chain already proven in `ambient.mix()`:

```python
def mix_music(
    speech_wav: Path,
    music_path: Path,
    out_wav: Path,
    *,
    speech_ms: int,
    gain_db: float = -18.0,
    fade_s: float = 2.0,
    sample_rate: int = 44100,
) -> Path:
    """Mix music under a speech segment (intro or outro)."""
```

Same approach: loop music, trim to speech length, gain-reduce, fade in/out,
amix. The function is intentionally separate from `ambient.py` to keep the
podcast/sleep boundary clean (ambient is sleep-only).

### Fallback behavior

- If `series` is None: no section handling, no music — identical to today
- If `series` is set but script has no section markers: render as all-body, no
  music (warn in logs)
- If `series` is set and script has sections but music file is missing: raise
  error early (fail-fast, before synthesis)

## 5. Frontend Changes

### Series selector

Add a series dropdown to `SpeakerConfig.tsx` (or a new `SeriesConfig` component
next to it):
- Fetches from `GET /api/series` on mount
- Options: "None" (default, no branding) + available series
- Selected series slug is sent in the `PodcastJobRequest`

### Type updates

```typescript
interface PodcastJobRequest {
  kind: "podcast"
  script_text: string
  speakers: Record<string, SpeakerVoice>
  pacing?: boolean
  seed?: number
  series?: string  // new: series slug
}

interface SeriesInfo {
  id: string
  name: string
}
```

### API client

Add `fetchSeries()` function in `api.ts` to call `GET /api/series`.

## 6. File inventory

### Create
- `docs/prompting_guides/elevenlabs_podcast.md`
- `docs/prompting_guides/elevenlabs_sleep.md`
- `backend/app/storage/series_registry.py`
- `backend/app/core/podcast_music.py`
- `backend/app/api/routes/series.py`
- `assets/series/the-shared-space.json`
- `assets/podcast_music/.gitkeep`

### Modify
- `docs/prompting_guides/README.md` — updated routing table
- `backend/app/core/script_parser.py` — section marker recognition
- `backend/app/core/models.py` — ScriptTurn.section, PodcastRequest.series,
  SeriesConfig, SeriesInfo
- `backend/app/core/orchestrator.py` — section-aware rendering + music mixing
- `backend/app/api/routes/__init__.py` — register series router
- `backend/app/main.py` — mount series route (if not auto-registered)
- `frontend/src/types.ts` — PodcastJobRequest.series, SeriesInfo
- `frontend/src/api.ts` — fetchSeries()
- `frontend/src/components/App.tsx` — series state + fetch
- `frontend/src/components/SpeakerConfig.tsx` — series selector dropdown
- `docs/ARCHITECTURE.md` — series system, section markers, music mixing
- `docs/CHANGELOG.md` — dated entry

### Delete
- `docs/prompting_guides/elevenlabs.md` (replaced by split guides)

## 7. Verification

1. **Prompting guides**: Copy the new `elevenlabs_podcast.md` into an LLM with
   test inputs for "The Shared Space". Verify the output script uses `[INTRO]`,
   `[BODY]`, `[OUTRO]` markers correctly and includes a branded intro/outro.
2. **Parser**: Run existing tests + new tests for section marker parsing,
   backward compatibility (no markers = all body), out-of-order marker rejection.
3. **Series registry**: Test scanning `assets/series/`, missing file handling.
4. **Music mixing**: Generate a short podcast with series set. Verify:
   - Intro and outro have music underneath
   - Body is purely vocal (no music)
   - Music fades in/out cleanly
   - Full episode plays seamlessly (no clicks or gaps at section boundaries)
5. **Backward compatibility**: Generate a podcast with no series set and no
   section markers. Verify identical output to current behavior.
6. **Frontend**: Series dropdown appears, selection persists, request includes
   series slug.
7. **Sleep guide**: Copy `elevenlabs_sleep.md` into an LLM, verify it produces
   well-structured sleep prose.
