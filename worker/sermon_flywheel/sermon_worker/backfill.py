"""Backfill: find past livestreams with no sermon on the site and run the flywheel for them.

    python -m sermon_worker.cli backfill --since 2025-05-04 [--plan-only] [--publish] [--link-existing]

Matching is by YouTube video ID, and by service date for sermons migrated from the
old site (which carry no video ID). Service dates come from the stream's actual start
time (America/New_York), which is reliable for weekday services too.

Human review decisions live in data/sermon_overrides.json:
  skip            services with no sermon (e.g. Good Friday liturgy, Lessons & Carols)
  start/end_time  reviewed sermon boundaries when automatic detection was wrong
  title/preacher/scripture_references/audio_file   clergy-supplied facts
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import PROJECT_ROOT
from .wordpress import WordPressClient
from .youtube import Video

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
OVERRIDES = Path(__file__).resolve().parent / "data" / "sermon_overrides.json"
NOT_SERMON_SERVICES = ("celebration of life", "funeral", "memorial", "wedding", "ordination", "installation")
MIN_SERVICE_MINUTES = 40


@dataclass
class Stream:
    video_id: str
    title: str
    started: datetime
    minutes: int

    @property
    def service_date(self) -> str:
        return self.started.date().isoformat()


@dataclass
class Decision:
    stream: Stream
    action: str          # process | skip | exists | link
    reason: str = ""
    post_id: int | None = None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def list_streams(channel_id: str, limit: int = 120) -> list[Stream]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "ignoreerrors": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/streams", download=False)
    streams = []
    for e in (info or {}).get("entries") or []:
        if not e or not (e.get("release_timestamp") or e.get("timestamp")):
            continue
        started = datetime.fromtimestamp(e.get("release_timestamp") or e["timestamp"], ET)
        streams.append(Stream(e["id"], e.get("title", ""), started, int((e.get("duration") or 0) // 60)))
    return streams


def site_sermons(wp: WordPressClient) -> list[dict]:
    sermons, page = [], 1
    while True:
        resp = wp._request("GET", "/wp/v2/sermons", params={
            "context": "edit", "status": "publish,draft,pending,future,private", "per_page": 100, "page": page,
            "_fields": "id,status,title,meta"})
        if resp.status_code != 200:
            break
        batch = resp.json()
        sermons += [{"id": s["id"], "status": s["status"], "title": s["title"]["raw"],
                     "date": s["meta"].get("asc_sermon_date", ""), "video_id": s["meta"].get("asc_youtube_video_id", "")}
                    for s in batch]
        if len(batch) < 100:
            break
        page += 1
    return sermons


def load_overrides(path: Path = OVERRIDES) -> dict:
    return json.loads(path.read_text(encoding="utf-8")).get("videos", {}) if path.exists() else {}


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

def easter(year: int) -> date:
    """Western (Gregorian) Easter date — anonymous Gregorian algorithm."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lv = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lv) // 451
    month = (h + lv - 7 * m + 114) // 31
    return date(year, month, (h + lv - 7 * m + 114) % 31 + 1)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def clean_title(title: str, service_date: str) -> str:
    """Tidy YouTube service titles ("18h", "2026i", missing year, wrong ordinal) using the calendar."""
    d = date.fromisoformat(service_date)
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(r"\b(\d+)h\b", r"\1th", t)                               # "18h Sunday" -> "18th Sunday"
    t = re.sub(r"\b(20\d\d)[a-z]\b", r"\1", t)                           # "2026i" -> "2026"
    t = re.sub(r"\bSunday After\b", "Sunday after", t)
    m = re.match(r"^\d+(?:st|nd|rd|th) Sunday after Pentecost", t, re.I)
    if m:
        weeks = (d - (easter(d.year) + timedelta(days=49))).days // 7
        if weeks >= 1:
            t = re.sub(r"^\d+(?:st|nd|rd|th)", ordinal(weeks), t)
    if not re.search(r"\b20\d\d\b|\b\d{1,2}-\d{1,2}-\d{2}\b", t):
        t = f"{t} {d.year}"
    return t


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def plan(streams: list[Stream], sermons: list[dict], overrides: dict, since: str) -> list[Decision]:
    by_video = {s["video_id"]: s for s in sermons if s["video_id"]}
    by_date: dict[str, list[dict]] = {}
    for s in sermons:
        by_date.setdefault(s["date"], []).append(s)

    decisions = []
    for st in sorted(streams, key=lambda s: s.started):
        if st.service_date < since:
            continue
        title = st.title.lower()
        override = overrides.get(st.video_id, {})
        if st.video_id in by_video:
            decisions.append(Decision(st, "exists", f"post {by_video[st.video_id]['id']}"))
        elif override.get("skip"):
            decisions.append(Decision(st, "skip", override["skip"]))
        elif any(w in title for w in NOT_SERMON_SERVICES):
            decisions.append(Decision(st, "skip", "special or pastoral service, not a parish sermon"))
        elif st.minutes < MIN_SERVICE_MINUTES:
            decisions.append(Decision(st, "skip", f"only {st.minutes} min (partial or empty stream)"))
        elif by_date.get(st.service_date):
            unlinked = [s for s in by_date[st.service_date] if not s["video_id"]]
            if unlinked:
                decisions.append(Decision(st, "link", f"migrated sermon '{unlinked[0]['title']}'", unlinked[0]["id"]))
            else:
                decisions.append(Decision(st, "exists", "sermon on this date"))
        else:
            decisions.append(Decision(st, "process", "no sermon on the site"))
    # One video per migrated sermon: keep the first (e.g. Easter Vigil vs. Easter Day share no date).
    seen = set()
    for d in decisions:
        if d.action == "link":
            if d.post_id in seen:
                d.action, d.reason = "exists", "sermon on this date already linked"
            seen.add(d.post_id)
    return decisions


def metadata_for(st: Stream, override: dict) -> dict:
    meta = {"service_date": st.service_date, "service_title": st.title, "title": clean_title(st.title, st.service_date)}
    for key in ("title", "preacher", "scripture_references", "start_time", "end_time", "note"):
        if override.get(key):
            meta[key] = override[key]
    if override.get("audio_file"):
        meta["audio_file"] = str((PROJECT_ROOT / override["audio_file"]).resolve())
    return meta


def to_video(st: Stream) -> Video:
    return Video(st.video_id, st.title, st.started.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"))
