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
    # Write a real WAV so _condition_reference_audio can read it with soundfile
    import soundfile as sf
    sr = 24000
    audio = np.random.randn(sr * 2).astype(np.float32) * 0.1
    sf.write(str(audio_dir / f"{slug}.wav"), audio, sr)
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
    utils_mod.preprocess_ref_audio_text = lambda audio, text, **k: (
        audio,
        text if text else "whisper transcribed text",
    )

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
    assert len(seg) > 0  # non-empty audio returned
    # Whisper-verified ref_text (fake returns "whisper transcribed text")
    assert fake_f5["ref_text"] == "whisper transcribed text"
    assert fake_f5["gen_text"] == "hello there"
    assert fake_f5["nfe_step"] == 16
    assert fake_f5["cfg_strength"] == 1.5


def test_unknown_voice_raises_provider_error(tmp_path, fake_f5):
    from app.core.errors import ProviderError

    provider = F5Provider(assets_dir=tmp_path)
    with pytest.raises(ProviderError):
        provider.synthesize("hi", "nonexistent", output_format="ignored")


def test_condition_reference_audio_adds_trailing_pad(tmp_path):
    """The conditioned reference should be longer than the original (trailing noise)."""
    import soundfile as sf

    original = tmp_path / "ref.wav"
    sr = 24000
    audio = np.random.randn(sr * 2).astype(np.float32) * 0.1  # 2s of audio
    sf.write(str(original), audio, sr)

    from app.providers.f5_provider import _condition_reference_audio

    conditioned = _condition_reference_audio(str(original))
    cond_audio, cond_sr = sf.read(conditioned, dtype="float32")
    # Should be ~1s longer (the trailing noise pad)
    assert len(cond_audio) > len(audio)
    assert abs(len(cond_audio) - len(audio) - sr) < sr * 0.1  # ~1s pad


def test_trim_trailing_silence():
    """Trailing silence should be removed, keeping a 50ms decay tail."""
    from app.providers.f5_provider import _trim_trailing_silence

    sr = 24000
    speech = np.random.randn(sr).astype(np.float32) * 0.1  # 1s speech
    silence = np.zeros(sr, dtype=np.float32)  # 1s silence
    audio = np.concatenate([speech, silence])
    trimmed = _trim_trailing_silence(audio, sr)
    # Should be much shorter than original (silence removed)
    assert len(trimmed) < len(audio)
    # But longer than just the speech (50ms tail kept)
    tail_samples = int(0.05 * sr)
    assert len(trimmed) >= len(speech)
    assert len(trimmed) <= len(speech) + tail_samples + 10


def test_apply_silero_vad_graceful_fallback():
    """If Silero VAD fails, the original audio should be returned."""
    from app.providers.f5_provider import _apply_silero_vad

    sr = 24000
    audio = np.random.randn(sr).astype(np.float32) * 0.1
    # This will fail because torch.hub won't have Silero cached in test env,
    # but should fall back gracefully.
    result = _apply_silero_vad(audio, sr)
    assert len(result) > 0  # got something back (original or processed)


def test_clip_audio_file_trims_long_reference(tmp_path):
    """A reference longer than the limit is trimmed to ~clip_seconds."""
    import soundfile as sf

    from app.providers.f5_provider import _clip_audio_file

    long_ref = tmp_path / "long.wav"
    sr = 24000
    sf.write(str(long_ref), np.random.randn(sr * 13).astype(np.float32) * 0.1, sr)

    clipped = _clip_audio_file(str(long_ref), 8.0)
    assert clipped != str(long_ref)  # a new temp file was written
    audio, out_sr = sf.read(clipped, dtype="float32")
    assert abs(len(audio) / out_sr - 8.0) < 0.05


def test_clip_audio_file_passthrough_when_short(tmp_path):
    """A reference already within the limit is returned unchanged."""
    import soundfile as sf

    from app.providers.f5_provider import _clip_audio_file

    short_ref = tmp_path / "short.wav"
    sr = 24000
    sf.write(str(short_ref), np.random.randn(sr * 5).astype(np.float32) * 0.1, sr)

    assert _clip_audio_file(str(short_ref), 8.0) == str(short_ref)


def test_synthesize_reads_nfe_step_from_voice_settings(tmp_path, fake_f5):
    """voice_settings['nfe_step'] should override the constructor default."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, nfe_step=16)

    provider.synthesize(
        "hello there", "brittney",
        output_format="ignored",
        voice_settings={"nfe_step": 32},
    )
    assert fake_f5["nfe_step"] == 32


def test_short_phrase_gets_slower_speed(tmp_path, fake_f5):
    """Short phrases (<=12 non-space chars) should use speed 0.5."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, speed=0.88)

    # "Breathe in." has 10 non-space chars -> triggers short-phrase pacing
    provider.synthesize(
        "Breathe in.", "brittney",
        output_format="ignored",
        voice_settings={"speed": 0.88},
    )
    assert fake_f5["speed"] == pytest.approx(0.5, abs=0.01)


def test_normal_sentence_not_slowed(tmp_path, fake_f5):
    """Normal-length sentences should NOT trigger short-phrase pacing."""
    _make_voice(tmp_path, "brittney", text="reference transcript")
    provider = F5Provider(assets_dir=tmp_path, speed=0.88)

    provider.synthesize(
        "Notice the gentle breathing in your body.", "brittney",
        output_format="ignored",
        voice_settings={"speed": 0.88},
    )
    # Speed should be 0.88 * emotion multiplier (1.0), not 0.5
    assert fake_f5["speed"] == pytest.approx(0.88, abs=0.05)
