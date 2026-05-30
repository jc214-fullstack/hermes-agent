"""Tests for the media-analysis-intake hook and its utility modules.

Covers:
- URL extraction from message text
- URL normalization / tracking-param stripping
- Dedup detection against sources.jsonl
- Workspace + state.json creation
- 00-request.md content
- Hook filter (only fires for discord + media-analysis channel)
- parent_chat_id present in agent:start context
"""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to locate lib and hook handler without touching installed paths
# ---------------------------------------------------------------------------

LIB_DIR = Path("/home/imagi/media-analysis/lib")
HOOK_DIR = Path("/home/imagi/.hermes/hooks/media-analysis-intake")


def _import_lib(name: str):
    """Import a module from the media-analysis lib directory."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, LIB_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_handler(url_norm_mod, state_mod):
    """Load handler.py with its lib imports patched to our test modules."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "media_analysis_handler", HOOK_DIR / "handler.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Inject pre-loaded lib modules so handler doesn't need real sys.path
    sys.modules.setdefault("url_norm", url_norm_mod)
    sys.modules.setdefault("state", state_mod)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# url_norm tests
# ---------------------------------------------------------------------------

class TestExtractUrls:
    def setup_method(self):
        self.mod = _import_lib("url_norm")

    def test_single_url(self):
        urls = self.mod.extract_urls("Check this out https://example.com/path?q=1")
        assert urls == ["https://example.com/path?q=1"]

    def test_multiple_urls(self):
        text = "See https://youtube.com/watch?v=abc and https://arxiv.org/abs/1234.5678"
        urls = self.mod.extract_urls(text)
        assert len(urls) == 2
        assert "https://youtube.com/watch?v=abc" in urls
        assert "https://arxiv.org/abs/1234.5678" in urls

    def test_no_urls(self):
        assert self.mod.extract_urls("just plain text with no links") == []

    def test_deduplication_preserves_order(self):
        text = "https://a.com https://b.com https://a.com"
        urls = self.mod.extract_urls(text)
        assert urls == ["https://a.com", "https://b.com"]

    def test_strips_trailing_punctuation(self):
        urls = self.mod.extract_urls("Look at https://example.com/page.")
        assert urls == ["https://example.com/page"]

    def test_http_and_https(self):
        text = "http://old.example.com and https://new.example.com"
        urls = self.mod.extract_urls(text)
        assert len(urls) == 2


