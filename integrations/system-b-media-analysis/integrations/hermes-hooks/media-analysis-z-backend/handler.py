"""
System B backend hook — agent:start

This hook runs after media-analysis-intake and connects the thread workspace to
jc214-fullstack/instagram-reel-analyzer's native Python backend. It does not
modify Hermes gateway internals and does not post to Discord directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"
BACKEND_REPO = Path("/home/imagi/projects/instagram-reel-analyzer")
WORKSPACE_ROOT = Path("/home/imagi/media-analysis/threads")
TIMEOUT_SECONDS = int(os.environ.get("SYSTEM_B_BACKEND_TIMEOUT", "300"))
FRAME_INTERVAL_SECONDS = int(os.environ.get("SYSTEM_B_FRAME_INTERVAL", "2"))

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
_LIVE_LIB = Path("/home/imagi/media-analysis/lib")
for _LIB in (_LIVE_LIB, _LOCAL_LIB):
    if _LIB.exists():
        if str(_LIB) in sys.path:
            sys.path.remove(str(_LIB))
        sys.path.insert(0, str(_LIB))

from url_norm import extract_urls, normalize_url  # type: ignore[import]
from state import ensure_workspace, read_state, upsert_source_record, write_state  # type: ignore[import]


def _is_media_analysis_event(context: dict[str, Any]) -> bool:
    if context.get("platform") != "discord":
        return False
    chat_id = str(context.get("chat_id", ""))
    parent_chat_id = str(context.get("parent_chat_id", ""))
    return chat_id == MEDIA_ANALYSIS_CHANNEL or parent_chat_id == MEDIA_ANALYSIS_CHANNEL


def _thread_id(context: dict[str, Any]) -> str:
    chat_id = str(context.get("chat_id", ""))
    session_id = str(context.get("session_id", ""))
    return chat_id if chat_id != MEDIA_ANALYSIS_CHANNEL else session_id


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _job_output_dir(workspace: Path, index: int) -> Path:
    return workspace / "assets" / f"source-{index + 1}"


def _sanitize_creator_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "whoever"
    raw = " ".join(raw.split())
    return raw[:80]


def _build_database_name(metadata: dict[str, Any], manifest: dict[str, Any], source_type: str) -> str:
    title = str(metadata.get("title") or metadata.get("description") or "").strip()
    creator = str(
        metadata.get("uploader")
        or metadata.get("channel")
        or metadata.get("author")
        or metadata.get("creator")
        or metadata.get("username")
        or ""
    ).strip()
    platform = source_type or str(metadata.get("extractor_key") or metadata.get("extractor") or "source").lower()
    if title and creator:
        return f"{platform}: {title} — {creator}"
    if title:
        return f"{platform}: {title}"
    if creator:
        return f"{platform}: post by {creator}"
    return f"{platform}: {metadata.get('id') or manifest.get('id') or 'source'}"


def _discord_safe_thread_name(name: str) -> str:
    cleaned = " ".join(str(name or "media source").split())
    # Discord channel/thread names are capped at 100 chars. Leave a little room
    # so API-side normalization does not reject borderline names.
    return cleaned[:96].rstrip(" -—:") or "media source"


def _build_thread_title_suggestion(metadata: dict[str, Any], manifest: dict[str, Any], source_type: str, state: dict[str, Any]) -> tuple[str, str, str]:
    canonical = _build_database_name(metadata, manifest, source_type)
    base = _discord_safe_thread_name(canonical)
    prior_count = 0
    dedup_hits = state.get("dedup_hits") or {}
    if isinstance(dedup_hits, dict):
        prior_count = len([v for v in dedup_hits.values() if v])
    if prior_count > 0:
        return canonical, base, _discord_safe_thread_name(f"{base} {prior_count + 1}")
    return canonical, base, base


def _rename_discord_thread(thread_id: str, title: str) -> dict[str, Any]:
    if os.environ.get("SYSTEM_B_RENAME_THREADS", "1").lower() in {"0", "false", "no", "off"}:
        return {"ok": False, "skipped": True, "reason": "disabled"}
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        return {"ok": False, "skipped": True, "reason": "missing DISCORD_BOT_TOKEN"}
    safe_title = _discord_safe_thread_name(title)
    payload = json.dumps({"name": safe_title}).encode("utf-8")
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{thread_id}",
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "Hermes-System-B/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return {"ok": 200 <= response.status < 300, "status": response.status, "name": safe_title}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "status": exc.code, "name": safe_title, "error": body}
    except Exception as exc:
        return {"ok": False, "name": safe_title, "error": str(exc)}


def _run_backend(url: str, output_dir: Path) -> tuple[int, str, str, dict[str, Any], Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "media_backend.cli",
        url,
        str(output_dir),
        "--frame-interval",
        str(FRAME_INTERVAL_SECONDS),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(BACKEND_REPO),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    manifest_path: Path | None = None
    stdout_lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if stdout_lines:
        candidate = Path(stdout_lines[-1])
        if candidate.exists():
            manifest_path = candidate
    if manifest_path is None:
        candidate = output_dir / "manifest.json"
        if candidate.exists():
            manifest_path = candidate
    manifest = _load_json(manifest_path) if manifest_path else {}
    return proc.returncode, proc.stdout, proc.stderr, manifest, manifest_path


def _copy_manifest_artifacts(job: dict[str, Any], manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    artifacts = job.setdefault("artifacts", {})
    artifacts["backend_manifest"] = str(manifest_path)
    if manifest.get("media_path"):
        artifacts["media"] = manifest.get("media_path")
    if manifest.get("media_paths"):
        artifacts["media_paths"] = manifest.get("media_paths")
    if manifest.get("asset_records"):
        artifacts["asset_records"] = manifest.get("asset_records")
    if manifest.get("video_path"):
        artifacts["video"] = manifest.get("video_path")
    if manifest.get("audio_path"):
        artifacts["audio"] = manifest.get("audio_path")
    if manifest.get("transcript_path"):
        artifacts["transcript"] = manifest.get("transcript_path")
    artifacts["frames"] = manifest.get("frames") or []
    return artifacts


def _adapter_label(manifest: dict[str, Any]) -> str:
    metadata = manifest.get("metadata") or {}
    decision = metadata.get("adapter_decision") or {}
    return str(decision.get("primary") or manifest.get("acquisition_method") or "_unknown_")


def _write_source_doc(thread_id: str, state: dict[str, Any]) -> None:
    workspace = ensure_workspace(thread_id)
    lines: list[str] = ["# Source Metadata", ""]
    if state.get("thread_title_suggestion"):
        lines.extend([
            "## Thread title suggestion",
            "",
            f"- Base: {state.get('thread_title_base', '_unknown_')}",
            f"- Suggested: {state.get('thread_title_suggestion', '_unknown_')}",
            f"- Source: {state.get('thread_title_source', '_unknown_')}",
            "",
        ])
    for idx, job in enumerate(state.get("jobs", []), start=1):
        manifest = job.get("backend_manifest") or {}
        metadata = manifest.get("metadata") or {}
        artifacts = job.get("artifacts") or {}
        lines.extend([
            f"## Source {idx}",
            "",
            f"- URL: {job.get('url', '')}",
            f"- Normalized URL: {job.get('normalized_url', '')}",
            f"- Source type: {job.get('source_type', 'unknown')}",
            f"- Status: {job.get('status', '')}",
            f"- Adapter: {_adapter_label(manifest)}",
            f"- Title: {metadata.get('title') or '_unknown_'}",
            f"- Creator/uploader: {metadata.get('uploader') or '_unknown_'}",
            f"- Platform ID: {metadata.get('id') or '_unknown_'}",
            f"- Duration: {metadata.get('duration') or '_unknown_'}",
            f"- Published/uploaded: {metadata.get('upload_date') or metadata.get('timestamp') or '_unknown_'}",
            f"- Views: {metadata.get('view_count') if metadata.get('view_count') is not None else '_unknown_'}",
            f"- Likes: {metadata.get('like_count') if metadata.get('like_count') is not None else '_unknown_'}",
            f"- Comments: {metadata.get('comment_count') if metadata.get('comment_count') is not None else '_unknown_'}",
            f"- Media kind: {manifest.get('media_kind') or '_unknown_'}",
            f"- Manifest: {artifacts.get('backend_manifest') or '_missing_'}",
            f"- Media: {artifacts.get('media') or '_missing_'}",
            f"- Video: {artifacts.get('video') or '_missing_'}",
            f"- Audio: {artifacts.get('audio') or '_missing_'}",
            f"- Transcript: {artifacts.get('transcript') or '_missing_'}",
            f"- Transcript status: {job.get('transcript_status') or '_unknown_'} ({job.get('transcript_method') or '_unknown_'})",
            f"- Frame count: {len(artifacts.get('frames') or [])}",
            f"- Source storage: {(job.get('source_storage') or {}).get('source_dir') or '_missing_'}",
            "",
        ])
        if state.get("diagnostics_requested"):
            lines.extend(["### Diagnostics", "", "- Diagnostics: 04-diagnostics.md", ""])
        if job.get("error"):
            lines.extend(["### Error", "", str(job.get("error")), ""])
        if metadata.get("description"):
            lines.extend(["### Description/caption", "", str(metadata.get("description")), ""])
    (workspace / "01-source.md").write_text("\n".join(lines), encoding="utf-8")


def _write_diagnostics_doc(thread_id: str, state: dict[str, Any]) -> None:
    workspace = ensure_workspace(thread_id)
    lines: list[str] = ["# System B Diagnostics", ""]
    lines.extend([
        f"- Thread: {thread_id}",
        f"- Diagnostics requested: {bool(state.get('diagnostics_requested'))}",
        f"- Trigger: {state.get('diagnostics_trigger') or '_none_'}",
        f"- Stage: {state.get('stage') or '_unknown_'}",
        "",
    ])
    for idx, job in enumerate(state.get("jobs", []), start=1):
        manifest = job.get("backend_manifest") or {}
        metadata = manifest.get("metadata") or {}
        artifacts = job.get("artifacts") or {}
        source_storage = job.get("source_storage") or manifest.get("source_storage") or {}
        lines.extend([
            f"## Source {idx}",
            "",
            f"- URL: {job.get('url') or '_missing_'}",
            f"- Status: {job.get('status') or '_unknown_'}",
            f"- Adapter: {_adapter_label(manifest)}",
            f"- Fallback warnings: {metadata.get('adapter_warnings') or []}",
            f"- Source storage: {source_storage.get('source_dir') or '_missing_'}",
            f"- Downloaded files: {len(manifest.get('media_paths') or [])}",
            f"- Manifest: {artifacts.get('backend_manifest') or '_missing_'}",
            f"- Media kind: {manifest.get('media_kind') or '_unknown_'}",
            f"- Transcript: {job.get('transcript_status') or manifest.get('transcript_status') or '_unknown_'}",
            f"- Frames: {len(artifacts.get('frames') or manifest.get('frames') or [])}",
            f"- Source index: {job.get('source_index_status') or '_unknown_'}",
            f"- Discord rename: {(job.get('thread_rename') or state.get('thread_rename') or {}).get('ok', '_unknown_')}",
            f"- Backend exit code: {job.get('backend_exit_code', '_unknown_')}",
            f"- Errors: {job.get('error') or manifest.get('errors') or []}",
            "",
        ])
        if job.get("backend_stderr"):
            lines.extend(["### Backend stderr", "", "```text", str(job.get("backend_stderr"))[-2000:], "```", ""])
        if job.get("error"):
            lines.extend(["Next action: inspect adapter stderr and retry with the fallback adapter if one is listed.", ""])
    (workspace / "04-diagnostics.md").write_text("\n".join(lines), encoding="utf-8")


def _ensure_state(thread_id: str, context: dict[str, Any], urls: list[str]) -> dict[str, Any]:
    state = read_state(thread_id)
    if state:
        return state
    # Fallback for manual dry-runs or if this hook is invoked before intake.
    state = {
        "thread_id": thread_id,
        "platform": context.get("platform", "discord"),
        "chat_id": context.get("chat_id", ""),
        "parent_chat_id": context.get("parent_chat_id", ""),
        "user_id": context.get("user_id", ""),
        "session_id": context.get("session_id", ""),
        "created_at": time.time(),
        "stage": "intake",
        "urls": urls,
        "dedup_hits": {},
        "jobs": [
            {
                "url": url,
                "normalized_url": "",
                "source_type": "unknown",
                "status": "pending",
                "duplicate_of": None,
                "artifacts": {},
            }
            for url in urls
        ],
        "error": None,
        "retry_count": 0,
    }
    write_state(thread_id, state)
    return state


async def handle(event_type: str, context: dict[str, Any]) -> None:
    if not _is_media_analysis_event(context):
        return
    message = str(context.get("message", ""))
    urls = extract_urls(message)
    if not urls:
        return
    if not BACKEND_REPO.exists():
        print(f"[media-analysis-z-backend] backend repo missing: {BACKEND_REPO}", flush=True)
        return

    thread_id = _thread_id(context)
    if not thread_id:
        print("[media-analysis-z-backend] no thread/session id; skipping", flush=True)
        return

    workspace = ensure_workspace(thread_id)
    state = _ensure_state(thread_id, context, urls)
    jobs = state.get("jobs") or []
    if not jobs:
        return

    state["stage"] = "extract"
    changed = False

    for idx, job in enumerate(jobs):
        url = job.get("url") or (urls[idx] if idx < len(urls) else "")
        if not url:
            continue
        if job.get("duplicate_of"):
            job["normalized_url"] = job.get("normalized_url") or normalize_url(url)
            job["status"] = "duplicate"
            changed = True
            continue
        artifacts = job.setdefault("artifacts", {})
        if artifacts.get("backend_manifest") and Path(str(artifacts["backend_manifest"])).exists():
            continue

        job["normalized_url"] = normalize_url(url)
        job["status"] = "extracting"
        job["started_extract_at"] = time.time()
        write_state(thread_id, state)

        try:
            out_dir = _job_output_dir(workspace, idx)
            code, stdout, stderr, manifest, manifest_path = _run_backend(url, out_dir)
            job["backend_stdout"] = stdout[-4000:]
            job["backend_stderr"] = stderr[-4000:]
            job["backend_exit_code"] = code
            if code != 0 or not manifest_path:
                job["status"] = "error"
                job["error"] = stderr.strip() or stdout.strip() or f"backend exited {code} without manifest"
            else:
                job["backend_manifest"] = manifest
                job["source_type"] = manifest.get("source") or job.get("source_type") or "unknown"
                if manifest.get("source_storage"):
                    job["source_storage"] = manifest.get("source_storage")
                artifacts = _copy_manifest_artifacts(job, manifest, manifest_path)
                if manifest.get("transcript_status"):
                    job["transcript_status"] = manifest.get("transcript_status")
                    job["transcript_method"] = manifest.get("transcript_method")
                job["status"] = "extracted"
                job["extracted_at"] = time.time()

                metadata = manifest.get("metadata") or {}
                canonical_name, base_title, suggested_title = _build_thread_title_suggestion(
                    metadata,
                    manifest,
                    job["source_type"],
                    state,
                )
                state["thread_title_base"] = base_title
                state["thread_title_suggestion"] = suggested_title
                state["thread_title_source"] = "backend_metadata"
                state["canonical_source_name"] = canonical_name
                job["canonical_name"] = canonical_name
                job["thread_title"] = suggested_title
                upsert_source_record(
                    normalized_url=job.get("normalized_url") or normalize_url(url),
                    raw_url=url,
                    thread_id=thread_id,
                    workspace_path=str(workspace),
                    source_type=job["source_type"],
                    title=str(metadata.get("title") or ""),
                    confidence=str(job.get("confidence") or manifest.get("confidence") or ""),
                    platform=job["source_type"],
                    creator=str(
                        metadata.get("uploader")
                        or metadata.get("channel")
                        or metadata.get("author")
                        or metadata.get("creator")
                        or metadata.get("username")
                        or ""
                    ),
                    canonical_name=canonical_name,
                    thread_title=suggested_title,
                    metadata={
                        "id": metadata.get("id"),
                        "duration": metadata.get("duration"),
                        "upload_date": metadata.get("upload_date"),
                        "webpage_url": metadata.get("webpage_url"),
                        "media_kind": manifest.get("media_kind"),
                        "acquisition_method": manifest.get("acquisition_method"),
                        "adapter_decision": metadata.get("adapter_decision"),
                        "adapter_warnings": metadata.get("adapter_warnings", []),
                        "transcript_status": manifest.get("transcript_status"),
                        "frame_count": manifest.get("frame_count") if manifest.get("frame_count") is not None else len(manifest.get("frames") or []),
                    },
                    source_storage=manifest.get("source_storage") or {},
                    manifest_path=str(manifest_path),
                    status=job["status"],
                )
                job["source_index_status"] = "upserted"
                rename_result = _rename_discord_thread(thread_id, suggested_title)
                state["thread_rename"] = rename_result
                job["thread_rename"] = rename_result
        except subprocess.TimeoutExpired as exc:
            job["status"] = "error"
            job["error"] = f"backend timeout after {TIMEOUT_SECONDS}s: {exc}"
        except Exception as exc:
            job["status"] = "error"
            job["error"] = str(exc)
        finally:
            changed = True
            write_state(thread_id, state)

    if changed:
        statuses = [job.get("status") for job in jobs]
        if any(status == "error" for status in statuses):
            state["stage"] = "extract_partial" if any(status == "extracted" for status in statuses) else "failed"
        elif all(status in {"extracted", "duplicate"} for status in statuses):
            state["stage"] = "extract_complete"
        write_state(thread_id, state)
        _write_source_doc(thread_id, state)
        if state.get("diagnostics_requested"):
            _write_diagnostics_doc(thread_id, state)
        print(f"[media-analysis-z-backend] thread={thread_id} statuses={statuses}", flush=True)
