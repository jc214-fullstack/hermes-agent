from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from hermes_cli.config import load_config

logger = logging.getLogger(__name__)

_DEFAULT_REPO = Path("/home/dylan-malik/projects/ObiVault")
_DEFAULT_VAULT = Path("/home/dylan-malik/ObiVault")


def _cfg() -> dict[str, Any]:
    try:
        return ((load_config().get("sessions") or {}).get("lifecycle") or {}).get("writeback") or {}
    except Exception:
        return {}


def _enabled() -> bool:
    cfg = _cfg()
    return bool(cfg.get("enabled", False))


def _repo_root() -> Path:
    cfg = _cfg()
    raw = cfg.get("repo_root") or _DEFAULT_REPO
    return Path(raw).expanduser()


def _vault_root() -> Path:
    cfg = _cfg()
    raw = cfg.get("vault_root") or _DEFAULT_VAULT
    return Path(raw).expanduser()


def _retention() -> str:
    return str(_cfg().get("raw_retention") or "archive")


def _write_html() -> bool:
    return bool(_cfg().get("write_html", True))


def _script_path() -> Optional[Path]:
    path = _repo_root() / "scripts" / "obsidian_bolt_memory.py"
    return path if path.is_file() else None


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return ""


def _truncate(text: str, limit: int = 240) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _first_message_by_role(messages: list[Any], role: str) -> str:
    for msg in messages:
        msg_role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
        if str(msg_role or "") != role:
            continue
        text = _message_text(msg)
        if text:
            return text
    return ""


def _last_message_by_role(messages: list[Any], role: str) -> str:
    for msg in reversed(messages):
        msg_role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
        if str(msg_role or "") != role:
            continue
        text = _message_text(msg)
        if text:
            return text
    return ""


