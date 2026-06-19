"""Long-form QC tests.

The pure scoring (markup stripping, word normalization, WER edit distance) is
tested directly. The heavy ASR/embedding paths are faked into ``sys.modules`` —
no Whisper download, no encoder, runnable on any platform — and the missing-deps
branches assert graceful degradation (a ``None`` metric + an explanatory note,
never a crash).
"""

import sys
import types

import pytest

from app.config import Settings
from app.core import qc


# ── pure helpers ───────────────────────────────────────────────────────────────
def test_strip_markup_removes_inline_tags():
    assert qc.strip_markup("Breathe in [pause:600] and out [calm]").split() == [
        "Breathe",
        "in",
        "and",
        "out",
    ]


def test_normalize_words_ignores_case_and_punctuation():
    assert qc.normalize_words("Hello, THERE! It's calm.") == [
        "hello",
        "there",
        "it's",
        "calm",
    ]


def test_wer_exact_match_is_zero():
    assert qc.word_error_rate("the tide breathes in", "The tide breathes in.") == 0.0


def test_wer_counts_substitution_insertion_deletion():
    # ref: a b c d (4 words); hyp drops "b", swaps "c"->"x": edits = 2 -> 0.5
    assert qc.word_error_rate("a b c d", "a x d") == pytest.approx(0.5)


def test_wer_empty_reference():
    assert qc.word_error_rate("", "") == 0.0
    assert qc.word_error_rate("", "unexpected words") == 1.0


# ── transcription (faked) ───────────────────────────────────────────────────────
@pytest.fixture
def fake_mlx_whisper(monkeypatch):
    mod = types.ModuleType("mlx_whisper")
    mod.transcribe = lambda path, path_or_hf_repo=None: {"text": "the tide breathes in"}
    monkeypatch.setitem(sys.modules, "mlx_whisper", mod)
    return mod


def test_transcribe_uses_mlx_when_available(fake_mlx_whisper):
    text, note = qc.transcribe("ignored.wav", Settings())
    assert text == "the tide breathes in"
    assert note is None


def test_transcribe_degrades_when_no_backend(monkeypatch):
    # Force both imports to fail even if installed.
    monkeypatch.setitem(sys.modules, "mlx_whisper", None)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    text, note = qc.transcribe("ignored.wav", Settings())
    assert text is None
    assert note and "uv sync --extra qc" in note


# ── speaker similarity (faked) ───────────────────────────────────────────────────
@pytest.fixture
def fake_resemblyzer(monkeypatch):
    """Fake encoder: reference embeds to [1,0]; the master windows to a list of
    2-vectors so we can drive cosine similarity deterministically."""
    import numpy as np

    state = {"partials": [np.array([1.0, 0.0]), np.array([0.0, 1.0])]}

    class _Slice:
        def __init__(self, start):
            self.start = start

    class VoiceEncoder:
        def __init__(self, *a, **k):
            pass

        def embed_utterance(self, wav, return_partials=False):
            if return_partials:
                partials = state["partials"]
                slices = [_Slice(i * 16000) for i in range(len(partials))]
                return np.array([1.0, 0.0]), partials, slices
            return np.array([1.0, 0.0])  # reference

    mod = types.ModuleType("resemblyzer")
    mod.VoiceEncoder = VoiceEncoder
    mod.preprocess_wav = lambda path: path
    monkeypatch.setitem(sys.modules, "resemblyzer", mod)
    return state


def test_speaker_similarity_flags_drifted_window(fake_resemblyzer):
    # Window 0 matches the reference (sim 1.0); window 1 is orthogonal (sim 0.0)
    # and falls below the 0.75 threshold.
    report, note = qc.speaker_similarity("master.wav", "ref.wav", Settings())
    assert note is None
    assert report.sim_min == pytest.approx(0.0)
    assert report.sim_mean == pytest.approx(0.5)
    assert [w.start_s for w in report.sim_flagged] == [pytest.approx(1.0)]


def test_speaker_similarity_degrades_without_encoder(monkeypatch):
    monkeypatch.setitem(sys.modules, "resemblyzer", None)
    report, note = qc.speaker_similarity("master.wav", "ref.wav", Settings())
    assert report.sim_mean is None
    assert note and "uv sync --extra qc" in note


# ── run_qc integration (faked) ───────────────────────────────────────────────────
def test_run_qc_computes_wer_and_sim(fake_mlx_whisper, fake_resemblyzer):
    report = qc.run_qc(
        "master.wav",
        source_text="The tide [pause:600] breathes in.",
        settings=Settings(),
        reference_audio="ref.wav",
    )
    assert report.wer == 0.0  # transcript matches the markup-stripped source
    assert report.transcript == "the tide breathes in"
    assert report.sim_min == pytest.approx(0.0)
    assert not report.notes


def test_run_qc_without_reference_skips_sim(fake_mlx_whisper):
    report = qc.run_qc(
        "master.wav", source_text="the tide breathes in", settings=Settings()
    )
    assert report.wer == 0.0
    assert report.sim_mean is None
    assert report.sim_flagged == []
