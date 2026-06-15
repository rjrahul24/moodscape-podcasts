"""Kokoro provider tests.

``list_voices`` must work with no ML libraries installed. ``synthesize`` is
exercised against a fake ``kokoro`` module injected into ``sys.modules`` so no
real model download happens.
"""

import sys
import types

import numpy as np
import pytest
from pydub import AudioSegment

from app.providers.kokoro_provider import VOICES, KokoroProvider


def test_list_voices_is_static_and_dependency_free():
    provider = KokoroProvider()
    voices = provider.list_voices()
    assert {v.id for v in voices} == set(VOICES)
    assert all(v.provider == "kokoro" for v in voices)


@pytest.fixture
def fake_kokoro(monkeypatch):
    """Inject a fake `kokoro` module whose pipeline yields 0.5 s of audio."""

    class FakeKPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.last_speed = None

        def __call__(self, text, voice, speed, split_pattern):
            self.last_speed = speed
            sr = 24000
            audio = np.zeros(int(sr * 0.5), dtype=np.float32)
            yield ("graphemes", "phonemes", audio)

    module = types.ModuleType("kokoro")
    module.KPipeline = FakeKPipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)
    return FakeKPipeline


def test_synthesize_returns_24k_segment(fake_kokoro):
    provider = KokoroProvider(speed=1.0)
    seg = provider.synthesize("hello world", "af_heart", output_format="ignored")
    assert isinstance(seg, AudioSegment)
    assert seg.frame_rate == 24000
    assert abs(len(seg) - 500) < 30


def test_british_voice_uses_lang_code_b(fake_kokoro):
    provider = KokoroProvider()
    provider.synthesize("cheerio", "bf_emma", output_format="ignored")
    assert provider._pipeline_gb is not None
    assert provider._pipeline_gb.kwargs["lang_code"] == "b"
    assert provider._pipeline_us is None


def test_default_speed_used_when_no_voice_settings(fake_kokoro):
    provider = KokoroProvider(speed=1.0)
    provider.synthesize("hi", "af_heart", output_format="ignored")
    assert provider._pipeline_us.last_speed == 1.0


def test_voice_settings_speed_overrides_default(fake_kokoro):
    provider = KokoroProvider(speed=1.0)
    provider.synthesize(
        "hi", "af_heart", output_format="ignored", voice_settings={"speed": 0.85}
    )
    assert provider._pipeline_us.last_speed == 0.85