def _tail(messages: list[Any], limit: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages[-limit:]:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
        text = _message_text(msg)
        if not text:
            continue
        out.append({"role": str(role or ""), "content": text[:1600]})
    return out


def _todo_items(agent: Any) -> list[dict[str, Any]]:
    store = getattr(agent, "_todo_store", None)
    reader = getattr(store, "read", None)
    if callable(reader):
        try:
            items = reader()
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        except Exception:
            return []
    return []


def _active_todo_lines(todo_items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in todo_items:
        status = str(item.get("status") or "")
        if status not in {"pending", "in_progress"}:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(content)
    return lines


def _session_title(agent: Any, session_id: str) -> Optional[str]:
    try:
        db = getattr(agent, "_session_db", None)
        if db and session_id:
            title = db.get_session_title(session_id)
            if isinstance(title, str) and title.strip():
                return title.strip()
    except Exception:
        pass
    return None


def _derive_objective(messages: list[Any]) -> Optional[str]:
    first_user = _first_message_by_role(messages, "user")
    if first_user:
        return _truncate(first_user, limit=400)
    return None


def _derive_summary_lines(messages: list[Any], todo_lines: list[str]) -> list[str]:
    lines = [f"Conversation captured {len(messages)} messages."] if messages else []
    last_user = _last_message_by_role(messages, "user")
    if last_user:
        lines.append(f"Latest user request: {_truncate(last_user)}")
    last_assistant = _last_message_by_role(messages, "assistant")
    if last_assistant:
        lines.append(f"Latest assistant response: {_truncate(last_assistant)}")
    if todo_lines:
        lines.append(f"Active todo count at boundary: {len(todo_lines)}")
    return lines


def _source_context_from_env() -> dict[str, Any]:
    return {
        "platform": os.getenv("HERMES_SESSION_PLATFORM") or None,
        "chat_id": os.getenv("HERMES_SESSION_CHAT_ID") or None,
        "chat_name": os.getenv("HERMES_SESSION_CHAT_NAME") or None,
        "thread_id": os.getenv("HERMES_SESSION_THREAD_ID") or None,
        "user_id": os.getenv("HERMES_SESSION_USER_ID") or None,
        "user_name": os.getenv("HERMES_SESSION_USER_NAME") or None,
        "message_id": os.getenv("HERMES_SESSION_MESSAGE_ID") or None,
        "gateway_session_key": os.getenv("HERMES_SESSION_KEY") or None,
    }


def _source_context_from_agent(agent: Any) -> dict[str, Any]:
    env = _source_context_from_env()
    return {
        "platform": getattr(agent, "platform", None) or env.get("platform"),
        "chat_id": getattr(agent, "_chat_id", None) or env.get("chat_id"),
        "chat_name": getattr(agent, "_chat_name", None) or env.get("chat_name"),
        "chat_type": getattr(agent, "_chat_type", None),
        "thread_id": getattr(agent, "_thread_id", None) or env.get("thread_id"),
        "user_id": getattr(agent, "_user_id", None) or env.get("user_id"),
        "user_name": getattr(agent, "_user_name", None) or env.get("user_name"),
        "guild_id": getattr(agent, "_guild_id", None),
        "parent_chat_id": getattr(agent, "_parent_chat_id", None),
        "message_id": getattr(agent, "_message_id", None) or env.get("message_id"),
        "gateway_session_key": getattr(agent, "_gateway_session_key", None) or env.get("gateway_session_key"),
    }


def _effective_container_id(source_context: dict[str, Any], session_id: str) -> str:
    return str(
        source_context.get("thread_id")
        or source_context.get("chat_id")
        or source_context.get("gateway_session_key")
        or session_id
        or "unknown-session"
    )


def build_payload(
    *,
    agent: Any,
    messages: list[Any],
    boundary_reason: str,
    session_id: str,
    parent_session_id: Optional[str] = None,
    source_override: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    source_context = source_override or _source_context_from_agent(agent)
    todo_items = _todo_items(agent)
    todo_lines = _active_todo_lines(todo_items)
    title = _session_title(agent, session_id)
    objective = _derive_objective(messages)
    summary_lines = _derive_summary_lines(messages, todo_lines)
    payload = {
        "agent": "Hermes-J214",
        "platform": source_context.get("platform"),
        "chat_id": source_context.get("chat_id"),
        "parent_channel_id": source_context.get("parent_chat_id"),
        "thread_id": source_context.get("thread_id"),
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "boundary_reason": boundary_reason,
        "effective_container_id": _effective_container_id(source_context, session_id),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "title": title,
        "summary_title": title or _truncate(objective or "Hermes session", limit=120),
        "objective": objective,
        "summary": summary_lines[0] if summary_lines else None,
        "what_happened": summary_lines,
        "source_context": source_context,
        "source": {
            "transcript_session_id": session_id,
            "message_count": len(messages),
            "recent_messages": _tail(messages),
        },
        "state": {
            "todo_snapshot": getattr(getattr(agent, "_todo_store", None), "format_for_injection", lambda: "")(),
            "todo_state": todo_items,
            "session_title": title,
            "open_loops": todo_lines,
            "next_steps": todo_lines[:1],
            "key_decisions": [],
            "files_touched": [],
            "repos_touched": [],
            "blockers": [],
            "artifacts": [],
        },
    }
    if metadata:
        payload.update(metadata)
    return payload


def _invoke(command: str, payload: dict[str, Any]) -> None:
    if not _enabled():
        return
    script = _script_path()
    if script is None:
        logger.debug("session lifecycle writeback skipped: obsidian_bolt_memory.py missing")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp = fh.name
    cmd = [
        sys.executable,
        str(script),
        command,
        "--vault-root",
        str(_vault_root()),
        "--payload-file",
        tmp,
    ]
    if command == "finalize-session":
        cmd.extend(["--raw-retention", _retention()])
        if not _write_html():
            cmd.append("--no-html")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.warning(
                "session lifecycle writeback failed (%s): %s %s",
                command,
                (proc.stdout or "").strip(),
                (proc.stderr or "").strip(),
            )
    except Exception as exc:
        logger.warning("session lifecycle writeback error (%s): %s", command, exc)
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


def checkpoint_from_compression(
    *,
    agent: Any,
    old_session_id: str,
    new_session_id: str,
    original_messages: list[Any],
    compressed_messages: list[Any],
) -> None:
    payload = build_payload(
        agent=agent,
        messages=original_messages,
        boundary_reason="compression",
        session_id=old_session_id,
        parent_session_id=None,
        metadata={
            "compression": {
                "new_session_id": new_session_id,
                "pre_message_count": len(original_messages),
                "post_message_count": len(compressed_messages),
                "compressed_tail": _tail(compressed_messages),
            },
            "source": {
                "transcript_session_id": old_session_id,
                "last_compaction_count": len(original_messages),
                "message_count": len(original_messages),
                "recent_messages": _tail(original_messages),
            },
        },
    )
    _invoke("session-raw-checkpoint", payload)


def finalize_session(
    *,
    agent: Any,
    session_id: str,
    boundary_reason: str,
    messages: list[Any],
    parent_session_id: Optional[str] = None,
    source_override: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    payload = build_payload(
        agent=agent,
        messages=messages,
        boundary_reason=boundary_reason,
        session_id=session_id,
        parent_session_id=parent_session_id,
        source_override=source_override,
        metadata=metadata,
    )
    _invoke("finalize-session", payload)
