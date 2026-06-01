import asyncio
import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_LIB = REPO_ROOT / "integrations" / "hermes-hooks" / "lib"
INTAKE_HOOK = REPO_ROOT / "integrations" / "hermes-hooks" / "media-analysis-intake" / "handler.py"


def _load_intake_hook():
    if str(HOOK_LIB) not in sys.path:
        sys.path.insert(0, str(HOOK_LIB))
    spec = importlib.util.spec_from_file_location("media_analysis_intake_handler", INTAKE_HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_intake_marks_systemb_test_messages_for_diagnostics(tmp_path, monkeypatch):
    handler = _load_intake_hook()
    import state as hook_state

    monkeypatch.setattr(hook_state, "WORKSPACE_ROOT", tmp_path / "threads")
    monkeypatch.setattr(hook_state, "INDEX_ROOT", tmp_path / "index")
    monkeypatch.setattr(hook_state, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl")
    monkeypatch.setattr(hook_state, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl")
    monkeypatch.setattr(handler, "init_state", hook_state.init_state)
    monkeypatch.setattr(handler, "load_source_index", hook_state.load_source_index)
    monkeypatch.setattr(handler, "record_source", hook_state.record_source)
    monkeypatch.setattr(handler, "record_batch", hook_state.record_batch)
    monkeypatch.setattr(handler, "write_request_doc", hook_state.write_request_doc)

    thread_id = "thread-test"
    asyncio.run(
        handler.handle(
            "agent:start",
            {
                "platform": "discord",
                "chat_id": thread_id,
                "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
                "message": "#systemb-test https://youtu.be/abc",
                "user_id": "user-1",
                "session_id": "session-1",
            },
        )
    )

    saved = hook_state.read_state(thread_id)
    assert saved["test_run"] is True
    assert saved["diagnostics_requested"] is True
    assert saved["diagnostics_trigger"] == "#systemb-test"


def test_intake_leaves_normal_messages_unmarked(tmp_path, monkeypatch):
    handler = _load_intake_hook()
    import state as hook_state

    monkeypatch.setattr(hook_state, "WORKSPACE_ROOT", tmp_path / "threads")
    monkeypatch.setattr(hook_state, "INDEX_ROOT", tmp_path / "index")
    monkeypatch.setattr(hook_state, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl")
    monkeypatch.setattr(hook_state, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl")
    monkeypatch.setattr(handler, "init_state", hook_state.init_state)
    monkeypatch.setattr(handler, "load_source_index", hook_state.load_source_index)
    monkeypatch.setattr(handler, "record_source", hook_state.record_source)
    monkeypatch.setattr(handler, "record_batch", hook_state.record_batch)
    monkeypatch.setattr(handler, "write_request_doc", hook_state.write_request_doc)

    thread_id = "thread-normal"
    asyncio.run(
        handler.handle(
            "agent:start",
            {
                "platform": "discord",
                "chat_id": thread_id,
                "parent_chat_id": handler.MEDIA_ANALYSIS_CHANNEL,
                "message": "please analyze https://youtu.be/abc",
                "user_id": "user-1",
                "session_id": "session-1",
            },
        )
    )

    saved = hook_state.read_state(thread_id)
    assert saved.get("test_run") is not True
    assert saved.get("diagnostics_requested") is not True
