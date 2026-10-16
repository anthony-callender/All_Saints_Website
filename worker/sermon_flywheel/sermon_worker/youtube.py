"""YouTube upload detection.

Primary: official YouTube Data API v3 — channel → uploads playlist → playlistItems
(2 quota units per sync; no search.list calls).
Fallback (no API key): the legacy agent's public RSS feed reader.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from . import legacy

log = logging.getLogger(__name__)
API = "https://www.googleapis.com/youtube/v3"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(RuntimeError):
    pass


@dataclass
class Video:
    video_id: str
    title: str
    published_at: str  # ISO 8601
    description: str = ""
    thumbnail_url: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def upload_date(self) -> str:
        return self.published_at[:10]


def is_valid_video_id(value: str) -> bool:
    return bool(VIDEO_ID_RE.match(value or ""))


def parse_uploads_playlist(channels_response: dict) -> str:
    items = channels_response.get("items") or []
    if not items:
        raise YouTubeError("Channel not found (check YOUTUBE_CHANNEL_ID).")
    try:
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except KeyError as exc:
        raise YouTubeError("Channel response has no uploads playlist.") from exc


def parse_playlist_items(response: dict) -> list[Video]:
    videos = []
    for item in response.get("items") or []:
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        video_id = details.get("videoId") or (snippet.get("resourceId") or {}).get("videoId", "")
        if not is_valid_video_id(video_id):
            continue
        if snippet.get("title") in ("Private video", "Deleted video"):
            continue
        thumbs = snippet.get("thumbnails") or {}
        thumb = next((thumbs[k]["url"] for k in ("maxres", "standard", "high", "medium", "default") if k in thumbs), "")
        videos.append(Video(
            video_id=video_id,
            title=snippet.get("title", ""),
            published_at=details.get("videoPublishedAt") or snippet.get("publishedAt", ""),
            description=snippet.get("description", ""),
            thumbnail_url=thumb,
        ))
    return videos


def parse_video(response: dict) -> Video:
    items = response.get("items") or []
    if not items:
        raise YouTubeError("Video not found or not public.")
    snippet = items[0]["snippet"]
    thumbs = snippet.get("thumbnails") or {}
    thumb = next((thumbs[k]["url"] for k in ("maxres", "standard", "high") if k in thumbs), "")
    return Video(items[0]["id"], snippet.get("title", ""), snippet.get("publishedAt", ""), snippet.get("description", ""), thumb)


def looks_like_service(video: Video) -> bool:
    """Only full services contain a sermon. Mirrors the legacy discovery heuristic."""
    title = video.title.lower()
    return any(w in title for w in ("sunday", "service", "livestream", "eucharist", "easter", "christmas",
                                    "pentecost", "advent", "lent", "epiphany", "trinity", "proper", "vigil", "ash wednesday"))


class YouTubeClient:
    def __init__(self, api_key: str, channel_id: str, session: requests.Session | None = None):
        self.api_key = api_key
        self.channel_id = channel_id
        self.session = session or requests.Session()

    def _get(self, path: str, **params) -> dict:
        params["key"] = self.api_key
        try:
            resp = self.session.get(f"{API}/{path}", params=params, timeout=20)
        except requests.RequestException as exc:
            raise YouTubeError(f"YouTube API request failed: {exc.__class__.__name__}") from None
        if resp.status_code != 200:
            reason = (resp.json().get("error") or {}).get("message", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
            raise YouTubeError(f"YouTube API {path} returned {resp.status_code}: {reason}")
        return resp.json()

    def recent_uploads(self, limit: int = 10) -> list[Video]:
        if not self.api_key:
            log.info("YOUTUBE_API_KEY not set; using the legacy RSS feed reader")
            return [
                Video(v.video_id, v.title, v.upload_date + "T00:00:00Z")
                for v in legacy.fetch_youtube_rss(self.channel_id, limit)
            ]
        uploads = parse_uploads_playlist(self._get("channels", part="contentDetails", id=self.channel_id))
        page = self._get("playlistItems", part="snippet,contentDetails", playlistId=uploads, maxResults=min(50, limit))
        return parse_playlist_items(page)[:limit]

    def get_video(self, video_id: str) -> Video:
        if not is_valid_video_id(video_id):
            raise YouTubeError(f"Not a YouTube video ID: {video_id!r}")
        if not self.api_key:
            return self._get_video_ytdlp(video_id)
        return parse_video(self._get("videos", part="snippet", id=video_id))

    @staticmethod
    def _get_video_ytdlp(video_id: str) -> Video:
        try:
            import yt_dlp
        except ImportError as exc:
            raise YouTubeError("Set YOUTUBE_API_KEY or install yt-dlp.") from exc
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        date = info.get("upload_date") or ""
        published = f"{date[:4]}-{date[4:6]}-{date[6:8]}T00:00:00Z" if len(date) == 8 else ""
        return Video(video_id, info.get("title", ""), published, info.get("description", ""), info.get("thumbnail", ""))
