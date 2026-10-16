"""Scripture for a service from the official ACNA lectionary insert.

All Saints' publishes a weekly "Readings and Collect" post linking the Anglican
Church in North America's insert PDF for that Sunday (BCP 2019 lectionary). The
insert contains each reading's reference and full ESV text, so the sermon post
can show the passage exactly like the parish's existing posts — with no ESV API key.

    insert_url_for(service_date)        -> URL from data/lectionary_inserts.json
    parse_insert(pdf text)              -> [Reading(kind, reference, Passage)]
    choose_readings(readings, sermon)   -> the reading(s) the preacher actually names

Choosing is evidence-based, never guessed: a reading is chosen only if its book
is named at least twice in the sermon transcript. Otherwise nothing is chosen and
the post is flagged for the editor.
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from .scripture import Passage

log = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent / "data" / "lectionary_inserts.json"

# Headings used by the inserts (Easter-season and feast-day inserts say "First Reading" / "Epistle Reading").
SECTION_RE = re.compile(
    r"^(Old Testament Reading|First Reading|Second Reading|New Testament Reading|Epistle Reading"
    r"|The Epistle|The Holy Gospel|The Gospel)\s*$",
    re.M,
)
# A reference line, e.g. "Matthew 9:35-10:15", "Acts 6:1-9, 7:2a,51-60", "Gal 6:1-18", "2 Corinthians 13:(5-10)11-14".
REF_RE = re.compile(r"^((?:[123] )?[A-Z][a-z]+\.?(?: (?:of )?[A-Z][a-z]+)* \d+:[0-9a-c()\-–,: ]+[0-9a-c)])\s*$", re.M)
END_RE = re.compile(r"(Reader|Deacon|Celebrant)?:?\s*The (word|Gospel) of the Lord", re.I)
ORDINALS = {"1": ("1", "first", "one", "i"), "2": ("2", "second", "two", "ii"), "3": ("3", "third", "three", "iii")}
ABBREVIATIONS = {
    "Gen": "Genesis", "Ex": "Exodus", "Exod": "Exodus", "Lev": "Leviticus", "Num": "Numbers", "Deut": "Deuteronomy",
    "Josh": "Joshua", "Judg": "Judges", "Sam": "Samuel", "Kgs": "Kings", "Chr": "Chronicles", "Neh": "Nehemiah",
    "Ps": "Psalm", "Prov": "Proverbs", "Eccl": "Ecclesiastes", "Isa": "Isaiah", "Jer": "Jeremiah", "Lam": "Lamentations",
    "Ezek": "Ezekiel", "Dan": "Daniel", "Hos": "Hosea", "Obad": "Obadiah", "Mic": "Micah", "Nah": "Nahum",
    "Hab": "Habakkuk", "Zeph": "Zephaniah", "Hag": "Haggai", "Zech": "Zechariah", "Mal": "Malachi", "Mt": "Matthew",
    "Matt": "Matthew", "Mk": "Mark", "Lk": "Luke", "Jn": "John", "Rom": "Romans", "Cor": "Corinthians",
    "Gal": "Galatians", "Eph": "Ephesians", "Phil": "Philippians", "Col": "Colossians", "Thess": "Thessalonians",
    "Tim": "Timothy", "Tit": "Titus", "Philem": "Philemon", "Heb": "Hebrews", "Jas": "James", "Pet": "Peter",
    "Rev": "Revelation",
}


@dataclass
class Reading:
    kind: str           # "Old Testament" | "First Reading" | "New Testament" | "Gospel"
    reference: str      # normalised, e.g. "2 Corinthians 13:5-14"
    passage: Passage


# ---------------------------------------------------------------------------
# Insert lookup
# ---------------------------------------------------------------------------

def insert_url_for(service_date: str, data_file: Path = DATA) -> str | None:
    if not data_file.exists():
        return None
    return (json.loads(data_file.read_text(encoding="utf-8")).get("inserts") or {}).get(service_date)


def fetch_insert_text(url: str, session: requests.Session | None = None) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf not installed; cannot read lectionary inserts")
        return None
    try:
        # The ACNA site rejects the default python-requests agent.
        resp = (session or requests.Session()).get(url, timeout=30, headers={"User-Agent": "ASC-Sermon-Worker"})
        resp.raise_for_status()
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(resp.content)).pages)
    except Exception as exc:  # noqa: BLE001 - any failure means "reference only"
        log.warning("Lectionary insert unavailable (%s): %s", url, exc.__class__.__name__)
        return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Remove page furniture (footer notice, page numbers) and re-join hyphenated line breaks."""
    text = re.sub(r"Sources:.*?All rights reserved\.", " ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*\d{1,2}\s*$", " ", text)                         # page numbers
    text = re.sub(r"(?m)^(Deacon|People|Reader|Celebrant):.*$", " ", text)   # liturgical responses
    text = re.sub(r"(?m)^\(St\. [A-Z][a-z]+ if .*\)\s*$", " ", text)         # rubric notes
    text = re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", text)                    # "anoth-\ner" -> "another"
    return " ".join(text.split())


