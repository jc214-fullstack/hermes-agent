"""Media acquisition using free/local adapters.

System B intentionally does not use Apify or paid hosted scraper actors. This
module routes direct raw media through a raw-file path, video-first URLs through
yt-dlp, and social/image/carousel-style sources through gallery-dl.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .adapters import AdapterDecision, decide_adapter
from .detector import detect
from .storage import raw_media_kind

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".flv"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif", ".avif"}
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}
_MEDIA_EXTENSIONS = _VIDEO_EXTENSIONS | _AUDIO_EXTENSIONS | _IMAGE_EXTENSIONS | _DOCUMENT_EXTENSIONS
class DownloadError(Exception):
    """Raised when media download or metadata capture fails."""


def _new_media_files(out_dir: Path, before: set[Path]) -> list[Path]:
    candidates = []
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() in before and path.suffix != ".part":
            continue
        if path.name.endswith(".info.json") or path.name.endswith(".metadata.json"):
            continue
        if path.suffix.lower() in {".json", ".jsonl", ".part", ".ytdl"}:
            continue
        if path.suffix.lower() not in _MEDIA_EXTENSIONS:
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda p: str(p))


def _primary_media(media_candidates: list[Path]) -> Path:
    if not media_candidates:
        raise DownloadError("download succeeded but no output media file was found.")
    video_candidates = [p for p in media_candidates if p.suffix.lower() in _VIDEO_EXTENSIONS]
    image_candidates = [p for p in media_candidates if p.suffix.lower() in _IMAGE_EXTENSIONS]
    ordered = video_candidates or image_candidates or media_candidates
    return sorted(ordered, key=lambda p: str(p))[0]


def _load_latest_json(out_dir: Path, patterns: tuple[str, ...]) -> dict:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(out_dir.rglob(pattern))
    files = sorted(files, key=lambda p: p.stat().st_mtime)
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _download_direct(source_ref: str, out_dir: Path) -> tuple[Path, dict]:
    parsed = urlparse(source_ref)
    out_dir.mkdir(parents=True, exist_ok=True)

    if parsed.scheme in {"http", "https"}:
        suffix = Path(parsed.path).suffix or ".bin"
        target = out_dir / f"raw-source{suffix.lower()}"
        try:
            with urllib.request.urlopen(source_ref, timeout=60) as response:
                target.write_bytes(response.read())
                content_type = response.headers.get("Content-Type")
        except Exception as exc:  # pragma: no cover - network failure details vary
            raise DownloadError(f"direct media download failed: {exc}") from exc
    else:
        source_path = Path(source_ref).expanduser()
        if not source_path.exists() or not source_path.is_file():
            raise DownloadError(f"direct media file not found: {source_path}")
        target = out_dir / source_path.name
        if source_path.resolve() != target.resolve():
            shutil.copy2(source_path, target)
        content_type = None

    metadata = {
        "id": target.stem,
        "title": target.stem,
        "extractor": "direct",
        "webpage_url": source_ref,
        "content_type": content_type,
        "_acquisition_method": "direct",
        "_downloaded_media_paths": [str(target)],
    }
    return target, metadata


def _attach_decision(metadata: dict, decision: AdapterDecision) -> dict:
    metadata["_adapter_decision"] = decision.to_dict()
    return metadata


def _download_ytdlp(url: str, out_dir: Path, *, allow_playlist: bool = False) -> tuple[Path, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.resolve() for p in out_dir.rglob("*") if p.is_file()}
    template = str(out_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--restrict-filenames",
        "--write-info-json",
        "--no-progress",
        "-o",
        template,
        url,
    ]
    if not allow_playlist:
        cmd.insert(1, "--no-playlist")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(f"yt-dlp exited {result.returncode}:\n{result.stderr.strip()}")

    metadata = _load_latest_json(out_dir, ("*.info.json",))
    media_candidates = _new_media_files(out_dir, before)
    if not media_candidates:
        media_candidates = _new_media_files(out_dir, set())
    primary_media = _primary_media(media_candidates)
    metadata["_acquisition_method"] = "yt-dlp"
    metadata["_downloaded_media_paths"] = [str(p) for p in media_candidates]
    return primary_media, metadata


def _download_gallery_dl(url: str, out_dir: Path) -> tuple[Path, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.resolve() for p in out_dir.rglob("*") if p.is_file()}
    metadata_dir = out_dir / "metadata"

    cmd = [
        "gallery-dl",
        "--no-progress",
        "--directory",
        str(out_dir),
        "--write-metadata",
        "--write-info-json",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownloadError(f"gallery-dl exited {result.returncode}:\n{result.stderr.strip()}")

    metadata = _load_latest_json(out_dir, ("*.json", "*.metadata.json", "metadata/*.json"))
    media_candidates = _new_media_files(out_dir, before)
    if not media_candidates:
        media_candidates = _new_media_files(out_dir, set())
    primary_media = _primary_media(media_candidates)
    metadata["_acquisition_method"] = "gallery-dl"
    metadata["_downloaded_media_paths"] = [str(p) for p in media_candidates]
    metadata["_gallery_dl_metadata_dir"] = str(metadata_dir)
    return primary_media, metadata


def download(url: str, out_dir: str | Path, *, allow_playlist: bool = False) -> tuple[Path, dict]:
    """Acquire media into out_dir using direct, yt-dlp, or gallery-dl.

    Returns ``(primary_media_path, metadata_dict)``. Metadata includes
    ``_downloaded_media_paths`` and ``_acquisition_method``.
    """

    out_dir = Path(out_dir)
    source_info = detect(url)
    decision = decide_adapter(url, source_info.source, allow_playlist=allow_playlist)

    if decision.primary in {"direct", "document"}:
        primary, metadata = _download_direct(url, out_dir)
        if decision.primary == "document":
            metadata["_acquisition_method"] = "document"
            metadata["extractor"] = "document"
        return primary, _attach_decision(metadata, decision)

    if decision.primary == "web-page":
        raise DownloadError("web-page adapter unsupported: no media extractor is available for generic web pages yet")

    adapter_errors: list[tuple[str, DownloadError]] = []
    adapters = (decision.primary, *decision.fallbacks)
    for index, adapter in enumerate(adapters):
        try:
            if adapter == "gallery-dl":
                primary, metadata = _download_gallery_dl(url, out_dir / "gallery-dl")
            elif adapter == "yt-dlp":
                adapter_dir = out_dir if index == 0 else out_dir / "yt-dlp"
                primary, metadata = _download_ytdlp(url, adapter_dir, allow_playlist=allow_playlist)
            elif adapter == "web-page":
                raise DownloadError("web-page adapter unsupported: no media extractor is available for generic web pages yet")
            else:
                raise DownloadError(f"unsupported adapter route: {adapter}")
            for failed_adapter, error in adapter_errors:
                metadata.setdefault("_adapter_warnings", []).append(f"{failed_adapter}: {error}")
            return primary, _attach_decision(metadata, decision)
        except DownloadError as exc:
            adapter_errors.append((adapter, exc))

    failures = "\n".join(f"{adapter} failed: {error}" for adapter, error in adapter_errors)
    raise DownloadError(f"adapter acquisition failed:\n{failures}")
