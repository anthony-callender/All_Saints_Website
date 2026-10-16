import pytest

from sermon_worker.youtube import (
    Video, YouTubeError, is_valid_video_id, looks_like_service, parse_playlist_items, parse_uploads_playlist,
)


def test_uploads_playlist_parsed():
    resp = {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUOouhW9_VVwiVODtl0gDvVA"}}}]}
    assert parse_uploads_playlist(resp) == "UUOouhW9_VVwiVODtl0gDvVA"


def test_missing_channel_raises():
    with pytest.raises(YouTubeError):
        parse_uploads_playlist({"items": []})


def test_playlist_items_skip_private_and_invalid(playlist_response):
    videos = parse_playlist_items(playlist_response)
    assert [v.video_id for v in videos] == ["6vWOq_VIX7E", "AAAAAAAAAAA"]
    first = videos[0]
    assert first.title == "Trinity Sunday 2026"
    assert first.upload_date == "2026-06-01"
    assert first.url == "https://www.youtube.com/watch?v=6vWOq_VIX7E"
    assert first.thumbnail_url.endswith("hqdefault.jpg")


def test_service_filter():
    assert looks_like_service(Video("6vWOq_VIX7E", "Trinity Sunday 2026", ""))
    assert looks_like_service(Video("6vWOq_VIX7E", "18th Sunday after Pentecost 2026", ""))
    assert not looks_like_service(Video("AAAAAAAAAAA", "VBS Promo", ""))


@pytest.mark.parametrize("vid,ok", [("6vWOq_VIX7E", True), ("short", False), ("6vWOq_VIX7E&x=1", False), ("", False)])
def test_video_id_validation(vid, ok):
    assert is_valid_video_id(vid) is ok
