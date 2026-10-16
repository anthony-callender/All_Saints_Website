"""WordPress REST client (Application Password auth) + pure payload builder."""
from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import requests

from . import PIPELINE_VERSION

log = logging.getLogger(__name__)


class WordPressAuthError(RuntimeError):
    """Credentials rejected: fail loudly, stop the run."""


class WordPressError(RuntimeError):
    """A write failed: the sermon is NOT marked complete."""


class DuplicateSermon(RuntimeError):
    pass


def build_sermon_payload(*, title: str, content: str, preacher: str | None, scripture_references: list[str],
                         excerpt: str | None, video_id: str, video_url: str, service_date: str, published_at: str,
                         transcript: str, status: str, audio_attachment_id: int | None = None,
                         featured_media: int | None = None) -> dict:
    meta = {
        "asc_sermon_date": service_date,
        "asc_preacher": preacher or "",
        "asc_scripture_references": list(scripture_references),
        "asc_youtube_video_id": video_id,
        "asc_youtube_url": video_url,
        "asc_source_published_at": published_at,
        "asc_transcript": transcript,
        "asc_pipeline_version": PIPELINE_VERSION,
    }
    if audio_attachment_id:
        meta["asc_audio_attachment_id"] = audio_attachment_id
    payload = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": status,
        "date": f"{service_date}T11:00:00" if service_date else None,
        "meta": meta,
    }
    if featured_media:
        payload["featured_media"] = featured_media
    return {k: v for k, v in payload.items() if v is not None}


class WordPressClient:
    def __init__(self, base_url: str, username: str, app_password: str, session: requests.Session | None = None):
        if not (base_url and username and app_password):
            raise WordPressAuthError("WP_BASE_URL, WP_USERNAME and WP_APPLICATION_PASSWORD are required.")
        if base_url.startswith("http://") and not any(h in base_url for h in ("localhost", "127.0.0.1", ".ddev.site", ".test")):
            raise WordPressAuthError("Refusing to send credentials over plain HTTP to a non-local host; use HTTPS.")
        self.base = base_url.rstrip("/") + "/wp-json"
        self.session = session or requests.Session()
        self.session.auth = (username, app_password)
        self.session.headers["User-Agent"] = PIPELINE_VERSION

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            resp = self.session.request(method, self.base + path, timeout=kwargs.pop("timeout", 60), **kwargs)
        except requests.RequestException as exc:
            raise WordPressError(f"{method} {path} failed: {exc.__class__.__name__}") from None
        if resp.status_code in (401, 403):
            raise WordPressAuthError(f"WordPress rejected the credentials ({resp.status_code}) for {path}.")
        return resp

    def verify(self) -> dict:
        resp = self._request("GET", "/wp/v2/users/me", params={"context": "edit"})
        if resp.status_code != 200:
            raise WordPressError(f"Auth check failed: HTTP {resp.status_code}")
        user = resp.json()
        if "edit_posts" not in (user.get("capabilities") or {}):
            raise WordPressAuthError("Integration user cannot edit posts.")
        return {"id": user.get("id"), "name": user.get("name")}

    def sermon_exists(self, video_id: str) -> dict:
        resp = self._request("GET", "/asc/v1/sermons/exists", params={"youtube_video_id": video_id})
        if resp.status_code != 200:
            raise WordPressError(f"Duplicate check failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def upload_media(self, path: Path, title: str = "") -> int:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            resp = self._request("POST", "/wp/v2/media", data=fh, timeout=600, headers={
                "Content-Type": mime,
                "Content-Disposition": f'attachment; filename="{path.name}"',
            })
        if resp.status_code not in (200, 201):
            raise WordPressError(f"Media upload failed: HTTP {resp.status_code} {resp.text[:200]}")
        media_id = int(resp.json()["id"])
        if title:
            self._request("POST", f"/wp/v2/media/{media_id}", json={"title": title})
        return media_id

    def create_sermon(self, payload: dict) -> dict:
        resp = self._request("POST", "/wp/v2/sermons", json=payload)
        if resp.status_code == 409:
            raise DuplicateSermon(resp.json().get("message", "duplicate"))
        if resp.status_code not in (200, 201):
            raise WordPressError(f"Create sermon failed: HTTP {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        return {"id": body["id"], "link": body.get("link"), "status": body.get("status"),
                "edit_link": f"{self.base.removesuffix('/wp-json')}/wp-admin/post.php?post={body['id']}&action=edit"}
