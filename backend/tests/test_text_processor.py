"""Tests for the conversational planner (sentences, pauses, tone tags)."""

import random

from app.core.text_processor import Pause, Speech, extract_emotion, plan_turn

GAP_MIN, GAP_MAX = 80, 220


def _plan(text, *, provider="elevenlabs", max_chars=2400, seed=0, inline_sfx=False):
    return plan_turn(
        text,
        provider=provider,
        max_chars=max_chars,
        rng=random.Random(seed),
        gap_min_ms=GAP_MIN,
        gap_max_ms=GAP_MAX,
        inline_sfx=inline_sfx,
    )


def test_extract_emotion_lifts_and_strips_known_tag():
    emotion, rest = extract_emotion("[excited] It works!")
    assert emotion == "excited"
    assert rest == "It works!"


def test_extract_emotion_is_case_insensitive():
    emotion, _ = extract_emotion("[CALM] easy now")
    assert emotion == "calm"


def test_unknown_tag_is_left_in_text():
    emotion, rest = extract_emotion("[laughs] yeah right")
    assert emotion is None
    assert rest == "[laughs] yeah right"


def test_single_sentence_has_no_trailing_gap():
    items = _plan("Just one sentence here.")
    assert items == [Speech("Just one sentence here.", None, 0)]


def test_intra_sentence_gaps_inserted_between_sentences():
    items = _plan("First sentence. Second sentence. Third one.")
    speeches = [it for it in items if isinstance(it, Speech)]
    assert [s.text for s in speeches] == [
        "First sentence.",
        "Second sentence.",
        "Third one.",
    ]
    # Every sentence but the last gets a gap within the configured range.
    assert all(GAP_MIN <= s.gap_after_ms <= GAP_MAX for s in speeches[:-1])
    assert speeches[-1].gap_after_ms == 0


def test_explicit_pause_tag_becomes_pause_item():
    items = _plan("Hold on. [pause:600] Okay go.")
    pauses = [it for it in items if isinstance(it, Pause)]
    assert pauses == [Pause(600)]
    # The pause sits between the two speech spans, in order.
    kinds = [type(it).__name__ for it in items]
    assert kinds == ["Speech", "Pause", "Speech"]


def test_pause_tag_accepts_ms_suffix():
    items = _plan("Wait. [pause:300ms] Done.")
    assert Pause(300) in items


def test_emotion_attaches_to_span_speech():
    items = _plan("[excited] We were wrong. And that is great.")
    speeches = [it for it in items if isinstance(it, Speech)]
    assert all(s.emotion == "excited" for s in speeches)
    assert "[excited]" not in speeches[0].text


def test_budget_splitting_delegates_to_chunker():
    long_sentence = "word " * 200  # ~1000 chars, no terminal punctuation
    items = _plan(long_sentence.strip() + ".", max_chars=100)
    speeches = [it for it in items if isinstance(it, Speech)]
    assert len(speeches) > 1
    assert all(len(s.text) <= 100 for s in speeches)
    # Sub-pieces of one sentence run together (no micro-pause between them).
    assert all(s.gap_after_ms == 0 for s in speeches)


def test_deterministic_for_same_seed():
    a = _plan("One. Two. Three. Four.", seed=42)
    b = _plan("One. Two. Three. Four.", seed=42)
    assert a == b


def test_mindfulness_tone_word_is_recognized():
    emotion, rest = extract_emotion("[soothing] Let go now.")
    assert emotion == "soothing"
    assert rest == "Let go now."


def test_sfx_tag_becomes_pause_by_default():
    # Without inline-SFX support, [deep_breath] turns into a short pause and the
    # literal tag never reaches a provider.
    items = _plan("Settle in. [deep_breath] And rest.")
    kinds = [type(it).__name__ for it in items]
    assert kinds == ["Speech", "Pause", "Speech"]
    pause = next(it for it in items if isinstance(it, Pause))
    assert pause.ms == 600  # SFX_PAUSE_MS["deep_breath"]
    assert all("[deep_breath]" not in s.text for s in items if isinstance(s, Speech))


def test_sfx_tag_kept_inline_when_provider_performs_it():
    # An inline-SFX-capable provider keeps the tag in the text (no extra pause).
    items = _plan("Settle in [deep_breath] and rest.", inline_sfx=True)
    assert all(not isinstance(it, Pause) for it in items)
    assert any("[deep_breath]" in it.text for it in items if isinstance(it, Speech))
