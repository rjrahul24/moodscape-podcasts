"""Parse a pasted podcast script into ordered speaker turns.

Convention (as typed by the user in the UI):

    [Speaker 1]: Hello there!
    [Speaker 2]: Hi — great to be here.
    A turn may span multiple lines; it continues until the next [Tag]: line.

The tag inside the brackets is free-form (``Speaker 1``, ``Host``, ``Guest``),
so the same machinery works for arbitrary speaker names. Inline delivery tags
that some providers understand (e.g. ``[excited]``) are preserved verbatim in
the turn text — only a tag at the very start of a line that is immediately
followed by ``:`` is treated as a speaker marker.
"""

from __future__ import annotations

import re

from .errors import ScriptParseError
from .models import ScriptTurn

# A speaker marker: start of line, [label], a colon, then optional text.
_SPEAKER_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*:\s*(.*)$")


def parse_script(script_text: str) -> list[ScriptTurn]:
    """Parse ``script_text`` into an ordered list of :class:`ScriptTurn`.

    Raises :class:`ScriptParseError` if no speaker markers are found or if
    non-blank content appears before the first marker.
    """
    turns: list[ScriptTurn] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_speaker is None:
            return
        text = "\n".join(current_lines).strip()
        if text:
            turns.append(
                ScriptTurn(index=len(turns), speaker=current_speaker, text=text)
            )

    for lineno, raw_line in enumerate(script_text.splitlines(), start=1):
        match = _SPEAKER_RE.match(raw_line)
        if match:
            flush()
            current_speaker = match.group(1).strip()
            if not current_speaker:
                raise ScriptParseError(f"Empty speaker name on line {lineno}.")
            current_lines = [match.group(2)]
        elif current_speaker is None:
            if raw_line.strip():
                raise ScriptParseError(
                    f"Line {lineno} has text before any [Speaker]: marker. "
                    f"Start each turn with a marker like '[Speaker 1]:'."
                )
        else:
            current_lines.append(raw_line)

    flush()

    if not turns:
        raise ScriptParseError(
            "No speaker turns found. Use markers like '[Speaker 1]:' at the "
            "start of each line."
        )
    return turns


def distinct_speakers(turns: list[ScriptTurn]) -> list[str]:
    """Return speaker labels in first-appearance order."""
    seen: dict[str, None] = {}
    for turn in turns:
        seen.setdefault(turn.speaker, None)
    return list(seen.keys())
