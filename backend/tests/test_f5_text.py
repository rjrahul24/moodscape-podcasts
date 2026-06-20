"""F5 text normalization tests."""

from app.core.f5_text import normalize_for_f5


class TestNormalizeForF5:
    def test_colons_become_commas(self):
        assert normalize_for_f5("Sleep well: rest now") == "Sleep well, rest now"

    def test_ellipsis_three_dots_become_period(self):
        assert normalize_for_f5("Breathe in...") == "Breathe in."

    def test_ellipsis_unicode_becomes_period(self):
        assert normalize_for_f5("Let go…") == "Let go."

    def test_em_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now — let go") == "Rest now , let go"

    def test_en_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now – let go") == "Rest now , let go"

    def test_double_dash_becomes_comma(self):
        assert normalize_for_f5("Rest now -- let go") == "Rest now , let go"

    def test_compound_hyphen_removed(self):
        assert normalize_for_f5("well-being") == "wellbeing"

    def test_hyphen_between_digits_preserved(self):
        # Hyphens between digits are not compounds — leave them alone
        assert normalize_for_f5("3-5") == "3-5"

    def test_all_caps_lowered(self):
        assert normalize_for_f5("BREATHE in deeply") == "breathe in deeply"

    def test_mixed_case_preserved(self):
        assert normalize_for_f5("Breathe In") == "Breathe In"

    def test_single_capital_letter_preserved(self):
        assert normalize_for_f5("I am calm") == "I am calm"

    def test_combined_normalizations(self):
        result = normalize_for_f5("NOTICE: your well-being...")
        assert result == "notice, your wellbeing."

    def test_empty_string(self):
        assert normalize_for_f5("") == ""

    def test_plain_text_unchanged(self):
        assert normalize_for_f5("The night is calm and still.") == "The night is calm and still."
