"""Command-line entry point for the System B media backend."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .detector import detect
from .downloader import DownloadError, download
from .extractor import (
    ExtractionError,
    TranscriptionError,
    extract_audio,
    extract_frames,
    transcribe_audio,
)
from .manifest import build_manifest_data, write_manifest
from .storage import plan_storage

DEFAULT_SOURCE_ROOT = Path("/home/imagi/media-analysis/sources")

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif", ".avif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".flv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}


def _media_kind(paths: list[Path]) -> str:
    if len(paths) > 1 and all(path.suffix.lower() in _IMAGE_EXTENSIONS for path in paths):
        return "carousel"
    if paths and all(path.suffix.lower() in _IMAGE_EXTENSIONS for path in paths):
        return "image"
    if paths and all(path.suffix.lower() in _AUDIO_EXTENSIONS for path in paths):
        return "audio"
    if paths and all(path.suffix.lower() in _DOCUMENT_EXTENSIONS for path in paths):
        return "document"
    if len(paths) > 1:
        return "mixed_carousel"
    return "video"


def _allows_carousel_download(source: str, url_path: str) -> bool:
    return source == "instagram" and any(segment in url_path.lower() for segment in ("/p/", "/carousel/"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="media-dl",
        description="Identify a media URL source, download it, and prepare local System B artifacts.",
    )
    parser.add_argument("url", help="Media URL to download")
    parser.add_argument("output_dir", help="Directory to write source media, artifacts, and manifest")
    parser.add_argument(
        "--source-root",
        default=str(DEFAULT_SOURCE_ROOT),
        help="Durable source storage root (default: /home/imagi/media-analysis/sources)",
    )
    parser.add_argument(
        "--frame-interval",
        type=int,
        default=8,
        metavar="SECONDS",
        help="Seconds between sampled frames (default: 8)",
    )
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio.wav extraction")
    parser.add_argument("--skip-transcript", action="store_true", help="Skip local faster-whisper STT")
    parser.add_argument("--skip-frames", action="store_true", help="Skip frame sampling")
    return parser


def _thread_run_data(out_dir: Path) -> dict[str, object]:
    thread_id = out_dir.name
    job_index = 0
    if out_dir.parent.name == "assets":
        thread_id = out_dir.parent.parent.name
        if out_dir.name.startswith("source-"):
            try:
                job_index = max(0, int(out_dir.name.split("-", 1)[1]) - 1)
            except ValueError:
                job_index = 0
    return {
        "thread_id": thread_id,
        "workspace_path": str(out_dir if out_dir.parent.name != "assets" else out_dir.parent.parent),
        "job_index": job_index,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    source_root = Path(args.source_root)
    source_info = detect(args.url)
    storage_plan = plan_storage(args.url, source_info.source)
    source_dir = source_root / storage_plan.relative_dir
    source_assets_dir = source_dir / "assets"
    errors: list[str] = []

    print(f"source: {source_info.source}", file=sys.stderr)
    print(f"storage: {storage_plan.relative_dir}", file=sys.stderr)

    try:
        allow_playlist = _allows_carousel_download(source_info.source, source_info.path)
        media_path, metadata = download(args.url, source_assets_dir, allow_playlist=allow_playlist)
    except DownloadError as exc:
        print(f"ERROR download: {exc}", file=sys.stderr)
        return 1

    media_paths = [Path(path) for path in metadata.get("_downloaded_media_paths", [])] or [media_path]
    kind = _media_kind(media_paths)
    is_visual_only = kind in {"image", "carousel", "document"}
    is_audio_only = kind == "audio"

    print(f"media: {media_path}", file=sys.stderr)
    print(f"media_kind: {kind}", file=sys.stderr)
    artifact_dir = source_assets_dir / f"{media_path.stem}-analysis"

    audio_path: Path | None = None
    transcript_path: Path | None = None
    transcript_status = "unavailable"
    transcript_method: str | None = None
    frames: list[Path] = []

    if is_visual_only:
        frames = media_paths if kind != "document" else []
        transcript_status = "visual_only" if kind != "document" else "document_only"
        print(f"visual_assets: {len(frames)}", file=sys.stderr)
    elif is_audio_only:
        audio_path = media_path
        print(f"audio: {audio_path}", file=sys.stderr)
    elif not args.skip_audio:
        try:
            audio_path = extract_audio(media_path, artifact_dir)
            print(f"audio: {audio_path}", file=sys.stderr)
        except ExtractionError as exc:
            errors.append(str(exc))
            print(f"WARN audio: {exc}", file=sys.stderr)

    if audio_path and not args.skip_transcript:
        try:
            transcript_path = transcribe_audio(audio_path, source_assets_dir)
            transcript_status = "stt_complete"
            transcript_method = "faster-whisper"
            print(f"transcript: {transcript_path}", file=sys.stderr)
        except TranscriptionError as exc:
            transcript_status = "stt_failed"
            transcript_method = "faster-whisper"
            errors.append(str(exc))
            print(f"WARN transcript: {exc}", file=sys.stderr)
    elif audio_path and args.skip_transcript:
        transcript_status = "skipped"

    if not args.skip_frames and not is_visual_only:
        try:
            frames = extract_frames(media_path, artifact_dir, interval=args.frame_interval)
            print(f"frames: {len(frames)}", file=sys.stderr)
        except (ExtractionError, ValueError) as exc:
            errors.append(str(exc))
            print(f"WARN frames: {exc}", file=sys.stderr)

    manifest_data = build_manifest_data(
        url=args.url,
        source=source_info.source,
        media_path=media_path,
        media_paths=media_paths,
        media_kind=kind,
        audio_path=audio_path,
        frames=frames,
        metadata=metadata,
        errors=errors,
        transcript_path=transcript_path,
        transcript_method=transcript_method,
        transcript_status=transcript_status,
        storage_plan={
            "storage_class": storage_plan.storage_class,
            "relative_dir": str(storage_plan.relative_dir),
            "company": storage_plan.company,
            "platform": storage_plan.platform,
            "raw_kind": storage_plan.raw_kind,
        },
        source_storage={
            "source_key": storage_plan.source_key,
            "source_dir": str(source_dir),
            "storage_class": storage_plan.storage_class,
            "platform": storage_plan.platform,
            "company": storage_plan.company,
            "raw_kind": storage_plan.raw_kind,
        },
        thread_run=_thread_run_data(out_dir),
    )
    manifest_path = write_manifest(out_dir, manifest_data)
    print(f"manifest: {manifest_path}", file=sys.stderr)
    print(str(manifest_path))
    return 0


def entry_point() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entry_point()
