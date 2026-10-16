"""Optional sermon MP3, produced by the legacy agent's proven ffmpeg chain.

Audio is an enhancement: any failure returns None and the pipeline continues.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import legacy

log = logging.getLogger(__name__)


def make_sermon_mp3(video_url: str, start_time: str, end_time: str, meta: dict, output_dir: Path,
                    source_file: Path | None = None) -> Path | None:
    downloaded = None
    try:
        source = source_file or legacy.download_youtube_audio(video_url)
        if not source_file:
            downloaded = Path(source)  # full-service recording; removed once the sermon is cut
        job = {
            "service_date": meta.get("service_date", ""),
            "sermon_title": meta.get("title", ""),
            "service_title": meta.get("service_title", ""),
            "preacher": meta.get("preacher") or "",
            "start_time": start_time,
            "end_time": end_time,
        }
        return legacy.build_audio(job, Path(source), output_dir, "clean")
    except (legacy.LegacyError, OSError, Exception) as exc:  # noqa: BLE001 - audio must never stop the pipeline
        log.warning("Audio skipped: %s", str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__)
        return None
    finally:
        if downloaded and downloaded.exists():
            downloaded.unlink(missing_ok=True)
