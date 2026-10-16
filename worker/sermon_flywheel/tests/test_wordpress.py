import pytest

from sermon_worker import PIPELINE_VERSION
from sermon_worker.gutenberg import scripture_blocks, sermon_blocks
from sermon_worker.llm import parse_notes
from sermon_worker.scripture import Passage
from sermon_worker.wordpress import (
    DuplicateSermon, WordPressAuthError, WordPressClient, WordPressError, build_sermon_payload,
)


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.text = status, body or {}, str(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.auth = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def client(responses):
    return WordPressClient("http://allsaints.ddev.site", "sermon-worker", "abcd efgh", session=FakeSession(responses))


def test_notes_blocks_are_deterministic_and_escaped(notes_json):
    notes = parse_notes(notes_json.replace("Examine yourselves", "Examine <script>yourselves</script>"))
    html = sermon_blocks(notes)
    assert html == sermon_blocks(notes)
    assert "<script>" not in html and "&lt;script&gt;" in html
    order = [html.index(h) for h in ("Sermon Notes", "Examine", "Closing Takeaway")]
    assert order == sorted(order)


def test_scripture_blocks_match_parish_format():
    html = scripture_blocks([Passage("1 Peter 1:3-4", [("3", "Blessed be the God <and> Father"), ("4", "to an inheritance")])])
    assert "<sup>3</sup> Blessed be the God &lt;and&gt; Father" in html
    assert "<cite>1 Peter 1:3-4 (ESV)</cite>" in html and "ESV® Bible" in html
    assert scripture_blocks([]) == ""


def test_payload_shape():
    payload = build_sermon_payload(title="Gospel Conformity", content="<p>x</p>", preacher="The Rev. Scott Bailey",
                                   scripture_references=["2 Corinthians 13:5-14"], excerpt=None,
                                   video_id="6vWOq_VIX7E", video_url="https://youtu.be/6vWOq_VIX7E",
                                   service_date="2026-05-31", published_at="2026-06-01T14:00:00Z", transcript="t",
                                   status="draft", audio_attachment_id=42)
    assert payload["status"] == "draft" and payload["date"] == "2026-05-31T11:00:00"
    assert "excerpt" not in payload
    assert payload["meta"]["asc_youtube_video_id"] == "6vWOq_VIX7E"
    assert payload["meta"]["asc_audio_attachment_id"] == 42
    assert payload["meta"]["asc_preacher"] == "The Rev. Scott Bailey"
    assert payload["meta"]["asc_pipeline_version"] == PIPELINE_VERSION


def test_exists_and_create():
    wp = client([FakeResponse(200, {"exists": False}), FakeResponse(201, {"id": 7, "link": "l", "status": "draft"})])
    assert wp.sermon_exists("6vWOq_VIX7E") == {"exists": False}
    post = wp.create_sermon({"title": "t"})
    assert post["id"] == 7 and post["edit_link"].endswith("post=7&action=edit")
    method, url, kwargs = wp.session.calls[1]
    assert method == "POST" and url.endswith("/wp-json/wp/v2/sermons")


def test_auth_failure_is_loud():
    with pytest.raises(WordPressAuthError):
        client([FakeResponse(401, {"code": "rest_not_logged_in"})]).sermon_exists("6vWOq_VIX7E")


def test_duplicate_conflict():
    with pytest.raises(DuplicateSermon):
        client([FakeResponse(409, {"message": "exists"})]).create_sermon({})


def test_write_failure():
    with pytest.raises(WordPressError):
        client([FakeResponse(500, {"message": "db"})]).create_sermon({})


def test_refuses_credentials_over_plain_http_to_remote_host():
    with pytest.raises(WordPressAuthError):
        WordPressClient("http://example.org", "u", "p")


def test_requires_credentials():
    with pytest.raises(WordPressAuthError):
        WordPressClient("https://example.org", "", "")
