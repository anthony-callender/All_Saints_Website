"""Scripture passage text from the ESV API (https://api.esv.org), matching the
parish's existing sermon posts ("<reference> (ESV)" followed by the verses).

Optional: only used when ESV_API_KEY is set. Without it, posts show the
reference only. Never invents text: any failure means "reference only".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)
API = "https://api.esv.org/v3/passage/text/"
ESV_NOTICE = ("Scripture quotations are from the ESV® Bible (The Holy Bible, English Standard Version®), "
              "© 2001 by Crossway, a publishing ministry of Good News Publishers. Used by permission. All rights reserved.")


@dataclass
class Passage:
    reference: str
    verses: list[tuple[str, str]]  # (verse number, text)


def parse_passage(reference: str, text: str) -> Passage:
    """Split ESV API text like '[3] Blessed be… [4] to an inheritance…' into verses."""
    parts = re.split(r"\[(\d{1,3})\]\s*", text.strip())
    verses = [(parts[i], " ".join(parts[i + 1].split())) for i in range(1, len(parts) - 1, 2) if parts[i + 1].strip()]
    return Passage(reference, verses)


def fetch_passage(reference: str, api_key: str, session: requests.Session | None = None) -> Passage | None:
    if not api_key or not reference:
        return None
    session = session or requests.Session()
    try:
        resp = session.get(API, timeout=20, headers={"Authorization": f"Token {api_key}"}, params={
            "q": reference,
            "include-headings": "false",
            "include-footnotes": "false",
            "include-verse-numbers": "true",
            "include-short-copyright": "false",
            "include-passage-references": "false",
        })
    except requests.RequestException as exc:
        log.warning("ESV API unavailable: %s", exc.__class__.__name__)
        return None
    if resp.status_code != 200:
        log.warning("ESV API returned %s for %r", resp.status_code, reference)
        return None
    passages = resp.json().get("passages") or []
    if not passages:
        return None
    passage = parse_passage(reference, passages[0])
    return passage if passage.verses else None
