"""Command line interface.

  python -m sermon_worker.cli check
  python -m sermon_worker.cli sync --limit 3 [--dry-run]
  python -m sermon_worker.cli process VIDEO_ID [--dry-run] [--form FILE] [--transcript FILE]
                                               [--title T] [--preacher P] [--scripture REF ...] [--no-audio]
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from . import PIPELINE_VERSION, legacy
from .config import LEGACY_AGENT_DIR, Settings
from .lectionary import fetch_insert_text, insert_url_for, parse_insert
from .llm import OpenAIStructurer
from .pipeline import Pipeline, Result
from .transcript import CaptionTranscriptProvider, ChainProvider, FileTranscriptProvider, WhisperTranscriptProvider
from .wordpress import WordPressAuthError, WordPressClient, WordPressError
from .youtube import YouTubeClient, YouTubeError, looks_like_service

log = logging.getLogger("sermon_worker")


def readings_for_date(service_date: str) -> list:
    """The day's appointed readings (with ESV text) from the ACNA lectionary insert, if mapped."""
    url = insert_url_for(service_date)
    text = fetch_insert_text(url) if url else None
    return parse_insert(text) if text else []


def build_pipeline(settings: Settings, args, need_wp: bool) -> Pipeline:
    work = settings.work_dir
    providers = [
        FileTranscriptProvider([work / "transcripts", work / "captions"], getattr(args, "transcript", None)),
        CaptionTranscriptProvider(work / "captions"),
    ]
    if getattr(args, "whisper", False):
        providers.append(WhisperTranscriptProvider(work / "whisper"))
    structurer = None
    if getattr(args, "notes", False) or settings.include_notes:
        if settings.openai_api_key:
            structurer = OpenAIStructurer(settings.openai_api_key, settings.sermon_model)
        else:
            print("! --notes needs OPENAI_API_KEY; posting without AI notes.")
    wp = None
    if settings.wp_base_url or need_wp:
        wp = WordPressClient(settings.wp_base_url, settings.wp_username, settings.wp_application_password)
    return Pipeline(
        transcripts=ChainProvider(providers),
        structurer=structurer,
        esv_api_key=settings.esv_api_key,
        readings_for=readings_for_date,
        wordpress=wp,
        work_dir=work,
        post_status=settings.post_status,
        with_audio=not getattr(args, "no_audio", False),
        audio_source=getattr(args, "audio_source", None),
        audio_file=getattr(args, "audio_file", None),
    )


def metadata_from_args(args) -> dict:
    meta: dict = {}
    if getattr(args, "form", None):
        form = legacy.parse_form(Path(args.form).read_text(encoding="utf-8"))
        meta.update({
            "title": form.get("sermon_title") or None,
            "preacher": form.get("preacher") or None,
            "scripture_references": [form["scripture_reference"]] if form.get("scripture_reference") else [],
            "service_date": form.get("service_date") or None,
            "service_title": form.get("service_title") or None,
        })
    for key in ("title", "preacher", "service_date"):
        if getattr(args, key, None):
            meta[key] = getattr(args, key)
    if getattr(args, "scripture", None):
        meta["scripture_references"] = args.scripture
    return {k: v for k, v in meta.items() if v}


def print_result(result: Result, verbose: bool = False) -> None:
    icon = {"created": "✔", "skipped": "↷", "dry_run": "◌", "failed": "✘"}.get(result.status, "?")
    print(f"{icon} {result.video_id}  {result.status.upper()}  {result.reason}")
    if result.post.get("link") or result.post.get("edit_link"):
        print(f"    view: {result.post.get('link')}\n    edit: {result.post.get('edit_link')}")
    for note in result.review:
        print(f"    review: {note}")
    if verbose and result.payload:
        shown = {**result.payload, "content": result.payload["content"][:1500] + ("…" if len(result.payload["content"]) > 1500 else ""),
                 "meta": {**result.payload["meta"], "asc_transcript": f"<{len(result.payload['meta']['asc_transcript'].split())} words>"}}
        print(json.dumps(shown, indent=2, ensure_ascii=False))


