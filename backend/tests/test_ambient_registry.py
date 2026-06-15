from app.storage import ambient_registry


def test_scan_missing_dir_returns_empty(tmp_path):
    assert ambient_registry.scan(tmp_path / "nope") == {}


def test_scan_finds_wav_and_mp3(tmp_path):
    (tmp_path / "rain.wav").write_bytes(b"x")
    (tmp_path / "fire.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore me")
    found = ambient_registry.scan(tmp_path)
    assert set(found) == {"rain", "fire"}
    assert found["rain"].name == "rain.wav"
