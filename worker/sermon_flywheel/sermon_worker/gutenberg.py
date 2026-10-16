"""Deterministic Gutenberg block markup.

The model never writes HTML. Every value is escaped and placed into ordinary
core blocks (heading, paragraph, list, quote) that an editor can change afterwards.
"""
from __future__ import annotations

import html
import json

from .llm import SermonNotes
from .scripture import ESV_NOTICE, Passage


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _block(name: str, inner: str, attrs: dict | None = None) -> str:
    a = " " + json.dumps(attrs, separators=(",", ":")) if attrs else ""
    return f"<!-- wp:{name}{a} -->\n{inner}\n<!-- /wp:{name} -->"


def heading(text: str, level: int = 2) -> str:
    attrs = None if level == 2 else {"level": level}
    return _block("heading", f'<h{level} class="wp-block-heading">{_esc(text)}</h{level}>', attrs)


def paragraph(text: str) -> str:
    return _block("paragraph", f"<p>{_esc(text)}</p>")


def scripture_blocks(passages: list[Passage], title: str = "Scripture") -> str:
    """The parish's format: each passage as a quote with verse numbers, then the ESV notice."""
    if not passages:
        return ""
    out = [heading(title)]
    for p in passages:
        verses = "".join(_block("paragraph", f"<p><sup>{_esc(n)}</sup> {_esc(t)}</p>") for n, t in p.verses)
        out.append(_block("quote", f'<blockquote class="wp-block-quote">{verses}<cite>{_esc(p.reference)} (ESV)</cite></blockquote>'))
    out.append(_block("paragraph", f'<p class="has-small-font-size">{_esc(ESV_NOTICE)}</p>', {"fontSize": "small"}))
    return "\n\n".join(out)


def sermon_blocks(notes: SermonNotes) -> str:
    """Optional AI sermon notes: Summary → Key Ideas → Closing Takeaway."""
    out = [heading("Sermon Notes"), paragraph(notes.summary)]
    for point in notes.key_points:
        out += [heading(point.heading, 3), paragraph(point.body)]
    if notes.closing_takeaway:
        out += [heading("Closing Takeaway", 3), paragraph(notes.closing_takeaway)]
    return "\n\n".join(out)
