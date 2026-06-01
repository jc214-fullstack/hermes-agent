import json
from pathlib import Path

from media_backend.manifest import MANIFEST_VERSION, build_asset_records, build_manifest_data, write_manifest


def test_write_manifest_creates_file(tmp_path):
    path = write_manifest(tmp_path, {"url": "https://example.com", "source": "instagram"})

    assert path == tmp_path / "manifest.json"
    content = json.loads(path.read_text())
    assert content["version"] == MANIFEST_VERSION
    assert content["url"] == "https://example.com"
    assert content["source"] == "instagram"


def test_write_manifest_creates_nested_dir(tmp_path):
    nested = tmp_path / "nested" / "dir"
    write_manifest(nested, {"url": "x", "source": "unknown"})
    assert (nested / "manifest.json").exists()


def test_build_manifest_data_full():
    data = build_manifest_data(
        url="https://instagram.com/reel/abc/",
        source="instagram",
        media_path=Path("/out/abc.mp4"),
        media_paths=[Path("/out/abc.mp4")],
        media_kind="video",
        audio_path=Path("/out/abc-analysis/audio.wav"),
        frames=[Path("/out/abc-analysis/frames/frame-001.jpg"), Path("/out/abc-analysis/frames/frame-002.jpg")],
        metadata={
            "id": "abc",
            "title": "Test",
            "uploader": "user",
            "duration": 30,
            "view_count": 100,
            "thumbnail": "https://example.com/thumb.jpg",
            "_adapter_decision": {
                "primary": "yt-dlp",
                "fallbacks": [],
                "reason": "video platform",
                "expected_media_kind": "video",
            },
        },
        errors=[],
        transcript_path=Path("/out/02b-stt-transcript.md"),
        transcript_method="faster-whisper",
        transcript_status="stt_complete",
        source_storage={
            "source_key": "ig-abc",
            "source_dir": "/sources/platform/meta/instagram/ig-abc",
            "storage_class": "platform",
            "platform": "instagram",
            "company": "meta",
            "raw_kind": None,
        },
        thread_run={
            "thread_id": "thread-1",
            "workspace_path": "/threads/thread-1",
            "job_index": 0,
        },
    )

    assert data["url"] == "https://instagram.com/reel/abc/"
    assert data["source"] == "instagram"
    assert data["media_kind"] == "video"
    assert data["acquisition_method"] is None
    assert data["storage_plan"] == {}
    assert data["source_storage"]["source_key"] == "ig-abc"
    assert data["thread_run"]["thread_id"] == "thread-1"
    assert data["similarity_candidates"] == []
    assert data["media_path"] == "/out/abc.mp4"
    assert data["media_paths"] == ["/out/abc.mp4"]
    assert data["video_path"] == "/out/abc.mp4"
    assert data["audio_path"] == "/out/abc-analysis/audio.wav"
    assert data["transcript_path"] == "/out/02b-stt-transcript.md"
    assert data["transcript_method"] == "faster-whisper"
    assert data["transcript_status"] == "stt_complete"
    assert data["frame_count"] == 2
    assert data["metadata"]["id"] == "abc"
    assert data["metadata"]["duration"] == 30
    assert data["metadata"]["view_count"] == 100
    assert data["metadata"]["adapter_decision"]["primary"] == "yt-dlp"
    assert data["errors"] == []
    assert data["asset_records"] == [
        {
            "index": 0,
            "path": "/out/abc.mp4",
            "kind": "video",
            "role": "primary",
            "suffix": ".mp4",
            "extraction_status": "extracted",
            "errors": [],
        }
    ]


def test_build_manifest_data_partial():
    data = build_manifest_data(
        url="https://tiktok.com/@user/video/123",
        source="tiktok",
        media_path=Path("/out/123.mp4"),
        media_kind="video",
        audio_path=None,
        frames=[],
        metadata={},
        errors=["ffmpeg audio failed"],
    )

    assert data["audio_path"] is None
    assert data["frame_count"] == 0
    assert data["errors"] == ["ffmpeg audio failed"]
    assert data["metadata"]["id"] is None


def test_build_manifest_data_visual_carousel():
    data = build_manifest_data(
        url="https://instagram.com/p/abc/",
        source="instagram",
        media_path=Path("/out/post-1.jpg"),
        media_paths=[Path("/out/post-1.jpg"), Path("/out/post-2.jpg")],
        media_kind="carousel",
        frames=[Path("/out/post-1.jpg"), Path("/out/post-2.jpg")],
        metadata={"id": "abc"},
        errors=[],
        transcript_status="visual_only",
    )

    assert data["media_kind"] == "carousel"
    assert data["media_path"] == "/out/post-1.jpg"
    assert data["media_paths"] == ["/out/post-1.jpg", "/out/post-2.jpg"]
    assert data["video_path"] is None
    assert data["frame_count"] == 2
    assert data["transcript_status"] == "visual_only"
    assert data["asset_records"] == [
        {
            "index": 0,
            "path": "/out/post-1.jpg",
            "kind": "image",
            "role": "carousel_item",
            "suffix": ".jpg",
            "extraction_status": "visual_only",
            "errors": [],
        },
        {
            "index": 1,
            "path": "/out/post-2.jpg",
            "kind": "image",
            "role": "carousel_item",
            "suffix": ".jpg",
            "extraction_status": "visual_only",
            "errors": [],
        },
    ]


def test_build_asset_records_mixed_carousel_marks_primary_video():
    image = Path("/out/post-1.jpg")
    video = Path("/out/post-2.mp4")

    records = build_asset_records(
        [image, video],
        media_kind="mixed_carousel",
        primary_media_path=video,
        extraction_status="partial",
        errors=["frame extraction failed"],
    )

    assert records == [
        {
            "index": 0,
            "path": "/out/post-1.jpg",
            "kind": "image",
            "role": "carousel_item",
            "suffix": ".jpg",
            "extraction_status": "partial",
            "errors": [],
        },
        {
            "index": 1,
            "path": "/out/post-2.mp4",
            "kind": "video",
            "role": "primary_video",
            "suffix": ".mp4",
            "extraction_status": "partial",
            "errors": ["frame extraction failed"],
        },
    ]
