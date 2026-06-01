"""Deterministic acquisition adapter routing for System B."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .storage import raw_media_kind


@dataclass(frozen=True)
class AdapterDecision:
    primary: str
    fallbacks: tuple[str, ...]
    reason: str
    expected_media_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["fallbacks"] = list(self.fallbacks)
        return data


def decide_adapter(source_ref: str, source: str, *, allow_playlist: bool = False) -> AdapterDecision:
    """Return the adapter route for a source before acquisition begins."""

    raw_kind = raw_media_kind(source_ref)
    if raw_kind == "document":
        return AdapterDecision("document", (), "document file", "document")
    if raw_kind:
        return AdapterDecision("direct", (), "raw media file", raw_kind)

    if source in {"youtube", "vimeo", "loom"}:
        return AdapterDecision("yt-dlp", (), "video platform", "video")

    if source == "instagram":
        if allow_playlist:
            return AdapterDecision("gallery-dl", ("yt-dlp",), "instagram carousel/post", "carousel")
        return AdapterDecision("yt-dlp", ("gallery-dl",), "instagram reel/video", "video")

    if source in {"twitter", "reddit", "facebook"}:
        return AdapterDecision("gallery-dl", ("yt-dlp",), "social/gallery source", "video")

    if source == "threads":
        return AdapterDecision("gallery-dl", ("yt-dlp",), "meta social source", "video")

    if source == "tiktok":
        return AdapterDecision("yt-dlp", ("gallery-dl",), "short video source", "video")

    if source == "direct":
        return AdapterDecision("direct", (), "direct source", None)

    return AdapterDecision("yt-dlp", ("web-page",), "generic web page fallback", None)
