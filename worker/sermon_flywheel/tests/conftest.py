"""Shared fixtures. No test touches the network or spends API credits."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).parent / "fixtures"

SERMON_TEXT = (
    "Today we turn to Second Corinthians chapter 13. Paul tells the church to examine yourselves to see "
    "whether you are in the faith. " * 40
    + "So may we be conformed to the gospel of Jesus Christ, by his grace and not by our strength. Amen."
)


@pytest.fixture
def vtt_path(tmp_path: Path) -> Path:
    """A small YouTube-style rolling-caption VTT containing liturgy + a sermon + the Creed."""
    cues = [
        (1700, "This is the Gospel of the Lord."),
        (1705, "Praise to you Lord Christ."),
        (1800, "You may be seated."),
        (1801, "You may be seated. Good morning everyone."),
    ]
    t = 1810
    for sentence in SERMON_TEXT.split(". "):
        cues.append((t, sentence.strip() + "."))
        t += 6
    cues.append((t + 400, "Let us stand and confess our faith. We believe in one God."))
    def ts(sec: int) -> str:
        return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}.000"

    lines = ["WEBVTT", ""]
    for start, text in cues:
        lines += [f"{ts(start)} --> {ts(start + 5)}", text, ""]
    path = tmp_path / "abcdefghijk.en.vtt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture
def notes_json() -> str:
    return (FIXTURES / "sermon_notes.json").read_text(encoding="utf-8")


@pytest.fixture
def playlist_response() -> dict:
    return json.loads((FIXTURES / "playlist_items.json").read_text(encoding="utf-8"))
