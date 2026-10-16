"""Structure a sermon transcript into validated notes.

The model may only *organise* what the preacher said. Guarantees enforced here,
not just requested in the prompt:
  - strict JSON schema output, validated with Pydantic (invalid → do not publish)
  - scripture references are kept only if the book is actually mentioned in the
    transcript (or supplied by authoritative metadata)
  - a preacher name is kept only if it appears in the transcript (or metadata)
  - unknown values are null / [] rather than guesses
"""
from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)


class SermonNotesError(RuntimeError):
    """LLM failed or returned invalid output: do not publish."""


class KeyPoint(BaseModel):
    heading: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=900)


class SermonNotes(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    preacher: str | None = None
    scripture_references: list[str] = Field(default_factory=list, max_length=6)
    summary: str = Field(min_length=40, max_length=1200)
    key_points: list[KeyPoint] = Field(default_factory=list, max_length=6)
    closing_takeaway: str | None = Field(default=None, max_length=600)
    excerpt: str = Field(min_length=20, max_length=320)

    @field_validator("title", "summary", "excerpt")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


SYSTEM_PROMPT = """You prepare website sermon notes for All Saints' Church, an Anglican parish.
You are given the transcript of ONE sermon (automatically transcribed, so expect small errors).

Rules — fidelity matters more than polish:
- Only organise and condense what the preacher actually said. Do not add ideas, illustrations, applications or doctrine that are not in the transcript.
- Do not alter or "improve" the theology. Use the preacher's own emphases and, where natural, their wording.
- Do not invent quotations. Do not put words in quotation marks unless they appear in the transcript.
- preacher: the preacher's name ONLY if it is explicitly stated in the transcript; otherwise null. Never guess from church context.
- scripture_references: ONLY passages the preacher explicitly names (e.g. "2 Corinthians 13:5-14"). Use standard book names. If no chapter/verse is stated, give what is stated (e.g. "2 Corinthians 13"). If none are named, return [].
- key_points: 2–5 main movements of the sermon in the order preached. Headings are short; bodies are 2–4 sentences.
- title: a short title reflecting the sermon's main theme (an editor will confirm it).
- summary: 2–4 sentences. excerpt: one sentence (max ~200 characters) for listings.
- closing_takeaway: the preacher's own concluding exhortation if there is one, else null.
- Ignore liturgy, announcements and greetings that are not part of the sermon.
- If something is unclear in the transcript, leave it out rather than guess."""

JSON_SCHEMA = {
    "name": "sermon_notes",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "preacher", "scripture_references", "summary", "key_points", "closing_takeaway", "excerpt"],
        "properties": {
            "title": {"type": "string"},
            "preacher": {"type": ["string", "null"]},
            "scripture_references": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "key_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["heading", "body"],
                    "properties": {"heading": {"type": "string"}, "body": {"type": "string"}},
                },
            },
            "closing_takeaway": {"type": ["string", "null"]},
            "excerpt": {"type": "string"},
        },
    },
}

ORDINALS = {"1": ("1", "first", "one", "i"), "2": ("2", "second", "two", "ii"), "3": ("3", "third", "three", "iii")}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower()))


def book_mentioned(reference: str, transcript: str) -> bool:
    """True if the reference's book (with ordinal, in any spoken form) occurs in the transcript."""
    m = re.match(r"^\s*([123])?\s*([A-Za-z][A-Za-z ]*?)\s*\d", reference + " 0")
    if not m:
        return False
    ordinal, book = m.group(1), _norm(m.group(2)).strip()
    if book in ("psalm", "psalms"):
        book = "psalm"
    norm = " " + _norm(transcript) + " "
    if not ordinal:
        return f" {book}" in norm
    return any(f" {form} {book}" in norm for form in ORDINALS[ordinal])


def enforce_fidelity(notes: SermonNotes, transcript: str, metadata: dict) -> tuple[SermonNotes, list[str]]:
    """Apply authoritative metadata and drop unsupported claims. Returns (notes, reviewer notes)."""
    review: list[str] = []
    data = notes.model_dump()

    if metadata.get("scripture_references"):
        data["scripture_references"] = list(metadata["scripture_references"])
    else:
        kept = [r for r in data["scripture_references"] if book_mentioned(r, transcript)]
        dropped = sorted(set(data["scripture_references"]) - set(kept))
        if dropped:
            review.append(f"Removed scripture not found in transcript: {', '.join(dropped)}")
        data["scripture_references"] = kept

    if metadata.get("preacher"):
        data["preacher"] = metadata["preacher"]
    elif data.get("preacher") and _norm(data["preacher"]).strip() not in _norm(transcript):
        review.append(f"Removed preacher '{data['preacher']}' (not stated in transcript)")
        data["preacher"] = None

    if metadata.get("title"):
        data["title"] = metadata["title"]
    return SermonNotes.model_validate(data), review


class Structurer(Protocol):
    name: str

    def structure(self, transcript: str, metadata: dict) -> SermonNotes: ...


class OpenAIStructurer:
    name = "openai"

    def __init__(self, api_key: str, model: str, client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=120, max_retries=2)
        self.client = client
        self.model = model

    def structure(self, transcript: str, metadata: dict) -> SermonNotes:
        context = {k: v for k, v in metadata.items() if v and k in ("service_title", "service_date")}
        user = f"Service context (not part of the sermon): {json.dumps(context)}\n\nSermon transcript:\n{transcript}"
        kwargs = {}
        if re.match(r"^(gpt-5|o\d)", self.model):
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["temperature"] = 0.2
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
                response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
                max_completion_tokens=6000,
                **kwargs,
            )
        except Exception as exc:  # network/auth/rate limit: never publish on failure
            raise SermonNotesError(f"OpenAI request failed: {exc.__class__.__name__}") from None
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            raise SermonNotesError("Model refused the request")
        return parse_notes(choice.message.content or "")


def parse_notes(raw: str) -> SermonNotes:
    try:
        return SermonNotes.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SermonNotesError(f"Invalid sermon notes JSON: {str(exc).splitlines()[0]}") from None
