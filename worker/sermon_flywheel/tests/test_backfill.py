from datetime import date, datetime

from sermon_worker.backfill import ET, Stream, clean_title, easter, metadata_for, plan


def test_easter_dates():
    assert easter(2025) == date(2025, 4, 20)
    assert easter(2026) == date(2026, 4, 5)


def test_clean_title_fixes_youtube_typos_and_ordinals():
    assert clean_title("18h Sunday after Pentecost 2026", "2026-09-27") == "18th Sunday after Pentecost 2026"
    assert clean_title("Ascension Day 2026i", "2026-05-14") == "Ascension Day 2026"
    # mislabelled on YouTube: 14 June 2026 is the 3rd Sunday after Pentecost (Pentecost was 24 May)
    assert clean_title("2nd Sunday After Pentecost", "2026-06-14") == "3rd Sunday after Pentecost 2026"
    assert clean_title("5th Sunday After Pentecost", "2026-06-28") == "5th Sunday after Pentecost 2026"
    assert clean_title("Second Sunday of Christmas 1-4-26", "2026-01-04") == "Second Sunday of Christmas 1-4-26"


def stream(vid, title, day, hour=11, minutes=95):
    return Stream(vid, title, datetime(*map(int, day.split("-")), hour, 0, tzinfo=ET), minutes)


def test_plan_classifies_streams():
    streams = [
        stream("aaaaaaaaaaa", "5th Sunday of Easter 2026", "2026-05-03"),                # missing
        stream("bbbbbbbbbbb", "Palm Sunday 2026", "2026-03-29"),                         # migrated, unlinked
        stream("ccccccccccc", "Trinity Sunday 2026", "2026-05-31"),                      # already linked
        stream("ddddddddddd", "Celebration of Life - Name", "2026-01-05"),               # pastoral
        stream("eeeeeeeeeee", "7th Sunday After Pentecost", "2026-07-12", minutes=5),    # partial
        stream("fffffffffff", "Good Friday 2026", "2026-04-03", hour=19),                # reviewed: no sermon
        stream("ggggggggggg", "Easter 2025", "2025-04-20"),                              # before window
    ]
    sermons = [
        {"id": 10, "status": "publish", "title": "Palm Sunday Expectations", "date": "2026-03-29", "video_id": ""},
        {"id": 11, "status": "publish", "title": "Gospel Conformity", "date": "2026-05-31", "video_id": "ccccccccccc"},
    ]
    overrides = {"fffffffffff": {"skip": "no sermon"}}
    actions = {d.stream.video_id: (d.action, d.post_id) for d in plan(streams, sermons, overrides, "2025-05-04")}
    assert actions["aaaaaaaaaaa"] == ("process", None)
    assert actions["bbbbbbbbbbb"] == ("link", 10)
    assert actions["ccccccccccc"][0] == "exists"
    assert actions["ddddddddddd"][0] == "skip" and actions["eeeeeeeeeee"][0] == "skip" and actions["fffffffffff"][0] == "skip"
    assert "ggggggggggg" not in actions


def test_metadata_uses_start_time_date_and_overrides():
    st = stream("ccccccccccc", "Trinity Sunday 2026", "2026-05-31")
    meta = metadata_for(st, {"title": "Gospel Conformity", "preacher": "The Rev. Scott Bailey"})
    assert meta["service_date"] == "2026-05-31" and meta["title"] == "Gospel Conformity"
    assert meta["preacher"] == "The Rev. Scott Bailey"
