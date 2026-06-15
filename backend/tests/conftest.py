import pytest
from pydub import AudioSegment

from app.core.models import Voice
from app.providers import registry
from app.providers.base import TTSProvider


class FakeProvider(TTSProvider):
    """A network-free provider that returns fixed-length silent audio."""

    def __init__(self, name: str = "fake", duration_ms: int = 300, sample_rate: int = 24000):
        self.name = name
        self._duration_ms = duration_ms
        self._sample_rate = sample_rate
        self.calls: list[tuple[str, str]] = []

    def list_voices(self) -> list[Voice]:
        return [Voice(id=f"{self.name}-v1", name="Fake Voice", provider=self.name)]

    def synthesize(self, text, voice_id, *, output_format, voice_settings=None) -> AudioSegment:
        self.calls.append((voice_id, text))
        return AudioSegment.silent(
            duration=self._duration_ms, frame_rate=self._sample_rate
        )


@pytest.fixture
def clean_registry():
    registry.clear()
    yield registry
    registry.clear()
