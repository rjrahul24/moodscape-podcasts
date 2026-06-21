"""Application configuration, loaded from environment / `.env`.

Everything tunable about the app lives here so that the rest of the code can
depend on a single, typed ``Settings`` object instead of reading the
environment directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root "assets/" directory: app/config.py -> app -> backend -> repo root.
_DEFAULT_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


class VoiceCatalogEntry(BaseModel):
    """A voice offered in the UI dropdown.

    ``label`` is optional — when omitted the name is resolved from the
    provider's API (falling back to the id).
    """

    id: str
    label: str | None = None
    provider: str = "elevenlabs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ElevenLabs. ``elevenlabs_model_id`` is the global fallback; the per-content
    # defaults below are used when a request doesn't pin a model. The UI can
    # override per speaker / per sleep story (v2 vs v3). v3 is the default — it
    # performs inline audio tags ([warmly], [exhales softly], …) for expressive
    # podcasts and calm sleep narration; v2 remains selectable as a stable
    # fallback. v3 caps requests at 5k chars (under elevenlabs_chunk_chars, fine).
    elevenlabs_api_key: str | None = None
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_podcast_model: str = "eleven_v3"
    elevenlabs_sleep_model: str = "eleven_v3"
    # Pull the voice "closer" (intimate proximity) — research sweet spot for both
    # expressive dialogue and bedtime narration. Sent on every EL request.
    elevenlabs_use_speaker_boost: bool = True
    # Server-side text normalization ("auto"|"on"|"off"): spells numbers/symbols
    # so the model never reads digits in a clipped, transactional tone.
    elevenlabs_text_normalization: str = "auto"
    # v3 sleep stability (discrete: 0.0 Creative / 0.5 Natural / 1.0 Robust).
    # Natural (0.5) keeps the inline calming tags ([calm], [warmly]) *responsive*
    # while staying steady — Robust (1.0) is more consistent but largely ignores
    # the tags, defeating the reason to run v3 for an expressive-but-calm read.
    elevenlabs_sleep_v3_stability: float = 0.5
    # Optional v3 sleep pacing tag, *reasserted on every chunk*. v3 tends to drift
    # from a calm bedtime register toward an "audiobook narrator" read over a long
    # story; prepending a pacing tag (e.g. "[slowly]") to each chunk holds the slow
    # register to the end. Empty string = disabled (today's behaviour); applies
    # only to sleep + v3, landing after the emotion tag (e.g. "[calm][slowly] …").
    elevenlabs_sleep_v3_pacing_tag: str = ""
    # On v2, translate author-placed [pause:N] markers into native <break time>
    # tags so ElevenLabs renders the breath with model-aware prosody (smoother
    # than a spliced silence). v3 has no break tags, so it always splices.
    elevenlabs_v2_native_breaks: bool = True
    # Per-provider intermediate format. Chunks are decoded then re-encoded for the
    # final master, so a higher-quality intermediate reduces loss *before*
    # mastering. ElevenLabs gates formats by plan tier:
    #   • mp3_44100_192 — Creator tier and up; the default (best non-PCM option).
    #   • pcm_44100      — lossless, but **Pro tier and up only** (the API rejects
    #                      it on lower tiers). On Pro, set this for a truly lossless
    #                      intermediate (matches sleep_sample_rate, no resample);
    #                      bytes_to_segment already decodes raw pcm_*.
    elevenlabs_segment_format: str = "mp3_44100_192"

    # Providers
    default_provider: str = "elevenlabs"

    # Audio
    segment_output_format: str = "mp3_44100_128"
    final_format: str = "m4a"
    also_export_wav: bool = True
    inter_turn_gap_ms: int = 400
    output_dir: str = "output"

    # Podcast conversational pacing (sanctioned exception to "no podcast
    # processing": pacing + voice-emotion only — never loudness/EQ/compression/
    # fades/ambient, which stay sleep-only). On by default; per-job overridable
    # via PodcastRequest.pacing.
    podcast_default_speed: float = 1.0
    podcast_speed_jitter: float = 0.03  # ±fraction of per-chunk speed (local providers)
    podcast_intra_sentence_gap_ms_min: int = 80  # randomized micro-pause between sentences
    podcast_intra_sentence_gap_ms_max: int = 220
    podcast_turn_gap_jitter: float = 0.4  # ±fraction applied to inter_turn_gap_ms
    # All segments are normalized to this rate before stitching, so providers
    # with different native rates (ElevenLabs 44.1kHz, local models 24kHz) mix.
    target_sample_rate: int = 44100
    # Short equal-power fade applied to each chunk WAV's edges before the concat
    # demuxer joins them — removes zero-crossing click artifacts at boundaries
    # without overlapping audio (the memory-safe stand-in for a crossfade). 0 = off.
    chunk_edge_fade_ms: int = 8

    # Local models — reference voice assets (F5)
    assets_dir: Path = _DEFAULT_ASSETS_DIR
    # Uploaded reference clips are cleaned (mono, resample, silence-trim, optional
    # denoise) before they enter the registry. Cloners need only a short window.
    reference_clip_sample_rate: int = 24000
    reference_clip_max_seconds: float = 30.0

    # Kokoro
    kokoro_speed: float = 1.0
    # Kokoro ignores punctuation for pausing — the app converts commas, ellipses,
    # semicolons, and dashes to explicit [pause:N] markers (sleep stories only).
    kokoro_pause_comma_ms: int = 80
    kokoro_pause_ellipsis_ms: int = 350
    kokoro_pause_semicolon_ms: int = 200
    kokoro_pause_dash_ms: int = 250
    kokoro_pause_paragraph_ms: int = 400

    # F5. ``f5_device="auto"`` resolves to CUDA > MPS > CPU. On Apple Silicon
    # this lands on MPS (~1.6x faster than CPU here); float16 is auto-selected
    # for MPS at model-load time (~8% on top), explicit ``f5_dtype="float32"``
    # overrides. The dominant cost is ``nfe_step`` — F5 runtime scales ~linearly
    # with it (measured MPS+fp16: nfe=32 → RTF 5.3, nfe=16 → 2.4, nfe=12 → 1.8).
    # With sway sampling, 16 is the quality/speed sweet spot (the reference
    # meditation project uses 16 as its working default, 32 only for final).
    f5_speed: float = 1.0
    f5_device: str = "auto"  # auto | cpu | mps | cuda
    f5_dtype: str = "float32"  # float32 | float16
    f5_nfe_step: int = 16
    f5_cfg_strength: float = 2.0
    f5_sway_coef: float = -1.0
    # F5 recomputes the *reference + generated* sequence on every chunk, so the
    # reference clip length is a direct, per-chunk runtime multiplier. Clipping
    # to ~8s (F5 needs only a few seconds to clone a voice) cuts ~30-40% off each
    # chunk vs the ~12s F5 preprocess default, with no audible clone-fidelity
    # loss. Applied in _condition_reference_audio before the anti-leak pad.
    f5_ref_clip_seconds: float = 8.0
    # F5 sleep story override. nfe=16 (was 32) keeps sway-sampled quality while
    # roughly halving render time; combined with the 8s reference clip a 10-min
    # story renders in ~14 min (RTF ~1.4) instead of ~53 min (RTF ~5.3). Speed
    # starts at a calm meditation pace (~95-100 WPM) before the ramp eases it.
    f5_sleep_nfe_step: int = 16
    f5_sleep_speed: float = 0.88

    # Per-provider chunk budgets (characters). Long text is split into bounded
    # chunks before synthesis so Kokoro stays under its 510 phoneme-token cap and
    # F5 stays within ~30s/pass. See core/chunker.py for the char-vs-token note.
    kokoro_chunk_chars: int = 400
    f5_chunk_chars: int = 250  # ~18s/pass: well under F5's ~30s garble edge
    elevenlabs_chunk_chars: int = 1000

    # Sleep stories (single-speaker, calming treatment — NOT applied to podcasts).
    # Base pace sits low (ElevenLabs honours 0.7–1.2; 0.7 is the slowest). Sleep
    # wants an unhurried read, so the default leans toward that floor and the
    # ramp eases it further. The UI Speed slider overrides per story.
    sleep_default_speed: float = 0.78
    sleep_default_pause_ms: int = 1050  # inter-sentence silence
    # Default delivery tone injected for ElevenLabs sleep chunks that don't open
    # with an author-placed tag, so even untagged prose lands in a calm register
    # (v3 prepends the mapped inline tag; v2 uses the matching numeric profile).
    # Empty string disables the injection.
    sleep_default_tone: str = "soothing"
    # Author-placed [pause:N] breaths are clamped to this ceiling (ms) on every
    # engine (the v2 native <break> tag is additionally clamped to 3 s by the API).
    sleep_pause_marker_max_ms: int = 5000
    # Default duration for a bare [pause] tag with no explicit ms value.
    sleep_pause_default_ms: int = 1000
    # Per-chunk loudness normalization *before* stitching. v3 drifts in loudness
    # between chunks under any settings; a single end-of-pipeline loudnorm can't
    # undo level jumps baked into the stitched track. Normalizing each chunk to a
    # common target first evens the drift out; the final master (sleep_target_lufs)
    # then sets the absolute level. Target sits above the master so the master
    # loudnorm doesn't fight it. Chunks shorter than the guard are skipped so
    # near-silent fragments aren't amplified.
    sleep_chunk_normalize: bool = True
    sleep_chunk_norm_lufs: float = -21.0
    sleep_chunk_norm_min_ms: int = 400
    # Inject an ellipsis ("…") at sentence boundaries that lack one, giving the
    # narrator a soft breathing pause at each break. Off by default (today's
    # behaviour); applies only to ElevenLabs sleep (both v2 and v3 honour "…").
    sleep_sentence_ellipsis: bool = False
    sleep_sample_rate: int = 44100
    sleep_channels: int = 2  # sleep masters are stereo
    sleep_target_lufs: float = -18.0  # EBU R128 integrated loudness target (calm but audible)
    sleep_true_peak_db: float = -2.0  # loudnorm true-peak ceiling (research: -2 to -3 dBTP)
    sleep_lowpass_hz: int = 8000  # gentle high-frequency roll-off
    sleep_fade_in_s: float = 2.0
    sleep_fade_out_s: float = 5.0
    # Seconds of ambient-bed-only playback before the narration starts. Gives
    # listeners a gentle entry instead of an abrupt first word. Only applies
    # when an ambient bed is selected; 0 = disabled.
    sleep_preroll_s: float = 3.0
    # Progressive "ramp-down": the story gently decelerates toward sleep onset.
    # Per-chunk speed eases from the baseline to baseline*end_factor, and the
    # inter-sentence pause grows up to pause_scale×, both interpolated over the
    # story. Gated per request by SleepStoryRequest.ramp (default on).
    sleep_ramp_speed_end_factor: float = 0.94  # ~6% slower by the final chunk
    sleep_ramp_pause_scale: float = 1.6  # final pauses ~60% longer than the first
    # Ambient bed ("light and slow" music under the narration). The bed is
    # band-limited so it sits softly *behind* the voice, looped with a crossfaded
    # seam (no click), pulled well under the voice, and — when ducking is on —
    # gently dips while the narrator speaks and breathes back up in the gaps.
    ambient_bed_target_lufs: float = -24.0  # normalize bed loudness before gain
    ambient_bed_gain_db: float = -18.0  # under the voice but audibly present
    ambient_bed_lowpass_hz: int = 3000  # dark, unobtrusive top end
    ambient_bed_highpass_hz: int = 90  # clear low mud that would fight the voice
    ambient_loop_crossfade_s: float = 2.0  # seam crossfade when looping the bed
    ambient_duck: bool = True  # sidechain-duck the bed under the voice
    # Gentle duck: sleep narration is near-continuous, so a hard duck would keep
    # the bed inaudible the whole story. A low ratio just nudges it under speech.
    ambient_duck_ratio: float = 2.0  # gentle compression ratio for the duck
    ambient_duck_threshold_db: float = -28.0  # voice level that triggers the duck
    ambient_duck_release_ms: int = 600  # how slowly the bed recovers after speech
    ambient_dir: Path = _DEFAULT_ASSETS_DIR / "ambient"
    series_dir: Path = _DEFAULT_ASSETS_DIR / "series"
    podcast_music_dir: Path = _DEFAULT_ASSETS_DIR / "podcast_music"

    # Long-form quality control (opt-in post-step; deps via `uv sync --extra qc`).
    # Off by default — it transcribes the whole master and embeds windows, so it
    # roughly doubles a job's wall-clock. Turn on to catch hallucinated/dropped
    # words (WER) and cloned-voice drift (SIM) over a 30–90 min render.
    enable_qc: bool = False
    qc_whisper_mlx_repo: str = "mlx-community/whisper-base-mlx"  # Apple Silicon ASR
    qc_whisper_faster_size: str = "base"  # faster-whisper CPU fallback size
    qc_sim_threshold: float = 0.75  # flag windows below this cosine similarity

    # Voice catalog (empty -> offer all account voices)
    voice_catalog: list[VoiceCatalogEntry] = Field(default_factory=list)

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
