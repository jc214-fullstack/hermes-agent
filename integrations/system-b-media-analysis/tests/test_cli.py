from pathlib import Path
from unittest.mock import patch

from media_backend.cli import _media_kind, main
from media_backend.downloader import DownloadError
from media_backend.extractor import ExtractionError, TranscriptionError


def test_media_kind_classifies_supported_flows():
    assert _media_kind([Path("post.jpg")]) == "image"
    assert _media_kind([Path("post-1.jpg"), Path("post-2.webp")]) == "carousel"
    assert _media_kind([Path("clip.mp4")]) == "video"
    assert _media_kind([Path("audio.wav")]) == "audio"
    assert _media_kind([Path("guide.pdf")]) == "document"
    assert _media_kind([Path("post-1.jpg"), Path("post-2.mp4")]) == "mixed_carousel"


def test_main_success(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"
    source_root = tmp_path / "sources"
    expected_source_dir = source_root / "platform" / "meta" / "instagram"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {"id": "abc123"})) as mock_dl,
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "abc123-analysis" / "audio.wav"),
        patch("media_backend.cli.transcribe_audio", return_value=tmp_path / "02b-stt-transcript.md") as mock_stt,
        patch("media_backend.cli.extract_frames", return_value=[tmp_path / "abc123-analysis" / "frames" / "frame-001.jpg"]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["--source-root", str(source_root), "https://www.instagram.com/reel/abc123/", str(tmp_path)])

    assert result == 0
    assert mock_dl.call_args.args[0] == "https://www.instagram.com/reel/abc123/"
    assert str(mock_dl.call_args.args[1]).startswith(str(expected_source_dir))
    assert mock_dl.call_args.kwargs == {"allow_playlist": False}
    mock_stt.assert_called_once()
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["source_storage"]["source_dir"].startswith(str(expected_source_dir))
    assert manifest_payload["thread_run"]["workspace_path"] == str(tmp_path)


def test_main_download_failure_exits_nonzero(tmp_path, capsys):
    with patch("media_backend.cli.download", side_effect=DownloadError("yt-dlp failed")):
        result = main(["https://www.instagram.com/reel/abc123/", str(tmp_path)])

    assert result == 1
    assert "ERROR download" in capsys.readouterr().err


def test_main_skip_audio_and_frames(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio") as mock_audio,
        patch("media_backend.cli.transcribe_audio") as mock_stt,
        patch("media_backend.cli.extract_frames") as mock_frames,
        patch("media_backend.cli.write_manifest", return_value=fake_manifest),
    ):
        result = main(["--skip-audio", "--skip-frames", "https://www.youtube.com/shorts/abc123", str(tmp_path)])

    assert result == 0
    mock_audio.assert_not_called()
    mock_stt.assert_not_called()
    mock_frames.assert_not_called()


def test_main_audio_failure_is_nonfatal(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio", side_effect=ExtractionError("ffmpeg failed")),
        patch("media_backend.cli.extract_frames", return_value=[]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest),
    ):
        result = main(["https://www.instagram.com/reel/abc123/", str(tmp_path)])

    assert result == 0


def test_main_frame_interval_forwarded(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "audio.wav"),
        patch("media_backend.cli.transcribe_audio", return_value=tmp_path / "02b-stt-transcript.md"),
        patch("media_backend.cli.extract_frames", return_value=[]) as mock_frames,
        patch("media_backend.cli.write_manifest", return_value=fake_manifest),
    ):
        main(["--frame-interval", "4", "https://youtu.be/abc123", str(tmp_path)])

    assert mock_frames.call_args.kwargs["interval"] == 4


def test_main_prints_manifest_path_to_stdout(tmp_path, capsys):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "audio.wav"),
        patch("media_backend.cli.transcribe_audio", return_value=tmp_path / "02b-stt-transcript.md"),
        patch("media_backend.cli.extract_frames", return_value=[]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest),
    ):
        main(["https://youtu.be/abc123", str(tmp_path)])

    stdout = capsys.readouterr().out.strip()
    assert stdout == str(fake_manifest)


def test_main_transcription_failure_is_nonfatal(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "audio.wav"),
        patch("media_backend.cli.transcribe_audio", side_effect=TranscriptionError("stt failed")),
        patch("media_backend.cli.extract_frames", return_value=[]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["https://www.instagram.com/reel/abc123/", str(tmp_path)])

    assert result == 0
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["transcript_status"] == "stt_failed"
    assert manifest_payload["transcript_method"] == "faster-whisper"


