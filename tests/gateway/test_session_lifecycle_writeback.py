from __future__ import annotations

from collections import OrderedDict
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(text=text, source=_make_source(), message_id="m1")


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner.hooks = cast(Any, SimpleNamespace(emit=AsyncMock(), loaded_hooks=False))
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._background_tasks = set()
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._queued_events = {}
    runner._busy_ack_ts = {}
    runner._session_run_generation = {}
    runner._agent_cache = cast(Any, OrderedDict())
    runner._agent_cache_lock = threading.Lock()
    runner._session_db = None
    runner._format_session_info = lambda: ""
    runner._is_user_authorized = lambda source: True
    runner._cleanup_agent_resources = MagicMock()

    session_key = build_session_key(_make_source())
    old_entry = SessionEntry(
        session_key=session_key,
        session_id="sess-old",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    new_entry = SessionEntry(
        session_key=session_key,
        session_id="sess-new",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner.session_store = MagicMock()
    runner.session_store._entries = {session_key: old_entry}
    runner.session_store.reset_session.return_value = new_entry
    runner.session_store.get_or_create_session.return_value = new_entry
    return runner, session_key


@pytest.mark.asyncio
async def test_reset_command_finalizes_old_session_with_cached_messages():
    runner, session_key = _make_runner()
    cached_agent = MagicMock()
    cached_agent.conversation_history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    with runner._agent_cache_lock:
        runner._agent_cache[session_key] = cached_agent

    with patch("agent.session_lifecycle_writeback.finalize_session") as mock_finalize:
        await runner._handle_reset_command(_make_event("/new"))

    mock_finalize.assert_called_once()
    kwargs = mock_finalize.call_args.kwargs
    assert kwargs["session_id"] == "sess-old"
    assert kwargs["boundary_reason"] == "new_session"
    assert kwargs["messages"] == cached_agent.conversation_history
    assert kwargs["metadata"]["next_session_id"] == "sess-new"
    assert kwargs["source_override"]["chat_id"] == "c1"


@pytest.mark.asyncio
async def test_session_expiry_watcher_finalizes_writeback_before_cleanup():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner._running = True
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._busy_ack_ts = {}
    runner._agent_cache = cast(Any, OrderedDict())
    runner._agent_cache_lock = threading.Lock()
    runner._last_session_store_prune_ts = 0.0
    runner._cleanup_agent_resources = MagicMock()
    runner._evict_cached_agent = MagicMock()
    runner._sweep_idle_cached_agents = MagicMock(return_value=0)

    session_key = "agent:main:telegram:dm:42"
    expired_entry = SessionEntry(
        session_key=session_key,
        session_id="sess-expired",
        created_at=datetime.now() - timedelta(hours=2),
        updated_at=datetime.now() - timedelta(hours=2),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    expired_entry.expiry_finalized = False

    cached_agent = MagicMock()
    cached_agent.conversation_history = [{"role": "user", "content": "stale context"}]
    with runner._agent_cache_lock:
        runner._agent_cache[session_key] = cached_agent

    runner.session_store = MagicMock()
    runner.session_store._ensure_loaded = MagicMock()
    runner.session_store._entries = {session_key: expired_entry}
    runner.session_store._is_session_expired = MagicMock(return_value=True)
    runner.session_store._lock = MagicMock()
    runner.session_store._lock.__enter__ = MagicMock(return_value=None)
    runner.session_store._lock.__exit__ = MagicMock(return_value=None)
    runner.session_store._save = MagicMock()

    _orig_sleep = __import__("asyncio").sleep

    async def _fast_sleep(_):
        await _orig_sleep(0)

    def _finalize_and_stop(*args, **kwargs):
        runner._running = False
        return None

    with patch("gateway.run.asyncio.sleep", side_effect=_fast_sleep), \
         patch("agent.session_lifecycle_writeback.finalize_session", side_effect=_finalize_and_stop) as mock_finalize:
        await runner._session_expiry_watcher(interval=0)

    mock_finalize.assert_called_once()
    kwargs = mock_finalize.call_args.kwargs
    assert kwargs["session_id"] == "sess-expired"
    assert kwargs["boundary_reason"] == "session_expired"
    assert kwargs["messages"] == cached_agent.conversation_history
    assert kwargs["metadata"]["session_key"] == session_key
    runner._cleanup_agent_resources.assert_called_once_with(cached_agent)
