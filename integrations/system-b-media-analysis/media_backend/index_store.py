"""Reader helpers for the System B JSONL source index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SOURCES_INDEX = Path("/home/imagi/media-analysis/index/sources.jsonl")


def load_sources(path: Path = DEFAULT_SOURCES_INDEX) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    except OSError:
        return []
    return records


def _record_time(record: dict[str, Any]) -> float:
    for key in ("updated_at", "extracted_at", "first_analyzed_at", "created_at"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def list_recent(limit: int = 20, *, path: Path = DEFAULT_SOURCES_INDEX) -> list[dict[str, Any]]:
    return sorted(load_sources(path), key=_record_time, reverse=True)[:limit]


def find_source(query: str, *, path: Path = DEFAULT_SOURCES_INDEX) -> dict[str, Any] | None:
    for record in load_sources(path):
        keys = {
            str(record.get("source_key") or ""),
            str(record.get("normalized_url") or ""),
            str(record.get("url") or ""),
        }
        if query in keys:
            return record
    return None


def find_by_thread(thread_id: str, *, path: Path = DEFAULT_SOURCES_INDEX) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in load_sources(path):
        thread_ids = record.get("thread_ids") or []
        if (
            record.get("thread_id") == thread_id
            or record.get("latest_thread_id") == thread_id
            or thread_id in thread_ids
        ):
            matches.append(record)
    return matches


def list_failures(limit: int = 20, *, path: Path = DEFAULT_SOURCES_INDEX) -> list[dict[str, Any]]:
    failures = []
    for record in load_sources(path):
        status = str(record.get("status") or "").lower()
        if status in {"error", "failed"} or record.get("error") or record.get("errors"):
            failures.append(record)
    return sorted(failures, key=_record_time, reverse=True)[:limit]
