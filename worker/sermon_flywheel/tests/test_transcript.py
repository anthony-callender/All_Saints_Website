from pathlib import Path

import pytest

from sermon_worker.transcript import (
    ChainProvider, FileTranscriptProvider, TranscriptUnavailable, extract_sermon, merge_rolling,
)


def test_merge_rolling_removes_caption_overlap():
    cues = ["Good morning everyone.", "Good morning everyone. So good to see", "So good to see all of you", "[Music] all of you today."]
    assert merge_rolling(cues) == "Good morning everyone. So good to see all of you today."


def test_extract_sermon_uses_legacy_bounds(vtt_path):
    sermon = extract_sermon(vtt_path, "test")
    assert sermon.confidence in ("medium", "high")
    assert "Second Corinthians" in sermon.text
    assert "We believe in one God" not in sermon.text  # Creed is after the sermon end
    assert sermon.word_count > 300


def test_empty_transcript_is_unavailable(tmp_path):
    empty = tmp_path / "x.vtt"
    empty.write_text("WEBVTT\n\n", encoding="utf-8")
    with pytest.raises(TranscriptUnavailable):
        extract_sermon(empty, "test")


def test_short_transcript_is_rejected(tmp_path):
    short = tmp_path / "x.vtt"
    short.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nYou may be seated. A few words only.\n", encoding="utf-8")
    with pytest.raises(TranscriptUnavailable, match="too short"):
        extract_sermon(short, "test", bounds=("00:00:00", "00:00:10"))


def test_low_confidence_is_not_published(tmp_path):
    service = tmp_path / "x.vtt"
    lines = ["WEBVTT", ""]
    for m in range(50):
        lines += [f"00:{m:02d}:00.000 --> 00:{m:02d}:05.000", f"A hymn and some prayers, verse {m}.", ""]
    service.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(TranscriptUnavailable, match="low-confidence"):
        extract_sermon(service, "test")


def test_reviewed_bounds_override_detection(vtt_path):
    sermon = extract_sermon(vtt_path, "test", bounds=("00:30:10", "00:40:00"))
    assert sermon.confidence == "reviewed" and sermon.start_time == "00:30:10"


class Failing:
    name = "captions"

    def get(self, video_id):
        raise TranscriptUnavailable("captions disabled")


def test_chain_falls_through_and_reports_reasons(vtt_path):
    chain = ChainProvider([Failing(), FileTranscriptProvider([vtt_path.parent])])
    path, source = chain.get("abcdefghijk")
    assert path == vtt_path and source == "file"
    with pytest.raises(TranscriptUnavailable, match="captions disabled"):
        ChainProvider([Failing()]).get("abcdefghijk")


def test_explicit_missing_file(tmp_path):
    with pytest.raises(TranscriptUnavailable):
        FileTranscriptProvider([], tmp_path / "missing.json").get("abcdefghijk")
