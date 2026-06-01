"""Source storage planning for System B media artifacts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_RAW_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".flv"}
_RAW_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_RAW_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif", ".avif"}
_RAW_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}

_COMPANY_PLATFORM_PATHS = {
    "youtube": (None, "youtube"),
    "instagram": ("meta", "instagram"),
    "facebook": ("meta", "facebook"),
    "threads": ("meta", "threads"),
    "tiktok": (None, "tiktok"),
    "twitter": (None, "x"),
    "reddit": (None, "reddit"),
    "bluesky": (None, "bluesky"),
    "vimeo": (None, "vimeo"),
    "loom": (None, "loom"),
}


@dataclass(frozen=True)
class StoragePlan:
    """Resolved storage location for a source without implying URL dedupe."""

    source_ref: str
    source: str
    source_key: str
    storage_class: str
    relative_dir: Path
    company: str | None = None
    platform: str | None = None
    raw_kind: str | None = None


def short_ref_hash(source_ref: str, length: int = 12) -> str:
    return hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:length]


def slugify(value: str, *, fallback: str = "source") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or fallback


def raw_media_kind(path_or_url: str) -> str | None:
    """Return raw media kind for direct files/URLs, or None if not raw media."""

    parsed = urlparse(path_or_url)
    suffix = Path(parsed.path or path_or_url).suffix.lower()
    if suffix in _RAW_VIDEO_EXTENSIONS:
        return "video"
    if suffix in _RAW_AUDIO_EXTENSIONS:
        return "audio"
    if suffix in _RAW_IMAGE_EXTENSIONS:
        return "image"
    if suffix in _RAW_DOCUMENT_EXTENSIONS:
        return "document"
    return None


def platform_company_path(source: str) -> tuple[str | None, str]:
    """Map platform source to company/platform path components."""

    return _COMPANY_PLATFORM_PATHS.get(source, (None, slugify(source, fallback="unknown")))


def _url_source_id(source_ref: str, source: str) -> str | None:
    parsed = urlparse(source_ref)
    path_parts = [part for part in (parsed.path or "").split("/") if part]
    if source == "youtube":
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id:
            return f"youtube-{query_id}"
        if parsed.hostname and parsed.hostname.endswith("youtu.be") and path_parts:
            return f"youtube-{path_parts[0]}"
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed"}:
            return f"youtube-{path_parts[1]}"
    if source == "instagram" and len(path_parts) >= 2 and path_parts[0] in {"reel", "p", "tv"}:
        return f"instagram-{path_parts[0]}-{path_parts[1]}"
    if source == "facebook" and path_parts:
        return f"facebook-{path_parts[-1]}"
    if source == "threads" and path_parts:
        return f"threads-{path_parts[-1]}"
    if source in {"tiktok", "twitter", "reddit", "vimeo", "loom"} and path_parts:
        return f"{source}-{path_parts[-1]}"
    if raw_media_kind(source_ref):
        stem = Path(parsed.path or source_ref).stem
        if stem:
            return stem
    return None


def plan_storage(source_ref: str, source: str, *, source_id: str | None = None) -> StoragePlan:
    """Plan where a source should live in the durable source tree.

    This intentionally does not dedupe. Repeated URLs can get their own request
    workspaces, while later analysis can compare semantic similarity.
    """

    raw_kind = raw_media_kind(source_ref)
    stable_id = slugify(source_id or _url_source_id(source_ref, source) or short_ref_hash(source_ref), fallback="source")
    if source == "direct" or raw_kind:
        kind = raw_kind or "unknown"
        return StoragePlan(
            source_ref=source_ref,
            source=source,
            source_key=stable_id,
            storage_class="raw-file",
            raw_kind=kind,
            relative_dir=Path("raw-files") / kind / stable_id,
        )

    if source == "unknown":
        return StoragePlan(
            source_ref=source_ref,
            source=source,
            source_key=stable_id,
            storage_class="web",
            relative_dir=Path("web") / "generic" / stable_id,
        )

    company, platform = platform_company_path(source)
    platform_dir = Path("platform") / platform
    if company:
        platform_dir = Path("platform") / company / platform
    return StoragePlan(
        source_ref=source_ref,
        source=source,
        source_key=stable_id,
        storage_class="platform",
        company=company,
        platform=platform,
        relative_dir=platform_dir / stable_id,
    )
