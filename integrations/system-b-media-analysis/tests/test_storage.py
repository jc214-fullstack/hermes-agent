from pathlib import Path

from media_backend.storage import platform_company_path, plan_storage, raw_media_kind


def test_youtube_storage_path_uses_platform_bucket():
    plan = plan_storage("https://www.youtube.com/watch?v=abc123", "youtube", source_id="yt-abc123")

    assert plan.source_key == "yt-abc123"
    assert plan.storage_class == "platform"
    assert plan.company is None
    assert plan.platform == "youtube"
    assert plan.relative_dir == Path("platform/youtube/yt-abc123")


def test_meta_instagram_storage_path_is_company_grouped():
    plan = plan_storage("https://www.instagram.com/p/abc123/", "instagram", source_id="ig-abc123")

    assert plan.source_key == "ig-abc123"
    assert plan.storage_class == "platform"
    assert plan.company == "meta"
    assert plan.platform == "instagram"
    assert plan.relative_dir == Path("platform/meta/instagram/ig-abc123")


def test_instagram_reel_and_post_use_same_platform_bucket():
    reel = plan_storage("https://www.instagram.com/reel/abc123/", "instagram", source_id="abc")
    post = plan_storage("https://www.instagram.com/p/def456/", "instagram", source_id="def")

    assert reel.relative_dir == Path("platform/meta/instagram/abc")
    assert post.relative_dir == Path("platform/meta/instagram/def")


def test_facebook_threads_are_meta_platforms():
    assert platform_company_path("facebook") == ("meta", "facebook")
    assert platform_company_path("threads") == ("meta", "threads")

    facebook = plan_storage("https://www.facebook.com/reel/123", "facebook", source_id="fb-123")
    threads = plan_storage("https://www.threads.net/@user/post/abc", "threads", source_id="th-abc")

    assert facebook.relative_dir == Path("platform/meta/facebook/fb-123")
    assert threads.relative_dir == Path("platform/meta/threads/th-abc")


def test_raw_video_storage_path_handles_direct_mp4():
    plan = plan_storage("https://cdn.example.com/tutorial.mp4", "direct", source_id="raw-test")

    assert plan.storage_class == "raw-file"
    assert plan.raw_kind == "video"
    assert plan.relative_dir == Path("raw-files/video/raw-test")


def test_raw_document_storage_path_handles_direct_pdf():
    plan = plan_storage("https://cdn.example.com/guide.pdf", "direct", source_id="doc-test")

    assert plan.storage_class == "raw-file"
    assert plan.raw_kind == "document"
    assert plan.relative_dir == Path("raw-files/document/doc-test")


def test_generic_article_url_routes_to_web_generic():
    plan = plan_storage("https://example.com/news/story", "unknown", source_id="article")

    assert plan.storage_class == "web"
    assert plan.platform is None
    assert plan.relative_dir == Path("web/generic/article")


def test_raw_media_kind_covers_images_documents_and_audio():
    assert raw_media_kind("/tmp/graphic.png") == "image"
    assert raw_media_kind("https://example.com/audio.wav") == "audio"
    assert raw_media_kind("https://example.com/doc.pdf") == "document"
    assert raw_media_kind("https://example.com/page") is None
