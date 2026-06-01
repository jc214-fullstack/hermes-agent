from media_backend.adapters import AdapterDecision, decide_adapter


def test_youtube_routes_to_ytdlp():
    decision = decide_adapter("https://www.youtube.com/watch?v=abc123", "youtube")

    assert decision == AdapterDecision(
        primary="yt-dlp",
        fallbacks=(),
        reason="video platform",
        expected_media_kind="video",
    )


def test_instagram_post_routes_gallery_first_with_ytdlp_fallback():
    decision = decide_adapter("https://www.instagram.com/p/abc123/", "instagram", allow_playlist=True)

    assert decision.primary == "gallery-dl"
    assert decision.fallbacks == ("yt-dlp",)
    assert decision.expected_media_kind == "carousel"


def test_instagram_reel_routes_ytdlp_with_gallery_fallback():
    decision = decide_adapter("https://www.instagram.com/reel/abc123/", "instagram")

    assert decision.primary == "yt-dlp"
    assert decision.fallbacks == ("gallery-dl",)
    assert decision.expected_media_kind == "video"


def test_social_sources_route_gallery_first():
    for source in ("twitter", "reddit", "facebook"):
        decision = decide_adapter(f"https://example.test/{source}/status/1", source)
        assert decision.primary == "gallery-dl"
        assert decision.fallbacks == ("yt-dlp",)


def test_direct_video_routes_direct():
    decision = decide_adapter("https://cdn.example.com/clip.mp4", "direct")

    assert decision.primary == "direct"
    assert decision.expected_media_kind == "video"


def test_pdf_url_routes_document_adapter():
    decision = decide_adapter("https://cdn.example.com/guide.pdf", "direct")

    assert decision.primary == "document"
    assert decision.expected_media_kind == "document"


def test_generic_page_routes_ytdlp_with_web_page_fallback():
    decision = decide_adapter("https://example.com/story", "unknown")

    assert decision.primary == "yt-dlp"
    assert decision.fallbacks == ("web-page",)
    assert decision.expected_media_kind is None
