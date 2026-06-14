from io import BytesIO

import pytest
from pydub import AudioSegment

from app.core.models import Voice
from app.providers import registry
from app.providers.base import TTSProvider


class FakeProvider(TTSProvider):
    """A network-free provider that returns fixed-length silent WAV audio."""

    def __init__(self, name: str = "fake", duration_ms: int = 300):
        self.name = name
        self._duration_ms = duration_ms
        self.calls: list[tuple[str, str]] = []

    def list_voices(self) -> list[Voice]:
        return [Voice(id=f"{self.name}-v1", name="Fake Voice", provider=self.name)]

    def synthesize(self, text, voice_id, *, output_format, voice_settings=None) -> bytes:
        self.calls.append((voice_id, text))
        buffer = BytesIO()
        AudioSegment.silent(duration=self._duration_ms).export(buffer, format="wav")
        return buffer.getvalue()


@pytest.fixture
def clean_registry():
    registry.clear()
    yield registry
    registry.clear()
