import json
from unittest.mock import MagicMock, patch

import pytest

from media_backend.downloader import DownloadError, download


def test_download_success(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_video.write_bytes(b"fake video data")
    fake_info = tmp_path / "abc123.info.json"
    fake_info.write_text(json.dumps({"id": "abc123", "title": "Test Reel"}))

    with patch("media_backend.downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        video_path, metadata = download("https://instagram.com/reel/abc123/", tmp_path)

    assert video_path == fake_video
    assert metadata["id"] == "abc123"
    assert metadata["title"] == "Test Reel"
    cmd = mock_run.call_args[0][0]
    assert "yt-dlp" in cmd
    assert "--write-info-json" in cmd
    assert "--no-playlist" in cmd
    assert metadata["_downloaded_media_paths"] == [str(fake_video)]
    assert metadata["_adapter_decision"]["primary"] == "yt-dlp"


def test_download_ytdlp_failure(tmp_path):
    with patch("media_backend.downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="ERROR: Unsupported URL", stdout="")
        with pytest.raises(DownloadError, match="yt-dlp exited 1"):
            download("https://example.com/bad", tmp_path)


def test_download_no_output_file(tmp_path):
    with patch("media_backend.downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        with pytest.raises(DownloadError, match="no output media file"):
            download("https://instagram.com/reel/abc123/", tmp_path)


def test_download_creates_output_dir(tmp_path):
    target = tmp_path / "nested" / "dir"

    def side_effect(*args, **kwargs):
        target.mkdir(parents=True, exist_ok=True)
        (target / "abc123.mp4").write_bytes(b"fake")
        return MagicMock(returncode=0, stderr="", stdout="")

    with patch("media_backend.downloader.subprocess.run", side_effect=side_effect):
        video_path, _ = download("https://instagram.com/reel/abc123/", target)

    assert target.exists()
    assert video_path.name == "abc123.mp4"


def test_download_corrupt_info_json(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_video.write_bytes(b"fake")
    corrupt_info = tmp_path / "abc123.info.json"
    corrupt_info.write_text("NOT VALID JSON {{{")

    with patch("media_backend.downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        video_path, metadata = download("https://instagram.com/reel/abc123/", tmp_path)

    assert video_path == fake_video
    assert metadata["_acquisition_method"] == "yt-dlp"
    assert metadata["_downloaded_media_paths"] == [str(fake_video)]
    assert metadata["_adapter_decision"]["primary"] == "yt-dlp"


def test_download_allow_playlist_uses_gallery_dl_for_social_carousels(tmp_path):
    gallery_dir = tmp_path / "gallery-dl"

    def side_effect(cmd, **kwargs):
        gallery_dir.mkdir(parents=True, exist_ok=True)
        (gallery_dir / "post-1.jpg").write_bytes(b"fake image 1")
        (gallery_dir / "post-2.jpg").write_bytes(b"fake image 2")
        (gallery_dir / "post.info.json").write_text(json.dumps({"id": "abc123", "title": "Carousel"}))
        return MagicMock(returncode=0, stderr="", stdout="")

    with patch("media_backend.downloader.subprocess.run", side_effect=side_effect) as mock_run:
        primary_path, metadata = download("https://instagram.com/p/abc123/", tmp_path, allow_playlist=True)

    cmd = mock_run.call_args[0][0]
    assert "gallery-dl" in cmd
    assert "--write-metadata" in cmd
    assert primary_path == gallery_dir / "post-1.jpg"
    assert metadata["_acquisition_method"] == "gallery-dl"
    assert metadata["_downloaded_media_paths"] == [str(gallery_dir / "post-1.jpg"), str(gallery_dir / "post-2.jpg")]
    assert metadata["_adapter_decision"]["primary"] == "gallery-dl"


def test_download_direct_local_file_registers_raw_media(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake video")
    out_dir = tmp_path / "out"

    media_path, metadata = download(str(source), out_dir)

    assert media_path == out_dir / "input.mp4"
    assert media_path.read_bytes() == b"fake video"
    assert metadata["_acquisition_method"] == "direct"
    assert metadata["extractor"] == "direct"
    assert metadata["_downloaded_media_paths"] == [str(media_path)]
    assert metadata["_adapter_decision"]["primary"] == "direct"


def test_download_direct_document_registers_document_adapter(tmp_path):
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"%PDF")
    out_dir = tmp_path / "out"

    media_path, metadata = download(str(source), out_dir)

    assert media_path == out_dir / "guide.pdf"
    assert metadata["_acquisition_method"] == "document"
    assert metadata["_adapter_decision"]["primary"] == "document"


def test_download_generic_web_page_fails_with_adapter_diagnostic(tmp_path):
    with pytest.raises(DownloadError, match="web-page adapter unsupported"):
        download("https://example.com/story", tmp_path)
