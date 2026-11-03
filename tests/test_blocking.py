"""Run: .venv/bin/python -m pytest tests  (or: .venv/bin/python tests/test_blocking.py)"""
import os
import sys

os.environ["HASEED_NO_BROWSER"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server  # noqa: E402

BLOCKED = [
    "https://www.pornhub.com/view_video.php?viewkey=abc",
    "https://xhamster.com/videos/x-123",
    "https://www.xvideos.com/video123/x",
    "https://chaturbate.com/someone/",
    "https://some-random-sexvideos.example/watch/1",
    "https://freeporn.example/v/1",
]
MUSIC = [
    "https://soundcloud.com/someone/some-track",
    "https://open.spotify.com/track/abc",
    "https://music.youtube.com/watch?v=abc",
    "https://artist.bandcamp.com/track/song",
    "https://www.anghami.com/song/123",
    "https://www.deezer.com/track/1",
    "https://music.apple.com/us/album/x/1",
]
ALLOWED = [
    "https://www.youtube.com/watch?v=rJPGXnWDFuw",
    "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    "https://www.instagram.com/reel/abc/",
    "https://x.com/user/status/1",
    "https://www.reddit.com/r/islam/comments/abc/x/",
    "https://www.essex.ac.uk/video",
    "https://www.middlesex.gov.uk/video",
    "https://podcasts.apple.com/us/podcast/x/id1",
    "https://www.youtube.com/watch?v=abc&list=xyz",
]


def blocked(url):
    try:
        server.check_allowed(url)
        return False
    except RuntimeError:
        return True


def test_adult_sites_blocked():
    assert [u for u in BLOCKED if not blocked(u)] == []


def test_normal_sites_allowed():
    assert [u for u in ALLOWED if blocked(u)] == []


def test_music_sites_blocked():
    assert [u for u in MUSIC if not blocked(u)] == []


def test_site_names_exist_in_yt_dlp():
    # a misspelt name would silently leave that site unblocked
    names = {ie.ie_key() for ie in server._SITES}
    assert server.ADULT_SITES <= names
    assert server.MUSIC_SITES <= names


if __name__ == "__main__":
    test_adult_sites_blocked(); test_music_sites_blocked(); test_normal_sites_allowed(); test_site_names_exist_in_yt_dlp()
    print("all blocking tests pass")