def normalise_reference(ref: str) -> str:
    """'Gal 6:1-18' -> 'Galatians 6:1-18'; '2 Corinthians 13:(5-10)11-14' -> '2 Corinthians 13:5-14'."""
    ref = " ".join(ref.split())
    ref = re.sub(r"^((?:[123] )?)([A-Z][a-z]+)\.?(?= \d)",
                 lambda m: m.group(1) + ABBREVIATIONS.get(m.group(2), m.group(2)), ref)
    m = re.match(r"^(.+?) (\d+):(.+)$", ref)
    if not m or "(" not in ref:
        return ref.replace("–", "-")
    book, chapter, verses = m.groups()
    nums = [int(n) for n in re.findall(r"\d+", verses)]
    return f"{book} {chapter}:{min(nums)}-{max(nums)}" if nums else ref


def _marker(number: int) -> re.Pattern:
    """A printed verse number: preceded by space/punctuation, followed by a word or quote."""
    return re.compile(rf"(?:(?<=\s)|(?<=[.!?”’\"])){number}(?=\s?[“‘\"'A-Za-z(])")


def split_verses(reference: str, text: str) -> list[tuple[str, str]]:
    """Split running text into verses using the sequential verse numbers printed in the insert.

    The first verse of a reading is unnumbered. Prefer the next verse number and only skip
    ahead (omitted verses) when it is absent, so numbers inside the text ("planted 40 vines")
    are not read as verses. When a reading crosses into the next chapter, the insert prints
    the chapter number in place of verse 1.
    """
    m = re.search(r":\(?(\d+)", reference)
    first = int(m.group(1)) if m else 1
    chapters = [int(c) for c in re.findall(r"(\d+):", reference)]
    next_chapters = [c for c in chapters[1:] if c != chapters[0]] if chapters else []

    verses, label, current_no, pos = [], str(first), first, 0
    while True:
        found = None
        for candidate in range(current_no + 1, current_no + 16):
            hit = _marker(candidate).search(text, pos)
            if hit:
                found = (str(candidate), candidate, hit)
                break
        if not found and next_chapters:
            hit = _marker(next_chapters[0]).search(text, pos)
            if hit:
                found = (str(next_chapters.pop(0)), 1, hit)   # chapter number printed as verse 1
        if not found:
            break
        new_label, number, hit = found
        verses.append((label, text[pos:hit.start()].strip()))
        label, current_no, pos = new_label, number, hit.end()
    verses.append((label, text[pos:].strip()))
    return [(n, t) for n, t in verses if t]


def parse_insert(raw: str) -> list[Reading]:
    readings = []
    sections = list(SECTION_RE.finditer(raw))
    for i, sec in enumerate(sections):
        chunk = raw[sec.end(): sections[i + 1].start() if i + 1 < len(sections) else len(raw)]
        ref = REF_RE.search(chunk)
        if not ref:
            continue
        body = chunk[ref.end():]
        end = END_RE.search(body)
        body = _clean(body[: end.start()] if end else body)
        heading = sec.group(1)
        kind = ("Gospel" if "Gospel" in heading else "Old Testament" if "Old" in heading
                else "First Reading" if "First" in heading else "New Testament")
        reference = normalise_reference(ref.group(1))
        verses = split_verses(ref.group(1), body)
        if verses:
            readings.append(Reading(kind, reference, Passage(reference, verses)))
    return readings


# ---------------------------------------------------------------------------
# Choosing the sermon's reading(s)
# ---------------------------------------------------------------------------

def mentions(reference: str, sermon_text: str) -> int:
    """How often the preacher names the reading's book (spoken ordinals included)."""
    m = re.match(r"^([123]) ([A-Za-z ]+?) \d", reference) or re.match(r"^()([A-Za-z ]+?) \d", reference)
    if not m:
        return 0
    ordinal, book = m.group(1), m.group(2).strip().lower()
    text = " " + re.sub(r"[^a-z0-9 ]", " ", sermon_text.lower()) + " "
    forms = [f"{o} {book}" for o in ORDINALS[ordinal]] if ordinal else [book]
    return sum(len(re.findall(rf"\b{re.escape(f)}\b", text)) for f in forms)


def choose_readings(readings: list[Reading], sermon_text: str, minimum: int = 2, limit: int = 2) -> list[Reading]:
    scored = sorted(((mentions(r.reference, sermon_text), r) for r in readings), key=lambda x: -x[0])
    return [r for score, r in scored if score >= minimum][:limit]
