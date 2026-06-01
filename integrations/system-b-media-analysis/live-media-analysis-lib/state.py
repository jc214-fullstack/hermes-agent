"""Workspace state management for System B analysis threads."""

import json
import os
import pathlib
import time


WORKSPACE_ROOT = pathlib.Path("/home/imagi/media-analysis/threads")
INDEX_ROOT = pathlib.Path("/home/imagi/media-analysis/index")
SOURCES_INDEX = INDEX_ROOT / "sources.jsonl"
BATCHES_INDEX = INDEX_ROOT / "batches.jsonl"


# ---------------------------------------------------------------------------
# Source dedup index
# ---------------------------------------------------------------------------

def load_source_index() -> dict[str, dict]:
    """Return a dict keyed by normalized URL mapping to source records."""
    records: dict[str, dict] = {}
    if not SOURCES_INDEX.exists():
        return records
    try:
        with SOURCES_INDEX.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    key = rec.get("normalized_url") or rec.get("url", "")
                    if key:
                        records[key] = rec
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return records


def record_source(
    normalized_url: str,
    raw_url: str,
    thread_id: str,
    workspace_path: str,
    source_type: str = "unknown",
    title: str = "",
    confidence: str = "",
) -> None:
    """Append or update a source record in sources.jsonl."""
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "normalized_url": normalized_url,
        "url": raw_url,
        "thread_id": thread_id,
        "workspace_path": workspace_path,
        "source_type": source_type,
        "title": title,
        "confidence": confidence,
        "first_analyzed_at": time.time(),
        "latest_reused_at": None,
    }
    with SOURCES_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def upsert_source_record(
    normalized_url: str,
    raw_url: str,
    thread_id: str,
    workspace_path: str,
    source_type: str = "unknown",
    title: str = "",
    confidence: str = "",
    platform: str = "",
    creator: str = "",
    canonical_name: str = "",
    thread_title: str = "",
    metadata: dict | None = None,
) -> None:
    """Insert or update the durable source index record for an analyzed source.

    ``record_source`` is append-only for intake-time registration. This helper
    is for post-extraction enrichment, when title/creator/platform metadata and
    the final Discord thread/database name are known.
    """
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    now = time.time()
    records: list[dict] = []
    existing: dict | None = None

    if SOURCES_INDEX.exists():
        try:
            with SOURCES_INDEX.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = rec.get("normalized_url") or rec.get("url", "")
                    if key == normalized_url:
                        existing = rec
                    else:
                        records.append(rec)
        except OSError:
            records = []

    record = existing or {
        "normalized_url": normalized_url,
        "first_analyzed_at": now,
        "latest_reused_at": None,
    }
    record.update({
        "normalized_url": normalized_url,
        "url": raw_url,
        "thread_id": thread_id,
        "workspace_path": workspace_path,
        "source_type": source_type,
        "title": title,
        "confidence": confidence,
        "platform": platform,
        "creator": creator,
        "canonical_name": canonical_name or title or thread_title,
        "thread_title": thread_title,
        "updated_at": now,
    })
    if metadata:
        record["metadata"] = metadata

    records.append(record)
    with SOURCES_INDEX.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def mark_source_reused(normalized_url: str) -> None:
    """Rewrite sources.jsonl to update latest_reused_at for the given URL."""
    if not SOURCES_INDEX.exists():
        return
    lines: list[str] = []
    updated = False
    try:
        with SOURCES_INDEX.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    lines.append(line)
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("normalized_url") == normalized_url:
                        rec["latest_reused_at"] = time.time()
                        lines.append(json.dumps(rec, ensure_ascii=False))
                        updated = True
                        continue
                except json.JSONDecodeError:
                    pass
                lines.append(line)
    except OSError:
        return
    if updated:
        SOURCES_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Batch index
# ---------------------------------------------------------------------------

def record_batch(
    discord_message_id: str,
    channel_id: str,
    user_id: str,
    job_count: int,
    thread_ids: list[str],
) -> None:
    """Append a batch record to batches.jsonl."""
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "discord_message_id": discord_message_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "job_count": job_count,
        "thread_ids": thread_ids,
        "created_at": time.time(),
    }
    with BATCHES_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Thread workspace management
# ---------------------------------------------------------------------------

def workspace_path(thread_id: str) -> pathlib.Path:
    return WORKSPACE_ROOT / thread_id


def ensure_workspace(thread_id: str) -> pathlib.Path:
    path = workspace_path(thread_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "assets").mkdir(exist_ok=True)
    return path


def read_state(thread_id: str) -> dict:
    """Read state.json for a thread workspace. Returns {} if missing."""
    path = workspace_path(thread_id) / "state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(thread_id: str, state: dict) -> None:
    """Write state.json atomically using a temp file."""
    ws = ensure_workspace(thread_id)
    target = ws / "state.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


def init_state(
    thread_id: str,
    platform: str,
    chat_id: str,
    parent_chat_id: str,
    user_id: str,
    session_id: str,
    raw_message: str,
    urls: list[str],
    dedup_hits: dict[str, str],  # normalized_url -> existing thread_id
) -> dict:
    """Create and persist initial state for a new analysis thread."""
    state = {
        "thread_id": thread_id,
        "platform": platform,
        "chat_id": chat_id,
        "parent_chat_id": parent_chat_id,
        "user_id": user_id,
        "session_id": session_id,
        "created_at": time.time(),
        "stage": "intake",
        "urls": urls,
        "dedup_hits": dedup_hits,
        "jobs": [
            {
                "url": url,
                "normalized_url": "",  # filled by extraction adapter
                "source_type": "unknown",
                "status": "pending",
                "duplicate_of": dedup_hits.get(url),
                "artifacts": {},
            }
            for url in urls
        ],
        "error": None,
        "retry_count": 0,
    }
    write_state(thread_id, state)
    return state


def write_request_doc(
    thread_id: str,
    platform: str,
    chat_id: str,
    parent_chat_id: str,
    user_id: str,
    session_id: str,
    raw_message: str,
    urls: list[str],
    dedup_hits: dict[str, str],
    timestamp: float,
) -> None:
    """Write 00-request.md for the thread workspace."""
    ws = ensure_workspace(thread_id)
    dedup_section = ""
    if dedup_hits:
        lines = ["", "## Duplicate sources detected", ""]
        for url, prior_thread in dedup_hits.items():
            lines.append(f"- `{url}` — previously analyzed in thread `{prior_thread}`")
        dedup_section = "\n".join(lines)

    url_list = "\n".join(f"- {u}" for u in urls) if urls else "_none_"
    import datetime
    ts_str = datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")

    content = f"""# Analysis Request

## Discord metadata

- Platform: {platform}
- Channel ID: {chat_id}
- Parent channel: {parent_chat_id or "_none_"}
- User ID: {user_id}
- Session ID: {session_id}
- Timestamp: {ts_str}

## Message text

{raw_message or "_empty_"}

## Extracted URLs

{url_list}
{dedup_section}
"""
    (ws / "00-request.md").write_text(content, encoding="utf-8")
