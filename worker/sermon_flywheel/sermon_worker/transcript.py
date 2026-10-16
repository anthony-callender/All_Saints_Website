"""Transcript acquisition + sermon extraction.

TranscriptProvider.get(video_id) -> path to a timed transcript (.json/.vtt/.tsv)
that the legacy loader understands. Providers (tried in order by ChainProvider):

  FileTranscriptProvider     an existing transcript you pass in (or in the work dir)
  CaptionTranscriptProvider  YouTube captions via yt-dlp (fast; auto-captions OK)
  WhisperTranscriptProvider  the legacy approach: download audio + local Whisper CLI

Then the legacy liturgical-cue detector finds the sermon inside the full service,
and only that span is cleaned and sent onward.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import legacy

log = logging.getLogger(__name__)
MIN_SERMON_WORDS = 300


class TranscriptUnavailable(RuntimeError):
    """No usable transcript: never publish without one."""


@dataclass
class Sermon:
    text: str
    start_time: str
    end_time: str
    confidence: str
    source: str
    notes: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class TranscriptProvider(Protocol):
    name: str

    def get(self, video_id: str) -> Path: ...


class FileTranscriptProvider:
    name = "file"

    def __init__(self, search_dirs: list[Path], explicit: Path | None = None):
        self.search_dirs = search_dirs
        self.explicit = explicit

    def get(self, video_id: str) -> Path:
        if self.explicit:
            if not self.explicit.exists():
                raise TranscriptUnavailable(f"Transcript file not found: {self.explicit}")
            return self.explicit
        for d in self.search_dirs:
            for pattern in (f"{video_id}*.json", f"{video_id}*.vtt", f"{video_id}*.tsv"):
                hits = sorted(d.glob(pattern)) if d.exists() else []
                if hits:
                    return hits[0]
        raise TranscriptUnavailable("No local transcript file")


class CaptionTranscriptProvider:
    """YouTube captions (manual or automatic) through yt-dlp. No API key needed."""

    name = "youtube-captions"

    def __init__(self, work_dir: Path):
        self.work_dir = work_dir

    def get(self, video_id: str) -> Path:
        try:
            import yt_dlp
        except ImportError as exc:
            raise TranscriptUnavailable("yt-dlp not installed") from exc
        self.work_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "outtmpl": str(self.work_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        except Exception as exc:  # yt-dlp raises many types; treat all as "unavailable"
            raise TranscriptUnavailable(f"Captions unavailable: {exc.__class__.__name__}") from None
        hits = sorted(self.work_dir.glob(f"{video_id}*.vtt"))
        if not hits:
            raise TranscriptUnavailable("Captions disabled or not yet generated for this video")
        return hits[0]


class WhisperTranscriptProvider:
    """Legacy AllSaints_Agent method: yt-dlp audio + local Whisper (slow on CPU)."""

    name = "whisper"

    def __init__(self, work_dir: Path, model: str = "base"):
        self.work_dir = work_dir
        self.model = model

    def get(self, video_id: str) -> Path:
        if not shutil.which("whisper"):
            raise TranscriptUnavailable("Whisper CLI not installed")
        try:
            audio = legacy.download_youtube_audio(f"https://www.youtube.com/watch?v={video_id}")
        except legacy.LegacyError as exc:
            raise TranscriptUnavailable(f"Audio download failed: {exc}") from None
        self.work_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        cmd = ["whisper", str(audio), "--model", self.model, "--language", "English",
               "--output_format", "json", "--verbose", "False", "--output_dir", str(self.work_dir)]
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, timeout=4 * 3600)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise TranscriptUnavailable(f"Whisper failed: {exc.__class__.__name__}") from None
        out = self.work_dir / f"{audio.stem}.json"
        if not out.exists():
            raise TranscriptUnavailable("Whisper produced no transcript")
        return out


class ChainProvider:
    name = "chain"

    def __init__(self, providers: list):
        self.providers = providers

    def get(self, video_id: str) -> tuple[Path, str]:
        reasons = []
        for provider in self.providers:
            try:
                return provider.get(video_id), provider.name
            except TranscriptUnavailable as exc:
                reasons.append(f"{provider.name}: {exc}")
        raise TranscriptUnavailable("; ".join(reasons) or "no providers configured")


# ---------------------------------------------------------------------------
# Cleaning + sermon extraction
# ---------------------------------------------------------------------------

NOISE_RE = re.compile(r"\[(?:music|applause|laughter|clears throat|inaudible|__)\]", re.I)


def merge_rolling(texts: list[str]) -> str:
    """Join caption cues, removing the repeated overlap typical of YouTube
    auto-captions (each cue repeats the tail of the previous one)."""
    out: list[str] = []
    for text in texts:
        words = NOISE_RE.sub(" ", text).split()
        if not words:
            continue
        max_k = min(len(words), len(out), 40)
        overlap = 0
        for k in range(max_k, 0, -1):
            if out[-k:] == words[:k]:
                overlap = k
                break
        out.extend(words[overlap:])
    return " ".join(out)


def extract_sermon(transcript_path: Path, source: str, bounds: tuple[str, str] | None = None) -> Sermon:
    """Find the sermon inside the service. `bounds` (start, end) from a human review override detection."""
    try:
        segments = legacy.load_segments(transcript_path)
    except legacy.LegacyError as exc:
        raise TranscriptUnavailable(f"Unreadable transcript: {exc}") from None
    if not segments:
        raise TranscriptUnavailable("Transcript is empty")

    notes = []
    if bounds:
        start_time, end_time, confidence = bounds[0], bounds[1], "reviewed"
    else:
        detection = legacy.detect_bounds(segments)
        start_time, end_time, confidence = detection.start_time, detection.end_time, detection.confidence
        if confidence == "low":
            # e.g. a Good Friday liturgy or Lessons & Carols with no sermon: never guess.
            raise TranscriptUnavailable(
                f"Sermon boundaries are low-confidence ({detection.start_reason} {detection.end_reason}); "
                "not publishing. Review the service and supply start/end times.")
        if confidence == "medium":
            notes.append(f"Sermon boundaries are medium-confidence ({start_time}-{end_time}); please listen to check.")
    start, end = legacy.seconds(start_time), legacy.seconds(end_time)
    text = merge_rolling([s.text for s in segments if start <= s.start <= end])
    if len(text.split()) < MIN_SERMON_WORDS:
        raise TranscriptUnavailable(f"Sermon transcript too short ({len(text.split())} words); not publishing.")
    return Sermon(text, start_time, end_time, confidence, source, notes)
