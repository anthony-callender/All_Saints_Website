# Legacy Sermon Agent Analysis (`AllSaints_Agent/`)

Inspected before any new sermon code was written. **Nothing in `AllSaints_Agent/` was moved, deleted, or edited.** It has its own git history (`fc4ffe8 Initial Commit`) and stays a standalone tool; the new worker imports it through a thin adapter.

## Summary

`AllSaints_Agent` is a set of ~1,600 lines of standard-library-heavy Python scripts (`automation/*.py`) operated by hand, one script per step, communicating through JSON "job" files in `work/`. It reliably produces a **trimmed, loudness-normalised sermon MP3 plus a copy-paste "posting packet"** for Squarespace. The final step — publishing to the website — is manual (13 click-steps documented in `workflow/allsaints-workflow.md`).

Important correction to the project brief: the agent does **not** pull transcripts from YouTube captions. It downloads the service audio with `yt-dlp` and transcribes it locally with **OpenAI Whisper (CLI)**. The transcript is used to *find the sermon inside the full service*, not to write notes.

## Entry points

| Script | Role | Reliability |
|---|---|---|
| `discover_work.py` | Reads the channel RSS feed (yt-dlp fallback) and scrapes `/latest-sermons`; marks services `needs_sermon_post` / `already_posted` / `review` by date. Infers Sunday date from Monday uploads. | Works; HTML scraping of Squarespace is fragile. |
| `create_job_from_discovery.py` | Turns a discovery item into a job JSON. | Trivial, fine. |
| `fetch_sermon_form.py` | Gmail IMAP: finds latest "sermon" email (clergy sermon form) and builds a packet. | Works with an app password. |
| `form_to_packet.py` | `parse_form()` — regex parser for the sermon-form email (title, preacher, scripture, scripture text, notes). | Solid, small, pure. |
| `transcribe_service.py` | Downloads audio (`download_youtube_audio`) and runs `whisper --model base`; optionally runs bounds detection and writes it into the job. | Works; slow on CPU (base model, full 90-min service). |
| `detect_sermon_bounds.py` | `detect(load_segments(path))` — finds sermon start/end in a Whisper JSON/TSV/VTT transcript using Anglican liturgical cues ("The Gospel of the Lord" → "you may be seated" … "we believe in one God" / Nicene Creed). Returns times + confidence. | **The most valuable piece.** Pure function, proven on a real service (high confidence on 2026‑05‑31). |
| `process_sermon_audio.py` | `build_audio()` — ffmpeg trim + mono + highpass/lowpass + loudnorm → 128k MP3 with ID3 title/artist/album/date. | Works; produced the real `upload-ready` MP3. |
| `weekly_packet.py` | `packet_text()` — Markdown packet for manual Squarespace posting; `slugify()`. | Replaced by REST publishing. |
| `check_environment.py`, `setup_ffmpeg.py`, `transcribe_instructions.ps1` | Tooling / one-off transcription of the *instruction* videos. | Utility only. |

`AllSaintsSermons-1..4.*` and `AllSaintsYouTube.*` are recordings + transcripts of **volunteer training videos** describing the manual process (useful requirements evidence, not sermon content).

## Current workflow

```
YouTube RSS ──► discover_work ──► job.json ──► transcribe_service (yt-dlp + Whisper)
                                                     │
sermon-form email ──► form_to_packet                 ▼
         (title, preacher, scripture)         detect_sermon_bounds
                         │                           │
                         └──────────► process_sermon_audio (ffmpeg) ──► MP3 + packet.md
                                                                          │
                                                       upload-ready/ ──► MANUAL Squarespace post
```

## Data model observed (real example `upload-ready/2026-05-31-gospel-conformity/job-data.json`)

`service_date, service_title, sermon_title, preacher, scripture_reference, scripture_text, youtube_url, start_time, end_time, boundary_detection{confidence,start_reason,end_reason}, audio_file, notes`.
Real values: *Gospel Conformity* · Scott · 2 Corinthians 13:5‑14 · video `6vWOq_VIX7E` · sermon 00:21:35 → 00:46:56 (high confidence).

## Dependencies & configuration

- Python 3.10+ stdlib; `yt-dlp`; `openai-whisper` CLI; `ffmpeg` (on PATH or `AllSaints_Agent/.bin`); `imageio-ffmpeg` (setup only).
- `.env` loaded by `local_env.load_local_env()` (Gmail IMAP, Planning Center, YouTube OAuth placeholders). No secrets committed; README asks for credential rotation because passwords were shared by email.
- Module imports are flat (`from weekly_packet import ROOT`), so `automation/` must be on `sys.path` to import.

## Reuse decision

| Component | Decision | How |
|---|---|---|
| `detect_sermon_bounds.detect/load_segments` | **Reuse as-is** | Worker trims transcript to the sermon before the LLM call, and trims audio. |
| `process_sermon_audio.build_audio/download_youtube_audio/timestamp/seconds` | **Reuse as-is** | Audio step calls `build_audio()` with detected bounds. |
| `transcribe_service` Whisper invocation | **Reuse logic** | `WhisperTranscriptProvider` runs the same CLI command; legacy script untouched. |
| `form_to_packet.parse_form` | **Reuse as-is** | Optional `--form` file supplies clergy-authoritative title/preacher/scripture that overrides LLM guesses. |
| `discover_work.fetch_youtube_rss` | **Reuse as fallback** | Used only when `YOUTUBE_API_KEY` is absent; primary detection is YouTube Data API uploads playlist. |
| `discover_work.fetch_sermon_posts` (Squarespace scrape) | **Replace** | Duplicate check is now `GET /wp-json/asc/v1/sermons/exists?youtube_video_id=`. |
| `weekly_packet.packet_text`, `upload-ready/` | **Retire for website** | Replaced by deterministic Gutenberg blocks + REST. YouTube title/thumbnail checklist remains a manual task. |
| `fetch_sermon_form` (IMAP) | **Leave untouched** | Out of weekend scope; can feed `--form` later. |

## Technical debt

- Steps chained by hand through files; no idempotency beyond "website already has a post on that date" (date-matching, title-collision prone).
- Squarespace HTML scraping for duplicate detection.
- Whisper `base` on full service is slow; no caching key other than filename.
- Exits via `SystemExit` inside library-ish functions (adapter catches it).
- Hard-coded absolute path from another machine in `job-data.json`.
- Binary media (≈270 MB of MP4 + MP3) sits in the folder; only `work/` and `downloads/` are ignored by its `.gitignore`.

## WordPress integration gap (what the new worker adds)

1. YouTube Data API upload detection (uploads playlist, no search quota burn).
2. Idempotency keyed on **YouTube video ID** via WordPress.
3. Structured, fidelity-constrained LLM summary (JSON, validated) — the legacy agent produced none.
4. Deterministic Gutenberg block generation.
5. Media upload (MP3) + Sermon CPT creation through the WordPress REST API with an Application Password, as **draft** by default so a person reviews before publishing.
