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

    # ElevenLabs
    elevenlabs_api_key: str | None = None
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    # Providers
    default_provider: str = "elevenlabs"

    # Audio
    segment_output_format: str = "mp3_44100_128"
    final_format: str = "wav"
    also_export_mp3: bool = True
    inter_turn_gap_ms: int = 400
    output_dir: str = "output"
    # All segments are normalized to this rate before stitching, so providers
    # with different native rates (ElevenLabs 44.1kHz, local models 24kHz) mix.
    target_sample_rate: int = 44100

    # Local models — reference voice assets (F5)
    assets_dir: Path = _DEFAULT_ASSETS_DIR

    # Kokoro
    kokoro_speed: float = 1.0

    # F5
    f5_speed: float = 1.0
    f5_nfe_step: int = 32
    f5_cfg_strength: float = 2.0
    f5_sway_coef: float = -1.0

    # Per-provider chunk budgets (characters). Long text is split into bounded
    # chunks before synthesis so Kokoro stays under its 510 phoneme-token cap and
    # F5 stays within ~30s/pass. See core/chunker.py for the char-vs-token note.
    kokoro_chunk_chars: int = 400
    f5_chunk_chars: int = 350
    elevenlabs_chunk_chars: int = 2400

    # Sleep stories (single-speaker, calming treatment — NOT applied to podcasts).
    sleep_default_speed: float = 0.85
    sleep_default_pause_ms: int = 900  # inter-sentence silence
    sleep_sample_rate: int = 44100
    sleep_channels: int = 2  # sleep masters are stereo
    sleep_target_lufs: float = -20.0  # EBU R128 integrated loudness target
    sleep_lowpass_hz: int = 8000  # gentle high-frequency roll-off
    sleep_fade_in_s: float = 2.0
    sleep_fade_out_s: float = 5.0
    ambient_bed_gain_db: float = -22.0  # how far under the narration the bed sits
    ambient_dir: Path = _DEFAULT_ASSETS_DIR / "ambient"

    # Voice catalog (empty -> offer all account voices)
    voice_catalog: list[VoiceCatalogEntry] = Field(default_factory=list)

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
