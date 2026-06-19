from app.core import sleep_text


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
