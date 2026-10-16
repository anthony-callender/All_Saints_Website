from sermon_worker.scripture import fetch_passage, parse_passage


def test_parse_esv_text():
    p = parse_passage("1 Peter 1:3-4", "  [3] Blessed be the God and Father\n    of our Lord [4] to an inheritance  ")
    assert p.verses == [("3", "Blessed be the God and Father of our Lord"), ("4", "to an inheritance")]


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.resp


def test_fetch_passage_ok():
    s = FakeSession(FakeResp(200, {"passages": ["[5] Examine yourselves"]}))
    p = fetch_passage("2 Corinthians 13:5", "key", s)
    assert p.verses == [("5", "Examine yourselves")]
    assert s.calls[0]["headers"]["Authorization"] == "Token key"


def test_fetch_passage_failures_mean_reference_only():
    assert fetch_passage("John 3:16", "", FakeSession(None)) is None                      # no key
    assert fetch_passage("John 3:16", "k", FakeSession(FakeResp(401, {}))) is None        # bad key
    assert fetch_passage("Hezekiah 1:1", "k", FakeSession(FakeResp(200, {"passages": []}))) is None
