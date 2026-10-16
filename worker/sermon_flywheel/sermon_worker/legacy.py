"""Adapter over the existing AllSaints_Agent scripts (imported, never modified).

Reused as-is:
  detect_sermon_bounds.detect / load_segments   sermon start/end from liturgical cues
  process_sermon_audio.build_audio / download_youtube_audio / seconds
  form_to_packet.parse_form                      clergy sermon-form parsing
  discover_work.fetch_youtube_rss / infer_service_date / Video

The legacy modules use flat imports (``from weekly_packet import ROOT``), so the
automation directory is put on sys.path once. Legacy code signals errors with
SystemExit; this adapter converts that into LegacyError.
"""
from __future__ import annotations

import importlib
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from .config import LEGACY_AGENT_DIR

AUTOMATION_DIR = LEGACY_AGENT_DIR / "automation"


class LegacyError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def module(name: str) -> ModuleType:
    if not AUTOMATION_DIR.is_dir():
        raise LegacyError(f"AllSaints_Agent not found at {AUTOMATION_DIR}")
    if str(AUTOMATION_DIR) not in sys.path:
        sys.path.insert(0, str(AUTOMATION_DIR))
    return importlib.import_module(name)


def call(module_name: str, func: str, *args, **kwargs):
    try:
        return getattr(module(module_name), func)(*args, **kwargs)
    except SystemExit as exc:  # legacy scripts exit on errors
        raise LegacyError(str(exc)) from None


def load_segments(path: Path) -> list:
    return call("detect_sermon_bounds", "load_segments", Path(path))


def detect_bounds(segments: list):
    return call("detect_sermon_bounds", "detect", segments)


def seconds(value) -> float | None:
    return call("process_sermon_audio", "seconds", value)


def download_youtube_audio(url: str) -> Path:
    return call("process_sermon_audio", "download_youtube_audio", url)


def build_audio(job: dict, source: Path, output_dir: Path, filter_mode: str = "clean") -> Path:
    ffmpeg = call("process_sermon_audio", "local_ffmpeg")
    return call("process_sermon_audio", "build_audio", job, Path(source), ffmpeg, Path(output_dir), filter_mode)


def parse_form(text: str) -> dict:
    return call("form_to_packet", "parse_form", text)


def fetch_youtube_rss(channel_id: str, limit: int) -> list:
    return call("discover_work", "fetch_youtube_rss", channel_id, limit)


def infer_service_date(video_id: str, title: str, upload_date: str) -> str:
    """Legacy rule: Sunday services uploaded on Monday belong to the previous Sunday."""
    Video = module("discover_work").Video
    service_date, _reason = call("discover_work", "infer_service_date", Video(title=title, url="", video_id=video_id, upload_date=upload_date))
    return service_date