def cmd_check(settings: Settings, args) -> int:
    ok = True
    print(f"{PIPELINE_VERSION}\n\nConfiguration:")
    for k, v in settings.describe().items():
        print(f"  {k:26} {v}")
    print("\nLegacy agent:")
    try:
        legacy.module("detect_sermon_bounds")
        legacy.module("process_sermon_audio")
        print(f"  AllSaints_Agent           ok ({LEGACY_AGENT_DIR})")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  AllSaints_Agent           FAILED: {exc}")
    for tool in ("ffmpeg", "yt-dlp", "whisper"):
        print(f"  {tool:26} {'found' if shutil.which(tool) else 'missing (optional)' if tool == 'whisper' else 'missing'}")
    print("\nWordPress:")
    try:
        wp = WordPressClient(settings.wp_base_url, settings.wp_username, settings.wp_application_password)
        user = wp.verify()
        print(f"  auth                      ok (user #{user['id']} {user['name']})")
        wp.sermon_exists("aaaaaaaaaaa")
        print("  sermon REST support       ok (/asc/v1/sermons/exists)")
    except (WordPressAuthError, WordPressError) as exc:
        ok = False
        print(f"  FAILED: {exc}")
    print("\nYouTube:")
    try:
        videos = YouTubeClient(settings.youtube_api_key, settings.youtube_channel_id).recent_uploads(3)
        source = "Data API" if settings.youtube_api_key else "RSS fallback"
        print(f"  recent uploads            ok via {source}: " + "; ".join(f"{v.video_id} {v.title}" for v in videos))
    except (YouTubeError, legacy.LegacyError, OSError) as exc:
        ok = False
        print(f"  FAILED: {exc}")
    print("\nPost format: audio post (title, preacher, scripture, MP3, YouTube link)")
    print("  scripture text:", "ESV API" if settings.esv_api_key else "reference only (set ESV_API_KEY for passage text)")
    print("  AI sermon notes:", f"on, {settings.sermon_model}" if settings.include_notes and settings.openai_api_key
          else "off (use --notes; needs OPENAI_API_KEY)")
    return 0 if ok else 1


def cmd_process(settings: Settings, args) -> int:
    pipeline = build_pipeline(settings, args, need_wp=not args.dry_run)
    video = YouTubeClient(settings.youtube_api_key, settings.youtube_channel_id).get_video(args.video_id)
    result = pipeline.process(video, metadata_from_args(args), dry_run=args.dry_run)
    print_result(result, verbose=args.dry_run or args.verbose)
    return 0 if result.status in ("created", "skipped", "dry_run") else 1


def cmd_sync(settings: Settings, args) -> int:
    pipeline = build_pipeline(settings, args, need_wp=not args.dry_run)
    videos = YouTubeClient(settings.youtube_api_key, settings.youtube_channel_id).recent_uploads(max(args.limit * 3, 10))
    services = [v for v in videos if looks_like_service(v)][: args.limit]
    print(f"Checking {len(services)} recent service video(s)")
    failures = 0
    for video in services:
        result = pipeline.process(video, dry_run=args.dry_run)
        print_result(result, verbose=args.verbose)
        failures += result.status == "failed"
    return 1 if failures else 0


