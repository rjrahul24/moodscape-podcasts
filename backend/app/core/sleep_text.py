"""Spell standalone integers as words for sleep narration.

The AI reads bare digits in a clipped, transactional tone ("twelve thirty-four"
becomes a rushed "one-two-three-four"), which breaks a hypnotic atmosphere. The
provider's ``apply_text_normalization="auto"`` handles most of this server-side,
but spelling numbers locally too keeps the cadence calm regardless of model and
gives a deterministic, testable result.

Scope is deliberately small and dependency-free: standalone non-negative integers
up to 999,999 (more than enough for a bedtime story). Numbers glued to letters
(``mp3``), decimals, and years-as-digits are left alone — over-normalizing causes
more harm than the occasional unspelled token.
"""

from __future__ import annotations

import re

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
    "ninety",
]

# A run of digits standing on its own (not glued to letters like "mp3"). Commas
# as thousands separators are tolerated and stripped.
_INT_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})+|\d+)(?![A-Za-z0-9])")


def _under_thousand(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    hundreds, rest = divmod(n, 100)
    head = f"{_ONES[hundreds]} hundred"
    return f"{head} {_under_thousand(rest)}" if rest else head


def int_to_words(n: int) -> str:
    """Spell a non-negative integer (0–999,999) as words."""
    if n < 1000:
        return _under_thousand(n)
    thousands, rest = divmod(n, 1000)
    head = f"{_under_thousand(thousands)} thousand"
    return f"{head} {_under_thousand(rest)}" if rest else head


def spell_numbers(text: str) -> str:
    """Replace standalone integers (≤ 999,999) in ``text`` with their word form.

    Out-of-range or malformed runs are left untouched.
    """

    def repl(match: re.Match[str]) -> str:
        digits = match.group(1).replace(",", "")
        value = int(digits)
        if value > 999_999:
            return match.group(0)
        return int_to_words(value)

    return _INT_RE.sub(repl, text)
