"""CosyVoice3 provider tests.

``list_voices`` only scans the filesystem (no ``mlx_audio`` import). ``synthesize``
runs against a fake ``mlx_audio`` injected into ``sys.modules`` — no model
download, no real inference, runnable on any platform.
"""

import sys
import types
from pathlib import Path

import pytest
from pydub import AudioSegment

from app.providers.cosyvoice_provider import CosyVoiceProvider


def _make_voice(assets_dir, slug, text="the exact words spoken"):
    audio_dir = assets_dir / "speakers" / "reference_audio"
    text_dir = assets_dir / "speakers" / "reference_text"
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{slug}.wav").write_bytes(b"RIFFfake")
    (text_dir / f"{slug}.txt").write_text(text, encoding="utf-8")


def test_list_voices_from_assets(tmp_path):
    _make_voice(tmp_path, "calm_brittney")
    provider = CosyVoiceProvider(assets_dir=tmp_path, model="m")
    voices = provider.list_voices()
    assert [(v.id, v.name, v.provider) for v in voices] == [
        ("calm_brittney", "Calm Brittney", "cosyvoice")
    ]


@pytest.fixture
def fake_mlx(monkeypatch):
    """Inject a fake mlx_audio. Returns the captured generate_audio kwargs."""
    captured: dict = {}

    def generate_audio(**kwargs):
        captured.update(kwargs)
        # Real generate_audio writes to ``{file_prefix}.{audio_format}`` (no
        # output-dir param); file_prefix is a full path.
        out = Path(f"{kwargs['file_prefix']}.wav")
        AudioSegment.silent(duration=400, frame_rate=24000).export(out, format="wav")

    pkg = types.ModuleType("mlx_audio")
    tts_pkg = types.ModuleType("mlx_audio.tts")
    gen_mod = types.ModuleType("mlx_audio.tts.generate")
    gen_mod.generate_audio = generate_audio
    utils_mod = types.ModuleType("mlx_audio.tts.utils")
    utils_mod.load_model = lambda model_id: f"model::{model_id}"

    monkeypatch.setitem(sys.modules, "mlx_audio", pkg)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts", tts_pkg)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.generate", gen_mod)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", utils_mod)
    return captured


def test_synthesize_instruct_mode_omits_ref_text(tmp_path, fake_mlx):
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = CosyVoiceProvider(assets_dir=tmp_path, model="cosy-model")

    seg = provider.synthesize(
        "hello   there",
        "brittney",
        output_format="ignored",
        voice_settings={"instruct": "Speak slowly."},
    )

    assert isinstance(seg, AudioSegment)
    assert seg.frame_rate == 24000
    # Instruct Mode: directive via instruct_text, ref_audio for timbre, and
    # ref_text MUST be omitted (else CosyVoice3 runs zero-shot and drops it).
    assert fake_mlx["instruct_text"] == "Speak slowly."
    assert "ref_text" not in fake_mlx
    assert fake_mlx["text"] == "hello there"
    assert fake_mlx["model"] == "model::cosy-model"
    assert fake_mlx["ref_audio"].endswith("brittney.wav")


def test_synthesize_without_instruct_is_zero_shot(tmp_path, fake_mlx):
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = CosyVoiceProvider(assets_dir=tmp_path, model="m")
    provider.synthesize("hi", "brittney", output_format="ignored")
    # Zero-shot: transcript passed, no instruction.
    assert fake_mlx["ref_text"] == "reference transcript"
    assert "instruct_text" not in fake_mlx


def test_unknown_voice_raises_provider_error(tmp_path, fake_mlx):
    from app.core.errors import ProviderError

    provider = CosyVoiceProvider(assets_dir=tmp_path, model="m")
    with pytest.raises(ProviderError):
        provider.synthesize("hi", "nonexistent", output_format="ignored")


def test_missing_mlx_surfaces_provider_error(tmp_path, monkeypatch):
    """Non-Apple-Silicon / uninstalled mlx_audio must degrade, not crash."""
    from app.core.errors import ProviderError

    _make_voice(tmp_path, "brittney")
    # Force the lazy import to fail even if mlx_audio happens to be installed.
    monkeypatch.setitem(sys.modules, "mlx_audio", None)
    provider = CosyVoiceProvider(assets_dir=tmp_path, model="m")
    with pytest.raises(ProviderError):
        provider.synthesize("hi", "brittney", output_format="ignored")