def cmd_backfill(settings: Settings, args) -> int:
    from . import backfill

    wp = WordPressClient(settings.wp_base_url, settings.wp_username, settings.wp_application_password)
    print("Listing livestreams and site sermons...")
    streams = backfill.list_streams(settings.youtube_channel_id, args.limit)
    overrides = backfill.load_overrides()
    decisions = backfill.plan(streams, backfill.site_sermons(wp), overrides, args.since)
    for d in decisions:
        print(f"  {d.stream.service_date} {d.stream.video_id} {d.action:8} {d.stream.title[:44]:44} {d.reason}")
    counts = {a: sum(d.action == a for d in decisions) for a in ("process", "link", "skip", "exists")}
    print("Plan:", ", ".join(f"{v} {k}" for k, v in counts.items()))
    if args.plan_only:
        return 0

    if args.link_existing:
        for d in (d for d in decisions if d.action == "link"):
            resp = wp._request("POST", f"/wp/v2/sermons/{d.post_id}", json={"meta": {
                "asc_youtube_video_id": d.stream.video_id, "asc_youtube_url": f"https://www.youtube.com/watch?v={d.stream.video_id}"}})
            print(f"{'✔' if resp.status_code == 200 else '✘'} linked post {d.post_id} -> {d.stream.video_id}")

    pipeline = build_pipeline(settings, args, need_wp=True)
    if args.publish:
        pipeline.post_status = "publish"
    failures = 0
    for d in (d for d in decisions if d.action == "process"):
        meta = backfill.metadata_for(d.stream, overrides.get(d.stream.video_id, {}))
        result = pipeline.process(backfill.to_video(d.stream), meta)
        print_result(result)
        failures += result.status == "failed"
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sermon_worker", description="All Saints' Sermon Flywheel")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Verify configuration, WordPress auth, YouTube and the legacy agent")

    sync = sub.add_parser("sync", help="Process recent service uploads that have no sermon yet")
    sync.add_argument("--limit", type=int, default=3)
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--no-audio", action="store_true")
    sync.add_argument("--whisper", action="store_true", help="Fall back to local Whisper if captions are unavailable")
    sync.add_argument("--notes", action="store_true", help="Add AI sermon notes (needs OPENAI_API_KEY)")

    back = sub.add_parser("backfill", help="Find past livestreams with no sermon on the site and process them")
    back.add_argument("--since", default="2025-05-04", help="Earliest service date (YYYY-MM-DD)")
    back.add_argument("--limit", type=int, default=120, help="How many recent livestreams to examine")
    back.add_argument("--plan-only", action="store_true", help="Show what would happen; change nothing")
    back.add_argument("--publish", action="store_true", help="Publish instead of creating drafts")
    back.add_argument("--link-existing", action="store_true", help="Attach video IDs to migrated sermons matched by date")
    back.add_argument("--no-audio", action="store_true")
    back.add_argument("--whisper", action="store_true")
    back.add_argument("--notes", action="store_true")

    proc = sub.add_parser("process", help="Process one YouTube video")
    proc.add_argument("video_id")
    proc.add_argument("--dry-run", action="store_true")
    proc.add_argument("--no-audio", action="store_true")
    proc.add_argument("--whisper", action="store_true")
    proc.add_argument("--notes", action="store_true", help="Add AI sermon notes (needs OPENAI_API_KEY)")
    proc.add_argument("--transcript", type=Path, help="Use an existing Whisper .json / .vtt transcript")
    proc.add_argument("--audio-source", type=Path, help="Use a local service audio/video file instead of downloading")
    proc.add_argument("--audio-file", type=Path, help="Publish a ready-made sermon MP3 (e.g. AllSaints_Agent/upload-ready/...)")
    proc.add_argument("--form", type=Path, help="Sermon form email text (legacy format): authoritative title/preacher/scripture")
    proc.add_argument("--title")
    proc.add_argument("--preacher")
    proc.add_argument("--scripture", action="append", help="Scripture reference (repeatable)")
    proc.add_argument("--service-date", dest="service_date")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = Settings.from_env()
        handler = {"check": cmd_check, "sync": cmd_sync, "process": cmd_process, "backfill": cmd_backfill}[args.command]
        return handler(settings, args)
    except WordPressAuthError as exc:
        print(f"✘ WordPress authentication failed: {exc}", file=sys.stderr)
        return 2
    except (YouTubeError, ValueError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
