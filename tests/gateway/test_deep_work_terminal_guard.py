"""Regression tests for Deep Work terminal safety guardrails."""

import json

from gateway.session_context import clear_session_vars, set_session_vars
from tools.terminal_tool import (
    _deep_work_gateway_restart_guard,
    _looks_like_gateway_restart_command,
    terminal_tool,
)


def test_gateway_restart_command_matcher_detects_common_shell_forms():
    assert _looks_like_gateway_restart_command("hermes gateway restart")
    assert _looks_like_gateway_restart_command("cd repo && hermes gateway restart --system")
    assert _looks_like_gateway_restart_command("uv run hermes gateway restart")
    assert not _looks_like_gateway_restart_command("hermes gateway status")


def test_deep_work_gateway_restart_guard_blocks_discord_deep_work(monkeypatch):
    monkeypatch.delenv("HERMES_ALLOW_DEEP_WORK_GATEWAY_RESTART", raising=False)
    tokens = set_session_vars(
        platform="discord",
        chat_id="1510072796959477963",
        chat_name="Command Center / #deep-work / Deep Work System",
        thread_id="1510072796959477963",
        user_id="u1",
        user_name="Mike",
        session_key="discord:1510072796959477963",
    )
    try:
        error = _deep_work_gateway_restart_guard("hermes gateway restart")
        assert error is not None
        assert "Blocked" in error
    finally:
        clear_session_vars(tokens)


def test_terminal_tool_returns_blocked_without_executing_restart(monkeypatch):
    monkeypatch.delenv("HERMES_ALLOW_DEEP_WORK_GATEWAY_RESTART", raising=False)
    tokens = set_session_vars(
        platform="discord",
        chat_id="1510072796959477963",
        chat_name="Command Center / #deep-work / Deep Work System",
        thread_id="1510072796959477963",
        user_id="u1",
        user_name="Mike",
        session_key="discord:1510072796959477963",
    )
    try:
        result = json.loads(terminal_tool("hermes gateway restart"))
        assert result["status"] == "blocked"
        assert result["exit_code"] == -1
        assert "Deep Work sessions may not run" in result["error"]
    finally:
        clear_session_vars(tokens)
