from app.core import sleep_text
from app.core.emotion import EMOTIONS, speed_multiplier


def test_int_to_words_basic():
    assert sleep_text.int_to_words(0) == "zero"
    assert sleep_text.int_to_words(7) == "seven"
    assert sleep_text.int_to_words(13) == "thirteen"
    assert sleep_text.int_to_words(42) == "forty-two"
    assert sleep_text.int_to_words(100) == "one hundred"
    assert sleep_text.int_to_words(305) == "three hundred five"
    assert sleep_text.int_to_words(1000) == "one thousand"
    assert sleep_text.int_to_words(2026) == "two thousand twenty-six"


def test_spell_numbers_in_sentence():
    assert sleep_text.spell_numbers("Count 3 slow breaths.") == (
        "Count three slow breaths."
    )
    assert sleep_text.spell_numbers("There were 12 stars and 100 dreams.") == (
        "There were twelve stars and one hundred dreams."
    )


def test_spell_numbers_handles_thousands_separator():
    assert sleep_text.spell_numbers("a field of 1,200 flowers") == (
        "a field of one thousand two hundred flowers"
    )


def test_spell_numbers_leaves_glued_and_oversized_alone():
    # Glued to letters (mp3) and out-of-range values are left untouched.
    assert sleep_text.spell_numbers("the mp3 file") == "the mp3 file"
    assert sleep_text.spell_numbers("1000000 stars") == "1000000 stars"


def test_spell_numbers_noop_without_digits():
    text = "The moon casts a silver glow across the room."
    assert sleep_text.spell_numbers(text) == text


def test_spell_numbers_leaves_pause_marker_duration_alone():
    # The duration inside an author's [pause:N] marker must survive spelling so
    # the provider/orchestrator can still parse it.
    assert sleep_text.spell_numbers("Rest. [pause:800] Sleep.") == (
        "Rest. [pause:800] Sleep."
    )
    assert sleep_text.spell_numbers("Count 3. [pause:1200ms] Drift.") == (
        "Count three. [pause:1200ms] Drift."
    )


def test_split_pauses_no_marker_is_single_segment():
    assert sleep_text.split_pauses("Just calm prose.") == [("Just calm prose.", 0)]


def test_split_pauses_splits_and_clamps():
    out = sleep_text.split_pauses(
        "Rest now. [pause:800] The lake is still. [pause:9000] Sleep.", max_ms=5000
    )
    assert out == [
        ("Rest now. ", 800),
        (" The lake is still. ", 5000),  # clamped to max_ms
        (" Sleep.", 0),
    ]


def test_split_pauses_tolerates_ms_suffix_and_spacing():
    out = sleep_text.split_pauses("a [ pause : 600 ms ] b")
    assert out == [("a ", 600), (" b", 0)]


def test_split_pauses_bare_pause_uses_default():
    out = sleep_text.split_pauses("Rest now. [pause] Sleep.", default_ms=1000)
    assert out == [("Rest now. ", 1000), (" Sleep.", 0)]


def test_split_pauses_bare_pause_custom_default():
    out = sleep_text.split_pauses("a [Pause] b", default_ms=500)
    assert out == [("a ", 500), (" b", 0)]


def test_split_pauses_mixed_bare_and_explicit():
    out = sleep_text.split_pauses(
        "A. [pause] B. [pause:2000] C.", default_ms=800
    )
    assert out == [("A. ", 800), (" B. ", 2000), (" C.", 0)]


# ---------------------------------------------------------------------------
# inject_sentence_pauses
# ---------------------------------------------------------------------------


def test_inject_sentence_pauses_adds_ellipsis_at_boundaries():
    assert sleep_text.inject_sentence_pauses("The sky is dark. Stars appear.") == (
        "The sky is dark.… Stars appear."
    )


def test_inject_sentence_pauses_handles_question_and_exclaim():
    assert sleep_text.inject_sentence_pauses("Are you there? Rest now! Sleep.") == (
        "Are you there?… Rest now!… Sleep."
    )


def test_inject_sentence_pauses_leaves_existing_ellipsis():
    text = "drifting... softly now."
    assert sleep_text.inject_sentence_pauses(text) == text


