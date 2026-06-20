from app.core import chunker
from app.core.models import ScriptTurn


def test_split_sentences_basic():
    text = "Hello there. How are you? I am fine!"
    assert chunker.split_sentences(text) == [
        "Hello there.",
        "How are you?",
        "I am fine!",
    ]


def test_split_sentences_collapses_newlines():
    text = "First line\nstill first.\n\nSecond one."
    assert chunker.split_sentences(text) == ["First line still first.", "Second one."]


def test_split_sentences_empty():
    assert chunker.split_sentences("   \n  ") == []


def test_budget_for_defaults_and_overrides():
    assert chunker.budget_for("kokoro") == 400
    assert chunker.budget_for("f5") == 250
    assert chunker.budget_for("elevenlabs") == 1000
    assert chunker.budget_for("unknown") == chunker.FALLBACK_BUDGET
    assert chunker.budget_for("kokoro", overrides={"kokoro": 123}) == 123


def test_chunk_text_packs_under_budget():
    text = "Aaaa. Bbbb. Cccc. Dddd."  # each sentence 5 chars
    chunks = chunker.chunk_text(text, max_chars=12)
    # Packs as many whole sentences as fit per chunk, never exceeding budget.
    assert all(len(c) <= 12 for c in chunks)
    assert " ".join(chunks).replace("  ", " ") == text


def test_chunk_text_never_splits_a_sentence_that_fits():
    text = "One two three four five six seven eight."
    chunks = chunker.chunk_text(text, max_chars=100)
    assert chunks == [text]


def test_chunk_text_hard_splits_overlong_sentence():
    long_sentence = "word " * 50  # 250 chars, no terminal punctuation
    chunks = chunker.chunk_text(long_sentence.strip(), max_chars=40)
    assert len(chunks) > 1
    assert all(len(c) <= 40 for c in chunks)


def test_chunk_text_empty():
    assert chunker.chunk_text("", max_chars=100) == []


def test_chunk_turn_preserves_speaker_and_indexes():
    turn = ScriptTurn(index=3, speaker="Speaker 2", text="Aaaa. Bbbb. Cccc.")
    chunks = chunker.chunk_turn(turn, "kokoro", start_index=7, overrides={"kokoro": 10})
    assert all(c.speaker == "Speaker 2" for c in chunks)
    assert all(c.turn_index == 3 for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(7, 7 + len(chunks)))


def test_chunk_prose_is_single_narrator():
    chunks = chunker.chunk_prose("Aaaa. Bbbb. Cccc.", "kokoro", overrides={"kokoro": 10})
    assert all(c.speaker == "narrator" for c in chunks)
    assert all(c.turn_index == 0 for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
