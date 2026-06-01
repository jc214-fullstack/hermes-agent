import asyncio
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_LIB = REPO_ROOT / "integrations" / "hermes-hooks" / "lib"
BACKEND_HOOK = REPO_ROOT / "integrations" / "hermes-hooks" / "media-analysis-z-backend" / "handler.py"


def _load_backend_hook():
    if str(HOOK_LIB) not in sys.path:
        sys.path.insert(0, str(HOOK_LIB))
    spec = importlib.util.spec_from_file_location("media_analysis_z_backend_handler", BACKEND_HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_hook_persists_duplicate_only_status(tmp_path, monkeypatch):
    handler = _load_backend_hook()
    import state as hook_state

    monkeypatch.setattr(hook_state, "WORKSPACE_ROOT", tmp_path)
    thread_id = "thread-123"
    url = "https://www.instagram.com/reel/abc123/"
    hook_state.write_state(
        thread_id,
        {
            "thread_id": thread_id,
            "platform": "discord",
            "chat_id": thread_id,
            "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
            "urls": [url],
            "stage": "intake",
            "dedup_hits": {url: "prior-thread"},
            "jobs": [
                {
                    "url": url,
                    "normalized_url": "",
                    "source_type": "unknown",
                    "status": "pending",
                    "duplicate_of": "prior-thread",
                    "artifacts": {},
                }
            ],
        },
    )

    asyncio.run(
        handler.handle(
            "agent:start",
            {
                "platform": "discord",
                "chat_id": thread_id,
                "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
                "message": url,
                "session_id": "session-123",
            },
        )
    )

    saved = hook_state.read_state(thread_id)
    assert saved["stage"] == "extract_complete"
    assert saved["jobs"][0]["status"] == "duplicate"
    assert saved["jobs"][0]["normalized_url"]


def test_backend_hook_copies_manifest_asset_records_into_artifacts():
    handler = _load_backend_hook()
    manifest = {
        "source": "instagram",
        "media_path": "/out/post2.mp4",
        "media_paths": ["/out/post1.jpg", "/out/post2.mp4"],
        "asset_records": [
            {
                "index": 0,
                "path": "/out/post1.jpg",
                "kind": "image",
                "role": "carousel_item",
                "suffix": ".jpg",
                "extraction_status": "extracted",
                "errors": [],
            },
            {
                "index": 1,
                "path": "/out/post2.mp4",
                "kind": "video",
                "role": "primary_video",
                "suffix": ".mp4",
                "extraction_status": "extracted",
                "errors": [],
            },
        ],
        "frames": [],
        "metadata": {},
    }
    job = {}

    artifacts = handler._copy_manifest_artifacts(job, manifest, Path("/out/manifest.json"))

    assert artifacts["backend_manifest"] == "/out/manifest.json"
    assert artifacts["media_paths"] == manifest["media_paths"]
    assert artifacts["asset_records"] == manifest["asset_records"]


def test_backend_hook_builds_canonical_database_title():
    handler = _load_backend_hook()
    canonical, base, suggested = handler._build_thread_title_suggestion(
        {"title": "Responding To Your Mad Men Hot Takes 🔥", "uploader": "Pure Kino"},
        {"id": "vukW2TrriYg"},
        "youtube",
        {"dedup_hits": {}},
    )

    assert canonical == "youtube: Responding To Your Mad Men Hot Takes 🔥 — Pure Kino"
    assert base == canonical
    assert suggested == canonical


def test_backend_hook_extract_success_upserts_source_and_renames(tmp_path, monkeypatch):
    handler = _load_backend_hook()
    import state as hook_state

    monkeypatch.setattr(hook_state, "WORKSPACE_ROOT", tmp_path / "threads")
    monkeypatch.setattr(hook_state, "INDEX_ROOT", tmp_path / "index")
    monkeypatch.setattr(hook_state, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl")
    monkeypatch.setattr(hook_state, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl")
    monkeypatch.setattr(handler, "ensure_workspace", hook_state.ensure_workspace)
    monkeypatch.setattr(handler, "read_state", hook_state.read_state)
    monkeypatch.setattr(handler, "write_state", hook_state.write_state)
    monkeypatch.setattr(handler, "upsert_source_record", hook_state.upsert_source_record)
    monkeypatch.setattr(handler, "_rename_discord_thread", lambda thread_id, title: {"ok": True, "name": title})

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "source": "youtube",
        "media_kind": "video",
        "acquisition_method": "yt-dlp",
        "source_storage": {
            "source_key": "yt-vukw2trriyG",
            "source_dir": str(tmp_path / "sources" / "platform" / "youtube" / "yt-vukw2trriyG"),
            "storage_class": "platform",
            "platform": "youtube",
            "company": None,
            "raw_kind": None,
        },
        "metadata": {
            "id": "vukW2TrriYg",
            "title": "Responding To Your Mad Men Hot Takes 🔥",
            "uploader": "Pure Kino",
            "duration": 1080,
            "upload_date": "20260601",
            "webpage_url": "https://www.youtube.com/watch?v=vukW2TrriYg",
            "adapter_decision": {"primary": "yt-dlp", "fallbacks": []},
        },
        "frames": [],
        "frame_count": 0,
        "transcript_status": "stt_complete",
    }
    monkeypatch.setattr(handler, "_run_backend", lambda url, out_dir: (0, str(manifest_path), "", manifest, manifest_path))

    thread_id = "thread-456"
    url = "https://www.youtube.com/watch?v=vukW2TrriYg"
    asyncio.run(
        handler.handle(
            "agent:start",
            {
                "platform": "discord",
                "chat_id": thread_id,
                "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
                "message": url,
                "session_id": "session-456",
            },
        )
    )

    saved = hook_state.read_state(thread_id)
    assert saved["stage"] == "extract_complete"
    assert saved["canonical_source_name"] == "youtube: Responding To Your Mad Men Hot Takes 🔥 — Pure Kino"
    assert saved["thread_rename"]["ok"] is True
    assert saved["jobs"][0]["source_storage"]["source_key"] == "yt-vukw2trriyG"

    records = [json.loads(line) for line in hook_state.SOURCES_INDEX.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["canonical_name"] == saved["canonical_source_name"]
    assert records[0]["thread_id"] == thread_id
    assert records[0]["source_key"] == "yt-vukw2trriyG"
    assert records[0]["source_dir"] == manifest["source_storage"]["source_dir"]
    assert records[0]["run_count"] == 1
    assert records[0]["thread_ids"] == [thread_id]


def test_backend_hook_writes_diagnostics_for_requested_runs(tmp_path, monkeypatch):
    handler = _load_backend_hook()
    import state as hook_state

    monkeypatch.setattr(hook_state, "WORKSPACE_ROOT", tmp_path / "threads")
    monkeypatch.setattr(hook_state, "INDEX_ROOT", tmp_path / "index")
    monkeypatch.setattr(hook_state, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl")
    monkeypatch.setattr(hook_state, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl")
    monkeypatch.setattr(handler, "ensure_workspace", hook_state.ensure_workspace)
    monkeypatch.setattr(handler, "read_state", hook_state.read_state)
    monkeypatch.setattr(handler, "write_state", hook_state.write_state)
    monkeypatch.setattr(handler, "upsert_source_record", hook_state.upsert_source_record)
    monkeypatch.setattr(handler, "_rename_discord_thread", lambda thread_id, title: {"ok": True, "name": title})

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "source": "youtube",
        "media_kind": "video",
        "acquisition_method": "yt-dlp",
        "source_storage": {
            "source_key": "yt-abc",
            "source_dir": str(tmp_path / "sources" / "platform" / "youtube" / "yt-abc"),
            "storage_class": "platform",
            "platform": "youtube",
            "company": None,
            "raw_kind": None,
        },
        "metadata": {"id": "abc", "title": "Demo", "uploader": "Tester", "adapter_decision": {"primary": "yt-dlp"}},
        "frames": ["frame-1.jpg"],
        "frame_count": 1,
        "transcript_status": "stt_complete",
    }
    monkeypatch.setattr(handler, "_run_backend", lambda url, out_dir: (0, str(manifest_path), "stderr", manifest, manifest_path))

    thread_id = "thread-diag"
    url = "https://youtu.be/abc"
    hook_state.write_state(
        thread_id,
        {
            "thread_id": thread_id,
            "platform": "discord",
            "chat_id": thread_id,
            "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
            "urls": [url],
            "stage": "intake",
            "diagnostics_requested": True,
            "test_run": True,
            "diagnostics_trigger": "#systemb-test",
            "dedup_hits": {},
            "jobs": [{"url": url, "normalized_url": "", "source_type": "unknown", "status": "pending", "artifacts": {}}],
        },
    )

    asyncio.run(
        handler.handle(
            "agent:start",
            {
                "platform": "discord",
                "chat_id": thread_id,
                "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
                "message": "#systemb-test https://youtu.be/abc",
                "session_id": "session-diag",
            },
        )
    )

    diagnostics = tmp_path / "threads" / thread_id / "04-diagnostics.md"
    assert diagnostics.exists()
    text = diagnostics.read_text(encoding="utf-8")
    assert "Adapter: yt-dlp" in text
    assert f"Source storage: {manifest['source_storage']['source_dir']}" in text
    assert "Diagnostics: 04-diagnostics.md" in (tmp_path / "threads" / thread_id / "01-source.md").read_text(encoding="utf-8")
