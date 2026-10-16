"""Pipeline behaviour (audio-post format) and failure policy, with every external system faked."""
import pytest

from sermon_worker import pipeline as pipeline_module
from sermon_worker.lectionary import Reading
from sermon_worker.llm import SermonNotesError, parse_notes
from sermon_worker.pipeline import Pipeline
from sermon_worker.scripture import Passage
from sermon_worker.transcript import ChainProvider, FileTranscriptProvider, TranscriptUnavailable
from sermon_worker.wordpress import WordPressAuthError, WordPressError
from sermon_worker.youtube import Video

VIDEO = Video("abcdefghijk", "Trinity Sunday 2026", "2026-06-01T14:00:00Z")
FORM = {"title": "Gospel Conformity", "preacher": "The Rev. Scott Bailey", "scripture_references": ["2 Corinthians 13:5-14"]}


class FakeWP:
    def __init__(self, exists=False, create_error=None, auth_error=False, upload_error=False):
        self.exists, self.create_error, self.auth_error, self.upload_error = exists, create_error, auth_error, upload_error
        self.created, self.uploaded = [], []

    def sermon_exists(self, video_id):
        if self.auth_error:
            raise WordPressAuthError("401")
        return {"exists": self.exists, "post_id": 9 if self.exists else None, "status": "publish"}

    def upload_media(self, path, title=""):
        if self.upload_error:
            raise WordPressError("upload failed")
        self.uploaded.append(path)
        return 55

    def create_sermon(self, payload):
        if self.create_error:
            raise self.create_error
        self.created.append(payload)
        return {"id": 1, "link": "l", "status": payload["status"], "edit_link": "e"}


class FakeStructurer:
    name = "fake"

    def __init__(self, notes_json=None, error=False):
        self.notes_json, self.error = notes_json, error

    def structure(self, transcript, metadata):
        if self.error:
            raise SermonNotesError("invalid json")
        return parse_notes(self.notes_json)


class NoTranscript:
    name = "none"

    def get(self, video_id):
        raise TranscriptUnavailable("captions disabled")


@pytest.fixture
def mp3(tmp_path):
    path = tmp_path / "sermon.mp3"
    path.write_bytes(b"ID3")
    return path


DAY_READINGS = [
    Reading("Old Testament", "Isaiah 5:1-7", Passage("Isaiah 5:1-7", [("1", "Let me sing for my beloved")])),
    Reading("New Testament", "2 Corinthians 13:5-14", Passage("2 Corinthians 13:5-14", [("5", "Examine yourselves"), ("6", "I hope you will find")])),
]


def make(vtt_path, wp=None, structurer=None, transcripts=None, audio_file=None, esv_api_key="", readings=None) -> Pipeline:
    return Pipeline(
        transcripts=transcripts or ChainProvider([FileTranscriptProvider([vtt_path.parent])]),
        wordpress=wp,
        work_dir=vtt_path.parent,
        structurer=structurer,
        esv_api_key=esv_api_key,
        readings_for=(lambda date: readings) if readings is not None else None,
        with_audio=audio_file is not None,
        audio_file=audio_file,
    )


def test_audio_post_in_parish_format(vtt_path, mp3):
    wp = FakeWP()
    result = make(vtt_path, wp, audio_file=mp3, readings=DAY_READINGS).process(VIDEO, FORM)
    assert result.status == "created" and not result.review
    payload = wp.created[0]
    assert payload["title"] == "Gospel Conformity" and payload["status"] == "draft"
    assert payload["meta"]["asc_preacher"] == "The Rev. Scott Bailey"
    assert payload["meta"]["asc_scripture_references"] == ["2 Corinthians 13:5-14"]
    assert payload["meta"]["asc_audio_attachment_id"] == 55
    assert payload["meta"]["asc_sermon_date"] == "2026-05-31"          # legacy Monday→Sunday rule
    assert payload["meta"]["asc_youtube_url"].endswith("abcdefghijk")  # "Watch the full service" link
    assert "<sup>5</sup> Examine yourselves" in payload["content"]     # verses from the day's insert
    assert "Sermon Notes" not in payload["content"]                    # no AI unless --notes
    assert mp3.exists()                                                 # user-supplied files are never deleted


def test_missing_metadata_is_flagged_not_guessed(vtt_path):
    wp = FakeWP()
    result = make(vtt_path, wp).process(VIDEO)
    payload = wp.created[0]
    assert payload["title"] == "Trinity Sunday 2026"
    assert payload["meta"]["asc_preacher"] == "" and payload["meta"]["asc_scripture_references"] == []
    assert any("No sermon title supplied" in r for r in result.review)
    assert any("No preacher supplied" in r for r in result.review)


