"""Sleep-story text preprocessing: number spelling and punctuation-to-pause conversion.

The AI reads bare digits in a clipped, transactional tone ("twelve thirty-four"
becomes a rushed "one-two-three-four"), which breaks a hypnotic atmosphere. The
provider's ``apply_text_normalization="auto"`` handles most of this server-side,
but spelling numbers locally too keeps the cadence calm regardless of model and
gives a deterministic, testable result.

Scope is deliberately small and dependency-free: standalone non-negative integers
up to 999,999 (more than enough for a bedtime story). Numbers glued to letters
(``mp3``), decimals, and years-as-digits are left alone — over-normalizing causes
more harm than the occasional unspelled token.

``punctuation_to_pauses`` converts within-sentence punctuation (commas, ellipses,
semicolons, dashes) to explicit ``[pause:N]`` markers for Kokoro, which ignores
punctuation entirely for pausing. The orchestrator's existing ``split_pauses``
machinery splices real silence at each marker.
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

# Author-placed deliberate-breath marker: [pause:800], [pause:800ms], or bare
# [pause] (spaces and case tolerated). The app renders this as a real silence —
# a native <break> on ElevenLabs v2, inserted silence on every other engine.
# Bare [pause] (no duration) uses a caller-supplied default.
_PAUSE_RE = re.compile(r"\[\s*pause\s*(?::\s*(\d+)\s*(?:ms)?\s*)?\s*\]", re.IGNORECASE)
# The opening of a pause marker, anchored to the end of the text seen so far —
# used so number-spelling leaves the duration inside [pause:800] untouched.
_PAUSE_PREFIX_RE = re.compile(r"\[\s*pause\s*:\s*\Z", re.IGNORECASE)


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
        # Leave the duration inside an author's [pause:800] marker as digits.
        if _PAUSE_PREFIX_RE.search(match.string[: match.start()]):
            return match.group(0)
        digits = match.group(1).replace(",", "")
        value = int(digits)
        if value > 999_999:
            return match.group(0)
        return int_to_words(value)

    return _INT_RE.sub(repl, text)


# A sentence boundary that should get a soft breathing ellipsis: terminal
# punctuation, NOT already followed by an ellipsis/em-dash, then whitespace, then
# the start of the next sentence (open quote/bracket/paren or a capital letter).
_SENTENCE_BOUNDARY_RE = re.compile(
    r"""(?<=[.!?])      # a sentence-ending mark
        (?<!\.\.\.)     # but not the tail of "..."
        [ \t]+          # inline space (don't touch paragraph breaks / newlines)
        (?=[\[\"'(“‘A-Z])  # next sentence opens here
    """,
    re.VERBOSE,
)

# A bracket tag like [calm] or [pause:800] — boundaries inside one are skipped so
# we never split a delivery cue.
_BRACKET_SPAN_RE = re.compile(r"\[[^\]]*\]")


def inject_sentence_pauses(text: str) -> str:
    """Insert an ellipsis ("…") at sentence boundaries that lack one.

    Gives the narrator a soft breathing pause at each sentence break (ElevenLabs
    honours "…" natively on both v2 and v3). Boundaries already followed by an
    ellipsis or em-dash are left alone, and boundaries that fall inside a ``[…]``
    delivery cue are never touched. Deterministic — no RNG.
    """
    # Mask bracket tags so a "." inside one is never treated as a boundary.
    spans = [(m.start(), m.end()) for m in _BRACKET_SPAN_RE.finditer(text)]

    def _in_span(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    def _repl(match: re.Match[str]) -> str:
        if _in_span(match.start()):
            return match.group(0)
        return "… "

    return _SENTENCE_BOUNDARY_RE.sub(_repl, text)


def split_pauses(
    text: str, *, max_ms: int = 5000, default_ms: int = 1000,
) -> list[tuple[str, int]]:
    """Split ``text`` on ``[pause:N]`` / ``[pause]`` markers into ``(segment, pause_ms_after)``.

    Each returned tuple is a run of prose followed by the deliberate pause (ms)
    the author requested after it; the final segment's pause is ``0``. Pause
    durations are clamped to ``[0, max_ms]``. A bare ``[pause]`` (no duration)
    uses ``default_ms``. With no markers present the result is a single
    ``[(text, 0)]`` — callers can treat that as the no-op case.

    The provider-agnostic splice path inserts a silence of ``pause_ms_after``
    between consecutive segments; the ElevenLabs v2 path instead keeps the marker
    inline and renders it as a native ``<break>`` (see the provider).
    """
    segments: list[tuple[str, int]] = []
    last = 0
    for match in _PAUSE_RE.finditer(text):
        raw = match.group(1)
        ms = int(raw) if raw is not None else default_ms
        segments.append((text[last : match.start()], min(max(ms, 0), max_ms)))
        last = match.end()
    segments.append((text[last:], 0))
    return segments


# ---------------------------------------------------------------------------
# Punctuation-to-pause conversion (Kokoro sleep stories)
# ---------------------------------------------------------------------------

# Order matters: multi-char sequences first so "..." isn't eaten as three commas.
_ELLIPSIS_RE = re.compile(r"\.{3}|…")
_DASH_RE = re.compile(r"—|–")
_SEMICOLON_RE = re.compile(r";")
_COMMA_RE = re.compile(r",")
_PARA_BREAK = re.compile(r"\n\s*\n")


def _has_nearby_pause(text: str, pos: int, window: int = 20) -> bool:
    """True if a ``[pause:N]`` marker exists within ``window`` chars of ``pos``."""
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    return bool(_PAUSE_RE.search(text[start:end]))


def punctuation_to_pauses(
    text: str,
    *,
    comma_ms: int = 80,
    ellipsis_ms: int = 350,
    semicolon_ms: int = 200,
    dash_ms: int = 250,
    paragraph_ms: int = 400,
) -> str:
    """Insert ``[pause:N]`` markers after within-sentence punctuation.

    Kokoro TTS ignores punctuation for pausing — commas, ellipses, semicolons,
    and dashes produce no audible gap. This function inserts ``[pause:N]``
    markers **after** each mark (keeping the punctuation in the text) so Kokoro
    retains the prosodic cues that punctuation provides for intonation, while
    the orchestrator's ``split_pauses`` machinery splices real silence.

    **Periods are left intact** — sentence boundaries are handled by the chunker
    (which splits on sentences) and the orchestrator (which inserts the
    inter-sentence gap). Converting periods would double-pause.

    Existing author-placed ``[pause:N]`` markers are preserved. Paragraph breaks
    (double newlines) without a nearby marker get ``[pause:{paragraph_ms}]``.

    Fully deterministic — no RNG.
    """
    # Protect existing [pause:N] markers by replacing them with placeholders,
    # inserting pauses after punctuation, then restoring them.
    placeholders: list[str] = []

    def _save_pause(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00PAUSE{len(placeholders) - 1}\x00"

    text = _PAUSE_RE.sub(_save_pause, text)

    # Insert pause markers AFTER punctuation (order: multi-char first).
    # The punctuation stays in the text so Kokoro can use it for prosody.
    text = _ELLIPSIS_RE.sub(lambda m: f"{m.group(0)} [pause:{ellipsis_ms}]", text)
    text = _DASH_RE.sub(lambda m: f"{m.group(0)} [pause:{dash_ms}]", text)
    text = _SEMICOLON_RE.sub(lambda m: f"{m.group(0)} [pause:{semicolon_ms}]", text)
    text = _COMMA_RE.sub(lambda m: f"{m.group(0)} [pause:{comma_ms}]", text)

    # Restore original [pause:N] markers.
    for i, original in enumerate(placeholders):
        text = text.replace(f"\x00PAUSE{i}\x00", original)

    # Insert paragraph-break pauses where none exist.
    def _para_repl(match: re.Match[str]) -> str:
        if _has_nearby_pause(match.string, match.start()):
            return match.group(0)
        return f"\n\n[pause:{paragraph_ms}]\n\n"

    text = _PARA_BREAK.sub(_para_repl, text)

    # Clean up doubled spaces from insertions.
    text = re.sub(r"  +", " ", text)

    return text
