import pytest

from app.core.errors import ScriptParseError
from app.core.script_parser import distinct_speakers, parse_script


def test_parses_basic_two_speaker_script():
    script = "[Speaker 1]: Hello!\n[Speaker 2]: Hi there."
    turns = parse_script(script)
    assert [(t.speaker, t.text) for t in turns] == [
        ("Speaker 1", "Hello!"),
        ("Speaker 2", "Hi there."),
    ]
    assert [t.index for t in turns] == [0, 1]


def test_multiline_turn_continues_until_next_marker():
    script = "[Host]: Line one.\nStill the host.\n[Guest]: My turn."
    turns = parse_script(script)
    assert turns[0].text == "Line one.\nStill the host."
    assert turns[1].text == "My turn."


def test_blank_lines_before_first_marker_are_ignored():
    turns = parse_script("\n\n[Speaker 1]: Hi")
    assert len(turns) == 1


def test_distinct_speakers_preserves_first_appearance_order():
    script = "[B]: x\n[A]: y\n[B]: z"
    assert distinct_speakers(parse_script(script)) == ["B", "A"]


def test_inline_bracket_tags_in_text_are_preserved():
    turns = parse_script("[Speaker 1]: [excited] Wow, hello!")
    assert turns[0].text == "[excited] Wow, hello!"


def test_text_before_first_marker_raises():
    with pytest.raises(ScriptParseError):
        parse_script("just some text\n[Speaker 1]: hi")


def test_no_markers_raises():
    with pytest.raises(ScriptParseError):
        parse_script("no markers at all")


def test_empty_speaker_name_raises():
    with pytest.raises(ScriptParseError):
        parse_script("[]: hello")