def test_main_skip_transcript(tmp_path):
    fake_video = tmp_path / "abc123.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_video, {})),
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "audio.wav"),
        patch("media_backend.cli.transcribe_audio") as mock_stt,
        patch("media_backend.cli.extract_frames", return_value=[]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["--skip-transcript", "https://www.instagram.com/reel/abc123/", str(tmp_path)])

    assert result == 0
    mock_stt.assert_not_called()
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["transcript_status"] == "skipped"


def test_main_visual_image_skips_audio_stt_and_frame_extraction(tmp_path):
    fake_image = tmp_path / "post.jpg"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_image, {"_downloaded_media_paths": [str(fake_image)]})),
        patch("media_backend.cli.extract_audio") as mock_audio,
        patch("media_backend.cli.transcribe_audio") as mock_stt,
        patch("media_backend.cli.extract_frames") as mock_frames,
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["https://www.instagram.com/p/abc123/", str(tmp_path)])

    assert result == 0
    mock_audio.assert_not_called()
    mock_stt.assert_not_called()
    mock_frames.assert_not_called()
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["media_kind"] == "image"
    assert manifest_payload["frames"] == [str(fake_image)]
    assert manifest_payload["transcript_status"] == "visual_only"


def test_main_instagram_post_allows_carousel_download(tmp_path):
    fake_image = tmp_path / "post1.jpg"
    fake_manifest = tmp_path / "manifest.json"
    source_root = tmp_path / "sources"

    with (
        patch("media_backend.cli.download", return_value=(fake_image, {"_downloaded_media_paths": [str(fake_image)]})) as mock_dl,
        patch("media_backend.cli.extract_audio"),
        patch("media_backend.cli.extract_frames"),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest),
    ):
        result = main(["--source-root", str(source_root), "https://www.instagram.com/p/abc123/", str(tmp_path)])

    assert result == 0
    assert mock_dl.call_args.args[0] == "https://www.instagram.com/p/abc123/"
    assert str(mock_dl.call_args.args[1]).startswith(str(source_root / "platform" / "meta" / "instagram"))
    assert mock_dl.call_args.kwargs == {"allow_playlist": True}


def test_main_document_url_skips_video_extraction(tmp_path):
    fake_doc = tmp_path / "sources" / "raw-files" / "document" / "guide" / "guide.pdf"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch("media_backend.cli.download", return_value=(fake_doc, {"_downloaded_media_paths": [str(fake_doc)]})),
        patch("media_backend.cli.extract_audio") as mock_audio,
        patch("media_backend.cli.transcribe_audio") as mock_stt,
        patch("media_backend.cli.extract_frames") as mock_frames,
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["--source-root", str(tmp_path / "sources"), "https://cdn.example.com/guide.pdf", str(tmp_path)])

    assert result == 0
    mock_audio.assert_not_called()
    mock_stt.assert_not_called()
    mock_frames.assert_not_called()
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["media_kind"] == "document"
    assert manifest_payload["transcript_status"] == "document_only"


def test_main_mixed_carousel_preserves_all_asset_records(tmp_path):
    fake_image = tmp_path / "post1.jpg"
    fake_video = tmp_path / "post2.mp4"
    fake_manifest = tmp_path / "manifest.json"

    with (
        patch(
            "media_backend.cli.download",
            return_value=(
                fake_video,
                {"_downloaded_media_paths": [str(fake_image), str(fake_video)]},
            ),
        ),
        patch("media_backend.cli.extract_audio", return_value=tmp_path / "audio.wav"),
        patch("media_backend.cli.transcribe_audio", return_value=tmp_path / "02b-stt-transcript.md"),
        patch("media_backend.cli.extract_frames", return_value=[tmp_path / "frame-001.jpg"]),
        patch("media_backend.cli.write_manifest", return_value=fake_manifest) as mock_manifest,
    ):
        result = main(["https://www.instagram.com/p/abc123/", str(tmp_path)])

    assert result == 0
    manifest_payload = mock_manifest.call_args.args[1]
    assert manifest_payload["media_kind"] == "mixed_carousel"
    assert manifest_payload["media_paths"] == [str(fake_image), str(fake_video)]
    assert manifest_payload["asset_records"] == [
        {
            "index": 0,
            "path": str(fake_image),
            "kind": "image",
            "role": "carousel_item",
            "suffix": ".jpg",
            "extraction_status": "extracted",
            "errors": [],
        },
        {
            "index": 1,
            "path": str(fake_video),
            "kind": "video",
            "role": "primary_video",
            "suffix": ".mp4",
            "extraction_status": "extracted",
            "errors": [],
        },
    ]
