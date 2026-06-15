"""Tests for F5 reference-voice discovery."""

from app.providers import f5_voice_registry


def _make_voice(assets_dir, slug, *, with_text=True, text="hello world"):
    audio_dir = assets_dir / "speakers" / "reference_audio"
    text_dir = assets_dir / "speakers" / "reference_text"
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{slug}.wav").write_bytes(b"RIFFfake")
    if with_text:
        (text_dir / f"{slug}.txt").write_text(text, encoding="utf-8")


def test_scan_finds_complete_pairs(tmp_path):
    _make_voice(tmp_path, "brittney")
    _make_voice(tmp_path, "clara")
    registry = f5_voice_registry.scan(tmp_path)
    assert set(registry) == {"brittney", "clara"}
    assert registry["brittney"]["audio"].name == "brittney.wav"
    assert registry["brittney"]["transcript"].name == "brittney.txt"


def test_wav_without_transcript_is_skipped(tmp_path):
    _make_voice(tmp_path, "lonely", with_text=False)
    assert f5_voice_registry.scan(tmp_path) == {}


def test_empty_transcript_is_skipped(tmp_path):
    _make_voice(tmp_path, "blank", text="")
    assert f5_voice_registry.scan(tmp_path) == {}


def test_missing_assets_dir_returns_empty(tmp_path):
    assert f5_voice_registry.scan(tmp_path / "does-not-exist") == {}
