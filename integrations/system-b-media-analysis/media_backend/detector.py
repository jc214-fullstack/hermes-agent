"""Source detection for System B media URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

Source = Literal[
    "instagram",
    "tiktok",
    "youtube",
    "twitter",
    "facebook",
    "threads",
    "reddit",
    "vimeo",
    "loom",
    "direct",
    "unknown",
]

_DIRECT_EXTENSIONS = {
    ".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".flv",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif", ".avif",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md",
}

_PATTERNS: list[tuple[Source, re.Pattern[str]]] = [
    ("instagram", re.compile(r"(^|\.)instagram\.com$|(^|\.)instagr\.am$", re.I)),
    ("tiktok", re.compile(r"(^|\.)(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)$", re.I)),
    ("youtube", re.compile(r"(^|\.)(youtube\.com|youtu\.be)$", re.I)),
    ("twitter", re.compile(r"(^|\.)(twitter\.com|x\.com)$", re.I)),
    ("facebook", re.compile(r"(^|\.)(facebook\.com|fb\.watch)$", re.I)),
    ("threads", re.compile(r"(^|\.)threads\.(net|com)$", re.I)),
    ("reddit", re.compile(r"(^|\.)(reddit\.com|redd\.it|v\.redd\.it)$", re.I)),
    ("vimeo", re.compile(r"(^|\.)vimeo\.com$", re.I)),
    ("loom", re.compile(r"(^|\.)loom\.com$", re.I)),
]


@dataclass(frozen=True)
class SourceInfo:
    source: Source
    url: str
    hostname: str
    path: str


def detect(url: str) -> SourceInfo:
    """Identify the media source for a URL.

    This is deliberately conservative. Unknown sources can still be attempted
    through yt-dlp, but callers get a stable label for routing and metrics.
    """

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path or ""

    for source, pattern in _PATTERNS:
        if pattern.search(hostname):
            return SourceInfo(source=source, url=url, hostname=hostname, path=path)

    bare_path = path.lower()
    if any(bare_path.endswith(ext) for ext in _DIRECT_EXTENSIONS):
        return SourceInfo(source="direct", url=url, hostname=hostname, path=path)

    return SourceInfo(source="unknown", url=url, hostname=hostname, path=path)
