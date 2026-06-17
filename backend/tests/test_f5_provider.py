"""F5 provider tests.

``list_voices`` only scans the filesystem. ``synthesize`` runs against fake
``f5_tts`` and ``torch`` modules injected into ``sys.modules`` — no model
download, no real inference.
"""

import sys
import types

import numpy as np
import pytest
from pydub import AudioSegment

from app.providers.f5_provider import F5Provider


def _make_voice(assets_dir, slug, text="the exact words spoken"):
    audio_dir = assets_dir / "speakers" / "reference_audio"
    text_dir = assets_dir / "speakers" / "reference_text"
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{slug}.wav").write_bytes(b"RIFFfake")
    (text_dir / f"{slug}.txt").write_text(text, encoding="utf-8")


def test_list_voices_from_assets(tmp_path):
    _make_voice(tmp_path, "calm_brittney")
    provider = F5Provider(assets_dir=tmp_path)
    voices = provider.list_voices()
    assert [(v.id, v.name, v.provider) for v in voices] == [
        ("calm_brittney", "Calm Brittney", "f5")
    ]


@pytest.fixture
def fake_f5(monkeypatch):
    """Inject fake torch + f5_tts modules. Returns the captured infer kwargs."""
    captured: dict = {}

    # torch
    import contextlib

    torch_mod = types.ModuleType("torch")
    backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False)
    )
    torch_mod.backends = backends
    torch_mod.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch_mod.float16 = "float16"
    torch_mod.set_num_threads = lambda n: None
    torch_mod.inference_mode = lambda: contextlib.nullcontext()
    monkeypatch.setitem(sys.modules, "torch", torch_mod)

    # f5_tts.api.F5TTS
    class FakeF5TTS:
        def __init__(self, model, device):
            self.model = model
            self.device = device
            self.ema_model = types.SimpleNamespace(to=lambda *a, **k: None)

        def infer(self, **kwargs):
            captured.update(kwargs)
            return np.zeros(int(24000 * 0.5), dtype=np.float32), 24000, None

    f5_pkg = types.ModuleType("f5_tts")
    api_mod = types.ModuleType("f5_tts.api")
    api_mod.F5TTS = FakeF5TTS
    infer_pkg = types.ModuleType("f5_tts.infer")
    utils_mod = types.ModuleType("f5_tts.infer.utils_infer")
    utils_mod.preprocess_ref_audio_text = lambda audio, text, **k: (audio, text)

    monkeypatch.setitem(sys.modules, "f5_tts", f5_pkg)
    monkeypatch.setitem(sys.modules, "f5_tts.api", api_mod)
    monkeypatch.setitem(sys.modules, "f5_tts.infer", infer_pkg)
    monkeypatch.setitem(sys.modules, "f5_tts.infer.utils_infer", utils_mod)
    return captured


def test_synthesize_returns_segment_and_passes_reference(tmp_path, fake_f5):
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, nfe_step=16, cfg_strength=1.5)

    seg = provider.synthesize("hello there", "brittney", output_format="ignored")

    assert isinstance(seg, AudioSegment)
    assert seg.frame_rate == 24000
    assert abs(len(seg) - 500) < 30
    # Reference + generation text + tuned params reached model.infer
    assert fake_f5["ref_text"] == "reference transcript"
    assert fake_f5["gen_text"] == "hello there"
    assert fake_f5["nfe_step"] == 16
    assert fake_f5["cfg_strength"] == 1.5


def test_unknown_voice_raises_provider_error(tmp_path, fake_f5):
    from app.core.errors import ProviderError

    provider = F5Provider(assets_dir=tmp_path)
    with pytest.raises(ProviderError):
        provider.synthesize("hi", "nonexistent", output_format="ignored")