class TestNormalizeUrl:
    def setup_method(self):
        self.mod = _import_lib("url_norm")

    def test_lowercases_host(self):
        norm = self.mod.normalize_url("https://YouTube.com/watch?v=abc")
        assert "youtube.com" in norm

    def test_strips_utm_params(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&real=1"
        norm = self.mod.normalize_url(url)
        assert "utm_source" not in norm
        assert "utm_medium" not in norm
        assert "real=1" in norm

    def test_strips_fbclid(self):
        url = "https://example.com/?fbclid=abc123&id=42"
        norm = self.mod.normalize_url(url)
        assert "fbclid" not in norm
        assert "id=42" in norm

    def test_stable_across_param_order(self):
        a = self.mod.normalize_url("https://example.com/?b=2&a=1")
        b = self.mod.normalize_url("https://example.com/?a=1&b=2")
        assert a == b

    def test_strips_fragment(self):
        norm = self.mod.normalize_url("https://example.com/page#section-3")
        assert "#" not in norm

    def test_strips_default_https_port(self):
        norm = self.mod.normalize_url("https://example.com:443/path")
        assert ":443" not in norm

    def test_youtube_id_preserved(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=trackme"
        norm = self.mod.normalize_url(url)
        assert "v=dQw4w9WgXcQ" in norm
        assert "si=" not in norm


# ---------------------------------------------------------------------------
# state.py tests
# ---------------------------------------------------------------------------

class TestStateManagement:
    def setup_method(self):
        self.mod = _import_lib("state")

    def test_ensure_workspace_creates_dirs(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            ws = self.mod.ensure_workspace("thread-abc")
        assert (tmp_path / "thread-abc").is_dir()
        assert (tmp_path / "thread-abc" / "assets").is_dir()

    def test_write_and_read_state(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            self.mod.write_state("t1", {"stage": "intake", "urls": []})
            result = self.mod.read_state("t1")
        assert result["stage"] == "intake"

    def test_read_state_missing_returns_empty(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            result = self.mod.read_state("nonexistent-thread")
        assert result == {}

    def test_init_state_sets_pending_jobs(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            state = self.mod.init_state(
                thread_id="t2",
                platform="discord",
                chat_id="t2",
                parent_chat_id="1509517024345194617",
                user_id="u1",
                session_id="s1",
                raw_message="check https://example.com",
                urls=["https://example.com"],
                dedup_hits={},
            )
        assert len(state["jobs"]) == 1
        assert state["jobs"][0]["status"] == "pending"
        assert state["jobs"][0]["url"] == "https://example.com"
        assert state["stage"] == "intake"

    def test_init_state_marks_duplicate(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            state = self.mod.init_state(
                thread_id="t3",
                platform="discord",
                chat_id="t3",
                parent_chat_id="1509517024345194617",
                user_id="u1",
                session_id="s1",
                raw_message="https://example.com",
                urls=["https://example.com"],
                dedup_hits={"https://example.com": "old-thread-111"},
            )
        assert state["jobs"][0]["duplicate_of"] == "old-thread-111"

    def test_write_request_doc(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            self.mod.write_request_doc(
                thread_id="t4",
                platform="discord",
                chat_id="t4",
                parent_chat_id="1509517024345194617",
                user_id="u99",
                session_id="sess-99",
                raw_message="https://arxiv.org/abs/1234",
                urls=["https://arxiv.org/abs/1234"],
                dedup_hits={},
                timestamp=time.time(),
            )
            content = (tmp_path / "t4" / "00-request.md").read_text()
        assert "https://arxiv.org/abs/1234" in content
        assert "u99" in content
        assert "1509517024345194617" in content

    def test_write_request_doc_dedup_section(self, tmp_path):
        with patch.object(self.mod, "WORKSPACE_ROOT", tmp_path):
            self.mod.write_request_doc(
                thread_id="t5",
                platform="discord",
                chat_id="t5",
                parent_chat_id="1509517024345194617",
                user_id="u1",
                session_id="s1",
                raw_message="https://example.com",
                urls=["https://example.com"],
                dedup_hits={"https://example.com": "prior-thread-777"},
                timestamp=time.time(),
            )
            content = (tmp_path / "t5" / "00-request.md").read_text()
        assert "prior-thread-777" in content
        assert "Duplicate sources detected" in content


class TestSourceIndex:
    def setup_method(self):
        self.mod = _import_lib("state")

    def test_record_and_load_source(self, tmp_path):
        with patch.object(self.mod, "INDEX_ROOT", tmp_path), \
             patch.object(self.mod, "SOURCES_INDEX", tmp_path / "sources.jsonl"):
            self.mod.record_source(
                normalized_url="https://example.com/page",
                raw_url="https://example.com/page?utm_source=x",
                thread_id="t10",
                workspace_path="/home/imagi/media-analysis/threads/t10",
            )
            index = self.mod.load_source_index()

        assert "https://example.com/page" in index
        assert index["https://example.com/page"]["thread_id"] == "t10"

    def test_load_empty_index(self, tmp_path):
        with patch.object(self.mod, "SOURCES_INDEX", tmp_path / "sources.jsonl"):
            result = self.mod.load_source_index()
        assert result == {}

    def test_mark_source_reused_updates_timestamp(self, tmp_path):
        sources_file = tmp_path / "sources.jsonl"
        with patch.object(self.mod, "INDEX_ROOT", tmp_path), \
             patch.object(self.mod, "SOURCES_INDEX", sources_file):
            self.mod.record_source(
                normalized_url="https://example.com",
                raw_url="https://example.com",
                thread_id="t20",
                workspace_path="/tmp/t20",
            )
            self.mod.mark_source_reused("https://example.com")
            index = self.mod.load_source_index()

        assert index["https://example.com"]["latest_reused_at"] is not None


# ---------------------------------------------------------------------------
# Hook filter tests
# ---------------------------------------------------------------------------

class TestHookFilter:
    """Test _is_media_analysis_event without importing the full hook module."""

    MEDIA_CH = "1509517024345194617"

    def _check(self, platform, chat_id, parent_chat_id) -> bool:
        if platform != "discord":
            return False
        return chat_id == self.MEDIA_CH or parent_chat_id == self.MEDIA_CH

    def test_thread_in_media_channel_via_parent(self):
        assert self._check("discord", "thread-111", self.MEDIA_CH)

    def test_direct_message_to_media_channel(self):
        assert self._check("discord", self.MEDIA_CH, "")

    def test_unrelated_channel_excluded(self):
        assert not self._check("discord", "999999999", "888888888")

    def test_non_discord_platform_excluded(self):
        assert not self._check("telegram", self.MEDIA_CH, "")

    def test_empty_context_excluded(self):
        assert not self._check("", "", "")


# ---------------------------------------------------------------------------
# Integration: hook handle() full path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hook_creates_workspace_for_url_message(tmp_path):
    """Full integration: handle() creates workspace when URL present."""
    url_norm_mod = _import_lib("url_norm")
    state_mod = _import_lib("state")

    # Patch filesystem roots to tmp_path
    with patch.object(state_mod, "WORKSPACE_ROOT", tmp_path / "threads"), \
         patch.object(state_mod, "INDEX_ROOT", tmp_path / "index"), \
         patch.object(state_mod, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl"), \
         patch.object(state_mod, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl"):

        # Patch sys.modules so handler.py uses our patched modules
        sys.modules["url_norm"] = url_norm_mod
        sys.modules["state"] = state_mod

        handler = _import_handler(url_norm_mod, state_mod)
        handler.MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"

        ctx = {
            "platform": "discord",
            "chat_id": "thread-42",
            "parent_chat_id": "1509517024345194617",
            "user_id": "user-1",
            "session_id": "sess-1",
            "message": "Check this https://arxiv.org/abs/1234.5678 for the new paper",
        }
        await handler.handle("agent:start", ctx)

    ws = tmp_path / "threads" / "thread-42"
    assert ws.is_dir()
    assert (ws / "state.json").exists()
    assert (ws / "00-request.md").exists()

    state = json.loads((ws / "state.json").read_text())
    assert state["thread_id"] == "thread-42"
    assert state["stage"] == "intake"
    assert len(state["jobs"]) == 1
    assert state["jobs"][0]["url"] == "https://arxiv.org/abs/1234.5678"

    req = (ws / "00-request.md").read_text()
    assert "arxiv.org" in req
    assert "1509517024345194617" in req


@pytest.mark.asyncio
async def test_hook_skips_non_discord(tmp_path):
    url_norm_mod = _import_lib("url_norm")
    state_mod = _import_lib("state")

    with patch.object(state_mod, "WORKSPACE_ROOT", tmp_path / "threads"), \
         patch.object(state_mod, "INDEX_ROOT", tmp_path / "index"), \
         patch.object(state_mod, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl"), \
         patch.object(state_mod, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl"):

        sys.modules["url_norm"] = url_norm_mod
        sys.modules["state"] = state_mod
        handler = _import_handler(url_norm_mod, state_mod)
        handler.MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"

        await handler.handle("agent:start", {
            "platform": "telegram",
            "chat_id": "1509517024345194617",
            "parent_chat_id": "",
            "user_id": "u1",
            "session_id": "s1",
            "message": "https://example.com",
        })

    assert not (tmp_path / "threads").exists()


@pytest.mark.asyncio
async def test_hook_skips_no_urls(tmp_path):
    url_norm_mod = _import_lib("url_norm")
    state_mod = _import_lib("state")

    with patch.object(state_mod, "WORKSPACE_ROOT", tmp_path / "threads"), \
         patch.object(state_mod, "INDEX_ROOT", tmp_path / "index"), \
         patch.object(state_mod, "SOURCES_INDEX", tmp_path / "index" / "sources.jsonl"), \
         patch.object(state_mod, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl"):

        sys.modules["url_norm"] = url_norm_mod
        sys.modules["state"] = state_mod
        handler = _import_handler(url_norm_mod, state_mod)
        handler.MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"

        await handler.handle("agent:start", {
            "platform": "discord",
            "chat_id": "thread-99",
            "parent_chat_id": "1509517024345194617",
            "user_id": "u1",
            "session_id": "s1",
            "message": "just chatting, no links here",
        })

    assert not (tmp_path / "threads").exists()


@pytest.mark.asyncio
async def test_hook_detects_duplicate_url(tmp_path):
    url_norm_mod = _import_lib("url_norm")
    state_mod = _import_lib("state")

    sources_file = tmp_path / "index" / "sources.jsonl"
    (tmp_path / "index").mkdir(parents=True)

    # Pre-seed a known URL in the index
    existing = {
        "normalized_url": "https://example.com/video",
        "url": "https://example.com/video",
        "thread_id": "prior-thread-555",
        "workspace_path": "/home/imagi/media-analysis/threads/prior-thread-555",
        "source_type": "article_url",
        "first_analyzed_at": time.time() - 3600,
        "latest_reused_at": None,
    }
    sources_file.write_text(json.dumps(existing) + "\n", encoding="utf-8")

    with patch.object(state_mod, "WORKSPACE_ROOT", tmp_path / "threads"), \
         patch.object(state_mod, "INDEX_ROOT", tmp_path / "index"), \
         patch.object(state_mod, "SOURCES_INDEX", sources_file), \
         patch.object(state_mod, "BATCHES_INDEX", tmp_path / "index" / "batches.jsonl"):

        sys.modules["url_norm"] = url_norm_mod
        sys.modules["state"] = state_mod
        handler = _import_handler(url_norm_mod, state_mod)
        handler.MEDIA_ANALYSIS_CHANNEL = "1509517024345194617"

        await handler.handle("agent:start", {
            "platform": "discord",
            "chat_id": "thread-new",
            "parent_chat_id": "1509517024345194617",
            "user_id": "u1",
            "session_id": "s1",
            "message": "https://example.com/video",
        })

    state = json.loads((tmp_path / "threads" / "thread-new" / "state.json").read_text())
    job = state["jobs"][0]
    assert job["duplicate_of"] == "prior-thread-555"

    req = (tmp_path / "threads" / "thread-new" / "00-request.md").read_text()
    assert "prior-thread-555" in req


# ---------------------------------------------------------------------------
# agent:start context includes parent_chat_id
# ---------------------------------------------------------------------------

def test_agent_start_hook_ctx_includes_parent_chat_id():
    """Verify run.py emits parent_chat_id in the agent:start hook context."""
    import ast
    run_py = Path("/home/imagi/.hermes/hermes-agent/gateway/run.py")
    src = run_py.read_text(encoding="utf-8")
    # Find the hook_ctx dict literal near the emit call
    assert '"parent_chat_id"' in src or "'parent_chat_id'" in src, (
        "parent_chat_id must be present in the agent:start hook_ctx in gateway/run.py"
    )
    # Confirm it's sourced from source.parent_chat_id
    assert "source.parent_chat_id" in src, (
        "hook_ctx must populate parent_chat_id from source.parent_chat_id"
    )
