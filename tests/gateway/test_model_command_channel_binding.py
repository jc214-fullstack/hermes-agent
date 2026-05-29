"""Tests for gateway /model channel-default persistence via --channel."""

import yaml
import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


class _PlatformCfg:
    def __init__(self):
        self.extra = {}


class _Cfg:
    def __init__(self):
        self.platforms = {Platform.DISCORD: _PlatformCfg()}


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner.config = _Cfg()
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._running_agents = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    return runner


def _make_event(text="/model gpt-5.3-codex --provider openai-codex --channel"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id="1509508958614978712",
            parent_chat_id="1509377909121618063",
            chat_type="group",
        ),
    )


def _fake_switch_result():
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model="gpt-5.3-codex",
        target_provider="openai-codex",
        provider_changed=False,
        api_key="sk-test",
        base_url="https://chatgpt.com/backend-api/codex",
        api_mode="codex_responses",
        provider_label="OpenAI Codex",
        is_global=False,
    )


@pytest.mark.asyncio
async def test_model_channel_persists_parent_binding_for_discord_thread(tmp_path, monkeypatch):
    import gateway.run as gateway_run

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    cfg_path = hermes_home / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"model": {"default": "gpt-5.4"}, "discord": {}}), encoding="utf-8")

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kw: _fake_switch_result())
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("hermes_cli.config.get_hermes_home", lambda: hermes_home)

    runner = _make_runner()
    result = await runner._handle_model_command(_make_event())

    assert result is not None
    assert "Saved channel default" in result
    assert "1509377909121618063" in result

    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    bindings = written["discord"]["channel_model_bindings"]
    assert any(
        b.get("id") == "1509377909121618063"
        and b.get("model") == "gpt-5.3-codex"
        and b.get("provider") == "openai-codex"
        for b in bindings
    )


@pytest.mark.asyncio
async def test_model_channel_explicit_id_overrides_parent(tmp_path, monkeypatch):
    import gateway.run as gateway_run

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    cfg_path = hermes_home / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"discord": {}}), encoding="utf-8")

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kw: _fake_switch_result())
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("hermes_cli.config.get_hermes_home", lambda: hermes_home)

    runner = _make_runner()
    result = await runner._handle_model_command(
        _make_event("/model gpt-5.3-codex --provider openai-codex --channel 999999")
    )

    assert result is not None
    assert "999999" in result

    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    bindings = written["discord"]["channel_model_bindings"]
    assert any(b.get("id") == "999999" for b in bindings)
