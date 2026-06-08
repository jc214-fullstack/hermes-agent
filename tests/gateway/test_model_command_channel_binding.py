"""Regression tests for gateway /model --channel persistence."""

import yaml
import pytest

import gateway.run as gateway_run
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._running_agents = {}
    runner.config = GatewayConfig(
        platforms={
            Platform.DISCORD: PlatformConfig(enabled=True, token="fake-token", extra={})
        }
    )
    return runner


def _make_event(text: str, *, chat_id: str = "thread-123", parent_chat_id: str | None = "parent-777"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id=chat_id,
            parent_chat_id=parent_chat_id,
            chat_type="thread" if parent_chat_id else "group",
            user_id="u1",
            user_name="tester",
        ),
    )


def _fake_switch_result():
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model="gpt-5.5",
        target_provider="openai-codex",
        provider_changed=True,
        api_key="sk-test",
        base_url="https://chatgpt.com/backend-api/codex",
        api_mode="codex_responses",
        provider_label="OpenAI Codex",
        is_global=False,
    )


def _setup_home(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    cfg_path = hermes_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"model": {"default": "old-model", "provider": "openrouter"}, "discord": {}, "providers": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("hermes_cli.config.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kw: _fake_switch_result())
    return cfg_path


@pytest.mark.asyncio
async def test_model_channel_persists_parent_channel_binding_by_default(tmp_path, monkeypatch):
    cfg_path = _setup_home(tmp_path, monkeypatch)
    runner = _make_runner()

    result = await runner._handle_model_command(
        _make_event("/model gpt-5.5 --channel")
    )

    assert result is not None
    assert "Saved channel default for `parent-777`" in result

    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["discord"]["channel_model_bindings"] == [
        {
            "id": "parent-777",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_mode": "codex_responses",
        }
    ]
    assert runner.config.platforms[Platform.DISCORD].extra["channel_model_bindings"] == [
        {
            "id": "parent-777",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_mode": "codex_responses",
        }
    ]


@pytest.mark.asyncio
async def test_model_channel_explicit_target_updates_existing_binding(tmp_path, monkeypatch):
    cfg_path = _setup_home(tmp_path, monkeypatch)
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "model": {"default": "old-model", "provider": "openrouter"},
                "discord": {
                    "channel_model_bindings": [
                        {"id": "child-999", "model": "old", "provider": "old-provider"}
                    ]
                },
                "providers": {},
            }
        ),
        encoding="utf-8",
    )
    runner = _make_runner()
    runner.config.platforms[Platform.DISCORD].extra["channel_model_bindings"] = [
        {"id": "child-999", "model": "old", "provider": "old-provider"}
    ]

    result = await runner._handle_model_command(
        _make_event("/model gpt-5.5 --channel child-999", chat_id="thread-123", parent_chat_id="parent-777")
    )

    assert result is not None
    assert "Saved channel default for `child-999`" in result

    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["discord"]["channel_model_bindings"] == [
        {
            "id": "child-999",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_mode": "codex_responses",
        }
    ]
    assert runner.config.platforms[Platform.DISCORD].extra["channel_model_bindings"] == [
        {
            "id": "child-999",
            "model": "gpt-5.5",
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_mode": "codex_responses",
        }
    ]
