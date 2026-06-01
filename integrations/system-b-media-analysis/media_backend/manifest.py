"""Manifest writer for System B media artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

MANIFEST_VERSION = "1"

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif", ".avif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".flv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}


def _asset_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return "image"
    if suffix in _VIDEO_EXTENSIONS:
        return "video"
    if suffix in _AUDIO_EXTENSIONS:
        return "audio"
    if suffix in _DOCUMENT_EXTENSIONS:
        return "document"
    return "unknown"


def _asset_role(path: Path, media_kind: str, primary_media_path: Path | None) -> str:
    if media_kind == "mixed_carousel":
        return "primary_video" if primary_media_path and path == primary_media_path else "carousel_item"
    if media_kind == "carousel":
        return "carousel_item"
    return "primary"


def build_asset_records(
    media_paths: list[Path],
    *,
    media_kind: str,
    primary_media_path: Path | None = None,
    extraction_status: str = "extracted",
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build v2-compatible per-asset records while v1 top-level fields remain."""

    errors = errors or []
    return [
        {
            "index": index,
            "path": str(path),
            "kind": _asset_kind(path),
            "role": _asset_role(path, media_kind, primary_media_path),
            "suffix": path.suffix.lower(),
            "extraction_status": extraction_status,
            "errors": errors if primary_media_path is None or path == primary_media_path else [],
        }
        for index, path in enumerate(media_paths)
    ]


def build_manifest_data(
    *,
    url: str,
    source: str,
    media_path: Path | None = None,
    media_paths: list[Path] | None = None,
    media_kind: str = "video",
    audio_path: Path | None = None,
    frames: list[Path] | None = None,
    metadata: dict[str, Any] | None = None,
    errors: list[str] | None = None,
    asset_records: list[dict[str, Any]] | None = None,
    transcript_path: Path | None = None,
    transcript_method: str | None = None,
    transcript_status: str = "unavailable",
    storage_plan: dict[str, Any] | None = None,
    source_storage: dict[str, Any] | None = None,
    thread_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable JSON payload consumed by Hermes/System B."""

    frames = frames or []
    media_paths = media_paths or ([media_path] if media_path else [])
    metadata = metadata or {}
    storage_plan = storage_plan or {}
    source_storage = source_storage or {}
    thread_run = thread_run or {}
    errors = errors or []
    if asset_records is None:
        asset_status = "partial" if errors else "extracted"
        if media_kind in {"image", "carousel"}:
            asset_status = "visual_only"
        elif media_kind == "document":
            asset_status = "document_only"
        asset_records = build_asset_records(
            media_paths,
            media_kind=media_kind,
            primary_media_path=media_path,
            extraction_status=asset_status,
            errors=errors,
        )

    return {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": url,
        "source": source,
        "media_kind": media_kind,
        "acquisition_method": metadata.get("_acquisition_method"),
        "storage_plan": storage_plan,
        "source_storage": source_storage,
        "thread_run": thread_run,
        "similarity_candidates": [],
        "media_path": str(media_path) if media_path else None,
        "media_paths": [str(path) for path in media_paths],
        "asset_records": asset_records,
        "video_path": str(media_path) if media_kind in {"video", "mixed_carousel"} and media_path else None,
        "audio_path": str(audio_path) if audio_path else None,
        "transcript_path": str(transcript_path) if transcript_path else None,
        "transcript_method": transcript_method,
        "transcript_status": transcript_status,
        "frames": [str(f) for f in frames],
        "frame_count": len(frames),
        "metadata": {
            "id": metadata.get("id"),
            "title": metadata.get("title"),
            "uploader": metadata.get("uploader") or metadata.get("channel"),
            "uploader_id": metadata.get("uploader_id") or metadata.get("channel_id"),
            "duration": metadata.get("duration"),
            "upload_date": metadata.get("upload_date"),
            "timestamp": metadata.get("timestamp"),
            "webpage_url": metadata.get("webpage_url"),
            "extractor": metadata.get("extractor"),
            "view_count": metadata.get("view_count"),
            "like_count": metadata.get("like_count"),
            "comment_count": metadata.get("comment_count"),
            "repost_count": metadata.get("repost_count"),
            "thumbnail": metadata.get("thumbnail"),
            "description": metadata.get("description"),
            "content_type": metadata.get("content_type"),
            "adapter_warnings": metadata.get("_adapter_warnings", []),
            "adapter_decision": metadata.get("_adapter_decision"),
        },
        "errors": errors,
    }


def write_manifest(out_dir: str | Path, data: dict[str, Any]) -> Path:
    """Write ``manifest.json`` into ``out_dir`` and return its path."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps({"version": MANIFEST_VERSION, **data}, indent=2, default=str))
    return path