def test_inject_sentence_pauses_leaves_unicode_ellipsis():
    text = "drifting… softly now."
    assert sleep_text.inject_sentence_pauses(text) == text


def test_inject_sentence_pauses_ignores_lowercase_continuation():
    # An abbreviation like "Dr." followed by a lowercase word is not a boundary.
    text = "Meet Dr. roberts by the lake."
    assert sleep_text.inject_sentence_pauses(text) == text


def test_inject_sentence_pauses_skips_inside_bracket_tags():
    # A period inside a tag (rare, but possible) must not trigger a split, and a
    # real boundary after a tag still gets the ellipsis.
    text = "[calm] The night fell. Stars came out."
    assert sleep_text.inject_sentence_pauses(text) == (
        "[calm] The night fell.… Stars came out."
    )


def test_inject_sentence_pauses_noop_without_boundaries():
    text = "One long unbroken calming sentence with no breaks"
    assert sleep_text.inject_sentence_pauses(text) == text


# ---------------------------------------------------------------------------
# punctuation_to_pauses
# ---------------------------------------------------------------------------


def test_comma_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("The air is cool, and very still.")
    assert "," in result
    assert "[pause:80]" in result
    assert "cool," in result


def test_ellipsis_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("drifting... softly now.")
    assert "..." in result
    assert "[pause:350]" in result


def test_unicode_ellipsis_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("drifting… softly now.")
    assert "[pause:350]" in result


def test_semicolon_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("water is warm; it holds you.")
    assert ";" in result
    assert "[pause:200]" in result


def test_dash_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("the trees — ancient and tall.")
    assert "—" in result
    assert "[pause:250]" in result


def test_en_dash_kept_with_pause_after():
    result = sleep_text.punctuation_to_pauses("the trees – ancient.")
    assert "–" in result
    assert "[pause:250]" in result


def test_period_not_converted():
    result = sleep_text.punctuation_to_pauses("The sky is dark. Stars appear.")
    assert ". " in result or result.endswith(".")
    assert "[pause:" not in result.replace("[pause:400]", "")  # no pause at periods (ignoring paragraph)


def test_ellipsis_matched_before_period():
    result = sleep_text.punctuation_to_pauses("fading... gone.")
    assert "[pause:350]" in result
    assert "." in result


def test_author_pause_preserved():
    text = "Rest. [pause:800] Sleep now."
    result = sleep_text.punctuation_to_pauses(text)
    assert "[pause:800]" in result


def test_author_pause_not_corrupted_by_punctuation():
    text = "Rest, friend. [pause:800] Sleep."
    result = sleep_text.punctuation_to_pauses(text)
    assert "[pause:800]" in result
    assert "," in result
    assert "[pause:80]" in result


def test_paragraph_break_gets_pause():
    text = "The lake was calm.\n\nA bird sang softly."
    result = sleep_text.punctuation_to_pauses(text)
    assert "[pause:400]" in result


def test_no_double_pause_at_paragraph():
    text = "Rest now.\n\n[pause:600]\n\nDrift softly."
    result = sleep_text.punctuation_to_pauses(text)
    assert "[pause:600]" in result
    # Should not insert an additional [pause:400] near the existing marker.
    assert result.count("[pause:400]") == 0


def test_custom_durations():
    result = sleep_text.punctuation_to_pauses(
        "cool, still", comma_ms=300
    )
    assert "[pause:300]" in result
    assert "," in result


def test_multiple_punctuation_types():
    text = "cool, still... ancient; patient — waiting."
    result = sleep_text.punctuation_to_pauses(text)
    assert "[pause:80]" in result   # comma
    assert "[pause:350]" in result  # ellipsis
    assert "[pause:200]" in result  # semicolon
    assert "[pause:250]" in result  # dash


# ---------------------------------------------------------------------------
# Emotion tags — sleep-oriented additions
# ---------------------------------------------------------------------------


def test_dreamy_and_tender_are_recognized_emotions():
    assert "dreamy" in EMOTIONS
    assert "tender" in EMOTIONS


def test_dreamy_speed_multiplier():
    assert speed_multiplier("dreamy") == 0.90


def test_tender_speed_multiplier():
    assert speed_multiplier("tender") == 0.96
