"""
System B intake hook — agent:start

Fires before every agent turn. Checks whether this turn belongs to the
Discord media-analysis channel (1509517024345194617) and contains URLs.
When it does, the hook pre-creates the thread workspace, writes 00-request.md
and state.json, and checks the dedup index.

The agent (guided by the discord-media-analysis skill) then handles extraction
and analysis. If the source is a known duplicate the workspace contains a
dedup_hits record so the agent can link back to the prior thread instead of
re-running full analysis.

No gateway internals are modified here — this hook only touches the filesystem.
"""

import sys
import time
from pathlib import Path

# Allow imports from the media-analysis lib directory
_LIB = Path("/home/imagi/media-analysis/lib")
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from url_norm import extract_urls, normalize_url  # type: ignore[import]
from state import (  # type: ignore[import]
    init_state,
    load_source_index,
    record_batch,
    record_source,
    write_request_doc,
)

MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"


def _is_media_analysis_event(context: dict) -> bool:
    """Return True when this agent turn is in the media-analysis lane."""
    if context.get("platform") != "discord":
        return False
    chat_id = context.get("chat_id", "")
    parent_chat_id = context.get("parent_chat_id", "")
    return chat_id == MEDIA_ANALYSIS_CHANNEL or parent_chat_id == MEDIA_ANALYSIS_CHANNEL


async def handle(event_type: str, context: dict) -> None:
    """Pre-create System B workspace when a URL lands in the media-analysis channel."""
    if not _is_media_analysis_event(context):
        return

    message = context.get("message", "")
    urls = extract_urls(message)
    if not urls:
        return

    chat_id = context.get("chat_id", "")
    parent_chat_id = context.get("parent_chat_id", "")
    user_id = context.get("user_id", "")
    session_id = context.get("session_id", "")

    # Workspace key: prefer the thread ID (chat_id) over the parent channel.
    # When the agent runs in a thread, chat_id IS the thread ID.
    thread_id = chat_id if chat_id != MEDIA_ANALYSIS_CHANNEL else session_id

    # Dedup check
    source_index = load_source_index()
    dedup_hits: dict[str, str] = {}
    for raw_url in urls:
        norm = normalize_url(raw_url)
        prior = source_index.get(norm)
        if prior:
            dedup_hits[raw_url] = prior.get("thread_id", "")

    ts = time.time()

    # Write workspace state
    try:
        state = init_state(
            thread_id=thread_id,
            platform="discord",
            chat_id=chat_id,
            parent_chat_id=parent_chat_id,
            user_id=user_id,
            session_id=session_id,
            raw_message=message,
            urls=urls,
            dedup_hits=dedup_hits,
        )
        # Default title contract for downstream thread naming.
        # If metadata extraction later discovers a creator/uploader, it should
        # overwrite this suggestion with "video by <creator>" (+ numeric suffix).
        state["thread_title_base"] = "video by whoever"
        state["thread_title_suggestion"] = "video by whoever"
        state["thread_title_source"] = "intake_default"
        from state import write_state  # type: ignore[import]
        write_state(thread_id, state)
        write_request_doc(
            thread_id=thread_id,
            platform="discord",
            chat_id=chat_id,
            parent_chat_id=parent_chat_id,
            user_id=user_id,
            session_id=session_id,
            raw_message=message,
            urls=urls,
            dedup_hits=dedup_hits,
            timestamp=ts,
        )
    except Exception as exc:
        print(
            f"[media-analysis-intake] workspace init failed for thread {thread_id}: {exc}",
            flush=True,
        )
        return

    # Register new sources (non-duplicates) in the index
    for raw_url in urls:
        norm = normalize_url(raw_url)
        if norm not in source_index:
            try:
                record_source(
                    normalized_url=norm,
                    raw_url=raw_url,
                    thread_id=thread_id,
                    workspace_path=str(Path("/home/imagi/media-analysis/threads") / thread_id),
                )
            except Exception as exc:
                print(
                    f"[media-analysis-intake] failed to record source {raw_url}: {exc}",
                    flush=True,
                )

    # Record batch entry (one per agent turn / Discord message)
    try:
        record_batch(
            discord_message_id=session_id,
            channel_id=chat_id,
            user_id=user_id,
            job_count=len(urls),
            thread_ids=[thread_id],
        )
    except Exception as exc:
        print(
            f"[media-analysis-intake] failed to record batch: {exc}",
            flush=True,
        )

    n_dupes = len(dedup_hits)
    n_new = len(urls) - n_dupes
    print(
        f"[media-analysis-intake] thread={thread_id} urls={len(urls)} "
        f"new={n_new} dupes={n_dupes}",
        flush=True,
    )