def test_scripture_text_from_esv(vtt_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_passage",
                        lambda ref, key: Passage(ref, [("5", "Examine yourselves"), ("6", "I hope you will find")]))
    wp = FakeWP()
    make(vtt_path, wp, esv_api_key="k").process(VIDEO, FORM)
    content = wp.created[0]["content"]
    assert "<sup>5</sup> Examine yourselves" in content and "2 Corinthians 13:5-14 (ESV)" in content


def test_scripture_chosen_from_readings_the_preacher_names(vtt_path):
    wp = FakeWP()
    meta = {k: v for k, v in FORM.items() if k != "scripture_references"}
    result = make(vtt_path, wp, readings=DAY_READINGS).process(VIDEO, meta)
    payload = wp.created[0]
    assert payload["meta"]["asc_scripture_references"] == ["2 Corinthians 13:5-14"]  # named in the sermon; Isaiah is not
    assert "Examine yourselves" in payload["content"]
    assert any("chosen from the day's appointed readings" in r for r in result.review)


def test_day_readings_shown_when_sermon_text_unknown(vtt_path):
    wp = FakeWP()
    meta = {k: v for k, v in FORM.items() if k != "scripture_references"}
    result = make(vtt_path, wp, readings=DAY_READINGS[:1]).process(VIDEO, meta)
    payload = wp.created[0]
    assert payload["meta"]["asc_scripture_references"] == []          # not claimed as the sermon text
    assert "The Readings" in payload["content"] and "Let me sing for my beloved" in payload["content"]
    assert any("appointed readings" in r for r in result.review)


def test_reviewed_bounds_and_audio_override(vtt_path, mp3):
    wp = FakeWP()
    meta = {**FORM, "start_time": "00:30:10", "end_time": "00:40:00", "audio_file": str(mp3)}
    result = make(vtt_path, wp, readings=DAY_READINGS).process(VIDEO, meta)
    assert result.status == "created" and wp.created[0]["meta"]["asc_audio_attachment_id"] == 55


def test_optional_ai_notes_are_added(vtt_path, notes_json):
    wp = FakeWP()
    make(vtt_path, wp, structurer=FakeStructurer(notes_json)).process(VIDEO, FORM)
    payload = wp.created[0]
    assert "Sermon Notes" in payload["content"] and payload["excerpt"]
    assert payload["meta"]["asc_scripture_references"] == ["2 Corinthians 13:5-14"]  # AI never sets scripture


def test_ai_notes_failure_does_not_block_the_post(vtt_path):
    wp = FakeWP()
    result = make(vtt_path, wp, structurer=FakeStructurer(error=True)).process(VIDEO, FORM)
    assert result.status == "created" and "Sermon Notes" not in wp.created[0]["content"]
    assert any("AI sermon notes skipped" in r for r in result.review)


def test_existing_sermon_is_skipped_before_any_work(vtt_path):
    wp = FakeWP(exists=True)
    result = make(vtt_path, wp, transcripts=ChainProvider([NoTranscript()])).process(VIDEO)
    assert result.status == "skipped" and not wp.created


def test_missing_transcript_never_publishes(vtt_path):
    wp = FakeWP()
    result = make(vtt_path, wp, transcripts=ChainProvider([NoTranscript()])).process(VIDEO)
    assert result.status == "failed" and "not publishing" in result.reason and not wp.created


def test_audio_upload_failure_continues_and_is_flagged(vtt_path, mp3):
    wp = FakeWP(upload_error=True)
    result = make(vtt_path, wp, audio_file=mp3).process(VIDEO, FORM)
    assert result.status == "created"
    assert "asc_audio_attachment_id" not in wp.created[0]["meta"]
    assert any("Audio upload failed" in r for r in result.review)


def test_wordpress_auth_failure_propagates(vtt_path):
    with pytest.raises(WordPressAuthError):
        make(vtt_path, FakeWP(auth_error=True)).process(VIDEO)


def test_wordpress_write_failure_is_failed(vtt_path):
    result = make(vtt_path, FakeWP(create_error=WordPressError("500"))).process(VIDEO, FORM)
    assert result.status == "failed"


def test_dry_run_makes_no_writes(vtt_path, mp3):
    wp = FakeWP()
    result = make(vtt_path, wp, audio_file=mp3).process(VIDEO, FORM, dry_run=True)
    assert result.status == "dry_run" and result.payload["meta"]["asc_youtube_video_id"] == "abcdefghijk"
    assert not wp.created and not wp.uploaded
