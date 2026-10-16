"""The sermon flywheel: one YouTube service video → one WordPress sermon draft,
in the parish's established format (an audio post):

    title · preacher · date · scripture · sermon MP3 (play + download)
    · "Watch the full service on YouTube" link · [optional AI sermon notes]

Order: duplicate check → transcript (to find the sermon inside the service)
→ sermon MP3 → scripture text → [optional notes] → upload MP3 → create draft.

Failure policy:
  existing sermon / duplicate  → skip
  transcript missing/too short → do not publish (can't locate the sermon or trim audio)
  audio fails                  → publish without MP3, flagged for the editor
  scripture text unavailable   → reference only
  AI notes fail / invalid JSON → publish without notes, flagged (notes are an add-on)
  WordPress auth failure       → raise (stop the run loudly)
  WordPress write failure      → failed; nothing marked complete
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import legacy
from .audio import make_sermon_mp3
from .gutenberg import paragraph, scripture_blocks, sermon_blocks
from .lectionary import Reading, choose_readings, mentions
from .llm import SermonNotesError, Structurer, enforce_fidelity
from .scripture import fetch_passage
from .transcript import ChainProvider, TranscriptUnavailable, extract_sermon
from .wordpress import DuplicateSermon, WordPressClient, WordPressError, build_sermon_payload
from .youtube import Video

log = logging.getLogger(__name__)


@dataclass
class Result:
    video_id: str
    status: str  # created | skipped | failed | dry_run
    reason: str = ""
    post: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)
    review: list[str] = field(default_factory=list)


@dataclass
class Pipeline:
    transcripts: ChainProvider
    wordpress: WordPressClient | None
    work_dir: Path
    structurer: Structurer | None = None   # set only when AI sermon notes are wanted (--notes)
    esv_api_key: str = ""                  # fallback scripture text source
    readings_for: Callable[[str], list[Reading]] | None = None  # service date -> the day's appointed readings
    post_status: str = "draft"
    with_audio: bool = True
    audio_source: Path | None = None       # full service recording to trim locally
    audio_file: Path | None = None         # ready-made sermon MP3 (e.g. AllSaints_Agent upload-ready output)

    def process(self, video: Video, metadata: dict | None = None, dry_run: bool = False) -> Result:
        meta = dict(metadata or {})
        vid = video.video_id
        log.info("Processing %s (%s)", vid, video.title)

        # 1. Duplicate check (idempotency key: YouTube video ID)
        if self.wordpress:
            existing = self.wordpress.sermon_exists(vid)
            if existing.get("exists"):
                return Result(vid, "skipped", f"Sermon already exists (post {existing.get('post_id')}, {existing.get('status')})", post=existing)
        elif not dry_run:
            return Result(vid, "failed", "WordPress is not configured")

        meta.setdefault("service_title", video.title)
        meta.setdefault("service_date", legacy.infer_service_date(vid, video.title, video.upload_date) or video.upload_date)

        # 2. Transcript → sermon span (legacy liturgical-cue detector)
        try:
            path, source = self.transcripts.get(vid)
            bounds = (meta["start_time"], meta["end_time"]) if meta.get("start_time") and meta.get("end_time") else None
            sermon = extract_sermon(path, source, bounds)
        except TranscriptUnavailable as exc:
            return Result(vid, "failed", f"No usable transcript; not publishing. {exc}")
        review = list(sermon.notes)
        log.info("Sermon %s–%s (%s confidence), %d words via %s", sermon.start_time, sermon.end_time,
                 sermon.confidence, sermon.word_count, sermon.source)

        # 3. Post facts: authoritative metadata only (clergy sermon form / CLI); never guessed.
        title = meta.get("title") or video.title
        preacher = meta.get("preacher")
        scripture = list(meta.get("scripture_references") or [])
        if not meta.get("title"):
            review.append(f"No sermon title supplied; using '{title}'. Please confirm with the preacher.")
        if not preacher:
            review.append("No preacher supplied; please add it.")

        # 4. Optional AI sermon notes (an add-on; never blocks the audio post)
        notes = None
        if self.structurer:
            try:
                notes, fidelity_review = enforce_fidelity(self.structurer.structure(sermon.text, meta), sermon.text, meta)
                review += fidelity_review
            except SermonNotesError as exc:
                review.append(f"AI sermon notes skipped ({exc}).")

        # 5. Scripture: the passage text, as on the parish's existing posts.
        #    Given reference -> text from the day's lectionary insert (else ESV API).
        #    No reference    -> the appointed reading the preacher actually names (>= 2 mentions).
        readings = self.readings_for(meta["service_date"]) if self.readings_for else []
        passages, scripture_title = [], "Scripture"
        if scripture:
            for ref in scripture:
                match = next((r for r in readings if _same_chapter(r.reference, ref)), None)
                passage = match.passage if match else fetch_passage(ref, self.esv_api_key)
                if passage:
                    passages.append(passage)
            if len(passages) < len(scripture):
                review.append("Scripture text not found for every reference; showing the reference only.")
        elif readings:
            chosen = choose_readings(readings, sermon.text)
            if chosen:
                scripture = [r.reference for r in chosen]
                passages = [r.passage for r in chosen]
                counts = ", ".join(f"{r.reference} named {mentions(r.reference, sermon.text)}x" for r in chosen)
                review.append(f"Scripture chosen from the day's appointed readings ({counts} in the sermon); please confirm.")
            else:
                # Show what was actually read at this service, without claiming it as the sermon text.
                passages, scripture_title = [r.passage for r in readings], "The Readings"
                review.append("The sermon does not clearly name one of the day's readings; showing the day's "
                              "appointed readings under 'The Readings'. Add the sermon text if known.")
        else:
            review.append("No scripture supplied and no lectionary insert found for this date.")

        note = paragraph(meta["note"]) if meta.get("note") else ""  # e.g. "recording begins partway through"
        content = "\n\n".join(part for part in (note, scripture_blocks(passages, scripture_title),
                                                 sermon_blocks(notes) if notes else "") if part)
        payload = build_sermon_payload(
            title=title, content=content, preacher=preacher, scripture_references=scripture,
            excerpt=notes.excerpt if notes else None, video_id=vid, video_url=video.url,
            service_date=meta["service_date"], published_at=video.published_at,
            transcript=sermon.text, status=self.post_status,
        )
        if dry_run:
            return Result(vid, "dry_run", "No changes made", payload=payload, review=review)

        # 6. Sermon MP3: the main deliverable (legacy ffmpeg chain), or a ready-made file
        mp3, generated = None, False
        audio_file = Path(meta["audio_file"]) if meta.get("audio_file") else self.audio_file
        if audio_file:
            mp3 = audio_file if audio_file.exists() else None
            if not mp3:
                review.append(f"Audio file not found: {audio_file}")
        elif self.with_audio:
            generated = True
            mp3 = make_sermon_mp3(video.url, sermon.start_time, sermon.end_time,
                                  {**meta, "title": title, "preacher": preacher}, self.work_dir / "audio", self.audio_source)
        if self.with_audio and not mp3:
            review.append("Sermon audio could not be produced; posted without MP3. Please add it.")

        # 7. Upload MP3
        try:
            if mp3:
                payload["meta"]["asc_audio_attachment_id"] = self.wordpress.upload_media(mp3, f"{title} (sermon audio)")
        except WordPressError as exc:
            review.append(f"Audio upload failed ({exc}); posted without MP3.")
        finally:
            if generated:
                self._cleanup(mp3)  # never delete a file the user supplied

        # 8. Create the draft sermon
        try:
            post = self.wordpress.create_sermon(payload)
        except DuplicateSermon as exc:
            return Result(vid, "skipped", f"Duplicate rejected by WordPress: {exc}")
        except WordPressError as exc:
            return Result(vid, "failed", str(exc), payload=payload, review=review)
        return Result(vid, "created", f"Created {post['status']} sermon", post=post, payload=payload, review=review)

    @staticmethod
    def _cleanup(path: Path | None) -> None:
        if path and path.exists():
            try:
                path.unlink()
            except OSError:
                shutil.rmtree(path, ignore_errors=True)


def _same_chapter(a: str, b: str) -> bool:
    """'2 Corinthians 13:5-14' vs '2 Corinthians 13:11-14' -> True (same book and chapter)."""
    def head(ref: str) -> str:
        return ref.split(":")[0].strip().lower()
    return head(a) == head(b)
