import pytest
from pydub import AudioSegment

from app.core.models import Voice
from app.providers import registry
from app.providers.base import TTSProvider


class FakeProvider(TTSProvider):
    """A network-free provider that returns fixed-length silent audio."""

    def __init__(
        self,
        name: str = "fake",
        duration_ms: int = 300,
        sample_rate: int = 24000,
        *,
        consumes_local_speed: bool = False,
        has_native_speed: bool = False,
    ):
        self.name = name
        self.consumes_local_speed = consumes_local_speed
        self.has_native_speed = has_native_speed
        self._duration_ms = duration_ms
        self._sample_rate = sample_rate
        self.calls: list[tuple[str, str]] = []
        # Full call records including voice_settings (for per-job speed assertions).
        self.synth_calls: list[dict] = []

    def list_voices(self) -> list[Voice]:
        return [Voice(id=f"{self.name}-v1", name="Fake Voice", provider=self.name)]

    def synthesize(self, text, voice_id, *, output_format, voice_settings=None) -> AudioSegment:
        self.calls.append((voice_id, text))
        self.synth_calls.append(
            {
                "text": text,
                "voice_id": voice_id,
                "output_format": output_format,
                "voice_settings": voice_settings,
            }
        )
        return AudioSegment.silent(
            duration=self._duration_ms, frame_rate=self._sample_rate
        )


@pytest.fixture
def clean_registry():
    registry.clear()
    yield registry
    registry.clear()
