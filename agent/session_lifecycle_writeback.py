from __future__ import annotations

import json
import logging
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


def _tail(messages: list[Any], limit: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages[-limit:]:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
        text = _message_text(msg)
        if not text:
            continue
        out.append({"role": str(role or ""), "content": text[:1600]})
    return out


def _source_context_from_agent(agent: Any) -> dict[str, Any]:
    return {
        "platform": getattr(agent, "platform", None),
        "chat_id": getattr(agent, "_chat_id", None),
        "chat_name": getattr(agent, "_chat_name", None),
        "chat_type": getattr(agent, "_chat_type", None),
        "thread_id": getattr(agent, "_thread_id", None),
        "user_id": getattr(agent, "_user_id", None),
        "user_name": getattr(agent, "_user_name", None),
        "gateway_session_key": getattr(agent, "_gateway_session_key", None),
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
    payload = {
        "agent": "Hermes-J214",
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "boundary_reason": boundary_reason,
        "effective_container_id": _effective_container_id(source_context, session_id),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source_context": source_context,
        "source": {
            "message_count": len(messages),
            "recent_messages": _tail(messages),
        },
        "state": {
            "todo_snapshot": getattr(getattr(agent, "_todo_store", None), "format_for_injection", lambda: "")(),
            "session_title": None,
        },
    }
    try:
        db = getattr(agent, "_session_db", None)
        if db and session_id:
            payload["state"]["session_title"] = db.get_session_title(session_id)
    except Exception:
        pass
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
            }
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
