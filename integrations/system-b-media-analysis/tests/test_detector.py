import pytest

from media_backend.detector import SourceInfo, detect


@pytest.mark.parametrize(
    ("url", "source"),
    [
        ("https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://instagram.com/p/DEF456/", "instagram"),
        ("https://www.tiktok.com/@user/video/123456789", "tiktok"),
        ("https://vm.tiktok.com/ABCDEF/", "tiktok"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://www.youtube.com/shorts/abcdef123", "youtube"),
        ("https://twitter.com/user/status/123456789", "twitter"),
        ("https://x.com/user/status/987654321", "twitter"),
        ("https://www.facebook.com/reel/123456789", "facebook"),
        ("https://fb.watch/abc123/", "facebook"),
        ("https://www.threads.net/@user/post/abc123", "threads"),
        ("https://www.reddit.com/r/funny/comments/abc123/title/", "reddit"),
        ("https://v.redd.it/abc123", "reddit"),
        ("https://vimeo.com/123456789", "vimeo"),
        ("https://www.loom.com/share/abc123def456", "loom"),
        ("https://example.com/video.mp4", "direct"),
        ("https://cdn.example.com/media/clip.webm?token=abc", "direct"),
        ("https://example.com/watch?id=123", "unknown"),
        ("not-a-url", "unknown"),
    ],
)
def test_detect_sources(url, source):
    assert detect(url).source == source


def test_detect_returns_source_info_with_url():
    url = "https://www.instagram.com/reel/ABC123/"
    result = detect(url)
    assert isinstance(result, SourceInfo)
    assert result.url == url
    assert result.hostname == "www.instagram.com"
