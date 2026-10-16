import json
from types import SimpleNamespace

import pytest

from conftest import SERMON_TEXT
from sermon_worker.llm import (
    OpenAIStructurer, SermonNotesError, book_mentioned, enforce_fidelity, parse_notes,
)


def test_valid_notes_parse(notes_json):
    notes = parse_notes(notes_json)
    assert notes.title == "Gospel Conformity"
    assert len(notes.key_points) == 2


@pytest.mark.parametrize("raw", ["not json", "{}", json.dumps({"title": "x", "summary": "short", "excerpt": "e"})])
def test_invalid_notes_rejected(raw):
    with pytest.raises(SermonNotesError):
        parse_notes(raw)


def test_too_many_key_points_rejected(notes_json):
    data = json.loads(notes_json)
    data["key_points"] = data["key_points"] * 4
    with pytest.raises(SermonNotesError):
        parse_notes(json.dumps(data))


@pytest.mark.parametrize("ref,expected", [
    ("2 Corinthians 13:5-14", True),   # transcript says "Second Corinthians"
    ("Romans 8:28", False),
    ("1 Corinthians 13", False),
])
def test_book_mentioned(ref, expected):
    assert book_mentioned(ref, SERMON_TEXT) is expected


def test_fidelity_drops_hallucinated_scripture_and_preacher(notes_json):
    notes, review = enforce_fidelity(parse_notes(notes_json), SERMON_TEXT, {})
    assert notes.scripture_references == ["2 Corinthians 13:5-14"]
    assert notes.preacher is None
    assert any("Romans 8:28" in r for r in review)
    assert any("Pastor Invented" in r for r in review)


def test_authoritative_metadata_wins(notes_json):
    meta = {"title": "Gospel Conformity", "preacher": "The Rev. Scott Bailey", "scripture_references": ["2 Corinthians 13:5-14"]}
    notes, review = enforce_fidelity(parse_notes(notes_json), SERMON_TEXT, meta)
    assert notes.preacher == "The Rev. Scott Bailey"
    assert notes.scripture_references == ["2 Corinthians 13:5-14"]
    assert not any("No sermon title supplied" in r for r in review)


class FakeCompletions:
    def __init__(self, content=None, error=None):
        self.content, self.error, self.calls = content, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.content, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_openai_structurer_requests_strict_schema(notes_json):
    completions = FakeCompletions(content=notes_json)
    notes = OpenAIStructurer("k", "gpt-5-mini", client=fake_client(completions)).structure(SERMON_TEXT, {})
    call = completions.calls[0]
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["reasoning_effort"] == "low" and "temperature" not in call
    assert notes.title == "Gospel Conformity"


def test_openai_failure_raises_notes_error():
    completions = FakeCompletions(error=TimeoutError("boom"))
    with pytest.raises(SermonNotesError):
        OpenAIStructurer("k", "gpt-5-mini", client=fake_client(completions)).structure(SERMON_TEXT, {})
