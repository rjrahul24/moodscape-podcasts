"""Application configuration, loaded from environment / `.env`.

Everything tunable about the app lives here so that the rest of the code can
depend on a single, typed ``Settings`` object instead of reading the
environment directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Voice catalog (empty -> offer all account voices)
    voice_catalog: list[VoiceCatalogEntry] = Field(default_factory=list)

    # CORS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
