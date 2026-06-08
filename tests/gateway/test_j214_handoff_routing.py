import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gateway.run as gateway_run
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key


def _ensure_discord_mock():
    if "discord" in sys.modules and hasattr(sys.modules["discord"], "__file__"):
        return
    discord_mod = MagicMock()
    discord_mod.Intents.default.return_value = MagicMock()
    discord_mod.Client = MagicMock
    discord_mod.File = MagicMock
    discord_mod.DMChannel = type("DMChannel", (), {})
    discord_mod.Thread = type("Thread", (), {})
    discord_mod.ForumChannel = type("ForumChannel", (), {})
    discord_mod.MessageType = SimpleNamespace(default=0, reply=1)
    discord_mod.ui = SimpleNamespace(View=object, button=lambda *a, **k: (lambda fn: fn), Button=object)
    discord_mod.ButtonStyle = SimpleNamespace(success=1, primary=2, secondary=2, danger=3, green=1, grey=2, blurple=2, red=3)
    discord_mod.Color = SimpleNamespace(orange=lambda: 1, green=lambda: 2, blue=lambda: 3, red=lambda: 4, purple=lambda: 5)
    discord_mod.Interaction = object
    discord_mod.Embed = MagicMock
    discord_mod.app_commands = SimpleNamespace(
        describe=lambda **kwargs: (lambda fn: fn),
        choices=lambda **kwargs: (lambda fn: fn),
        Choice=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    ext_mod = MagicMock()
    commands_mod = MagicMock()
    commands_mod.Bot = MagicMock
    ext_mod.commands = commands_mod
    sys.modules.setdefault("discord", discord_mod)
    sys.modules.setdefault("discord.ext", ext_mod)
    sys.modules.setdefault("discord.ext.commands", commands_mod)


_ensure_discord_mock()
import plugins.platforms.discord.adapter as discord_platform  # noqa: E402
from plugins.platforms.discord.adapter import DiscordAdapter  # noqa: E402


def _make_runner_with_binding():
    runner = object.__new__(gateway_run.GatewayRunner)
    runner.adapters = {}
    runner.session_store = None
    runner.config = GatewayConfig(
        platforms={
            Platform.DISCORD: PlatformConfig(
                enabled=True,
                token="fake",
                extra={
                    "channel_model_bindings": [
                        {
                            "id": "parent-chan",
                            "model": "gpt-5.4",
                            "provider": "openai-codex",
                            "base_url": "https://chatgpt.com/backend-api/codex",
                            "api_mode": "codex_responses",
                        }
                    ]
                },
            )
        }
    )
    runner._session_model_overrides = {}
    return runner


def test_channel_model_binding_inherits_from_parent_thread():
    runner = _make_runner_with_binding()
    source = SessionSource(
        platform=Platform.DISCORD,
        user_id="u1",
        chat_id="thread-1",
        parent_chat_id="parent-chan",
        chat_type="thread",
    )
    binding = runner._channel_model_binding_for_source(source)
    assert binding is not None
    assert binding["model"] == "gpt-5.4"
    assert binding["provider"] == "openai-codex"


def test_resolve_session_runtime_applies_channel_binding(monkeypatch):
    runner = _make_runner_with_binding()
    monkeypatch.setattr(gateway_run, "_resolve_gateway_model", lambda cfg=None: "anthropic/claude")
    monkeypatch.setattr(
        gateway_run,
        "_resolve_runtime_agent_kwargs",
        lambda: {
            "provider": "openrouter",
            "api_key": "router-key",
            "base_url": "https://openrouter.ai/api/v1",
            "api_mode": "chat_completions",
        },
    )
    source = SessionSource(
        platform=Platform.DISCORD,
        user_id="u1",
        chat_id="thread-1",
        parent_chat_id="parent-chan",
        chat_type="thread",
    )
    model, runtime_kwargs = runner._resolve_session_agent_runtime(source=source, user_config={})
    assert model == "gpt-5.4"
    assert runtime_kwargs["provider"] == "openai-codex"
    assert runtime_kwargs["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert runtime_kwargs["api_mode"] == "codex_responses"


def _make_reset_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")})
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._background_tasks = set()
    runner._queued_events = {}
    runner._session_db = MagicMock()
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner._cleanup_agent_resources = MagicMock()
    runner._evict_cached_agent = MagicMock()
    runner._clear_session_boundary_security_state = MagicMock()
    runner._release_running_agent_state = MagicMock()
    runner._invalidate_session_run_generation = MagicMock()
    runner._set_session_reasoning_override = MagicMock()
    runner._is_user_authorized = lambda _source: True
    runner._telegram_topic_new_header = lambda _source: None
    runner._is_telegram_topic_lane = lambda _source: False

    source = SessionSource(platform=Platform.TELEGRAM, user_id="u1", chat_id="c1", user_name="tester", chat_type="dm")
    session_key = build_session_key(source)
    session_entry = SessionEntry(session_key=session_key, session_id="sess-old", created_at=datetime.now(), updated_at=datetime.now(), platform=Platform.TELEGRAM, chat_type="dm")
    new_session_entry = SessionEntry(session_key=session_key, session_id="sess-new", created_at=datetime.now(), updated_at=datetime.now(), platform=Platform.TELEGRAM, chat_type="dm")
    runner.session_store = MagicMock()
    runner.session_store.reset_session.return_value = new_session_entry
    runner.session_store.get_or_create_session.return_value = new_session_entry
    runner.session_store._entries = {session_key: session_entry}
    runner.session_store._generate_session_key.return_value = session_key
    runner._resolve_session_agent_runtime = MagicMock(return_value=("gpt-5.4", {"provider": "openai-codex", "base_url": "https://chatgpt.com/backend-api/codex"}))
    return runner, source


@pytest.mark.asyncio
async def test_reset_persists_route_metadata_for_new_session():
    runner, source = _make_reset_runner()
    event = MessageEvent(text="/new", source=source, message_id="m1")
    with patch.object(gateway_run, "_load_gateway_config", return_value={}):
        await runner._handle_reset_command(event)
    runner._session_db.update_session_route_metadata.assert_called_once_with(
        "sess-new",
        model="gpt-5.4",
        billing_provider="openai-codex",
        billing_base_url="https://chatgpt.com/backend-api/codex",
    )


def test_discord_handoff_routes_include_legacy_deep_work(monkeypatch):
    monkeypatch.setattr(discord_platform.discord, "DMChannel", type("DMChannel", (), {}), raising=False)
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="fake", extra={
        "deep_work_channel_id": "999",
        "deep_work_trigger_phrases": ["Push this to deep work", " push this to deep work  "]
    }))
    routes = adapter._discord_handoff_routes()
    assert any(route.get("target_channel_id") == "999" for route in routes)
    assert adapter._match_deep_work_trigger("push this to deep work: please finish this", ["push this to deep work"]) == "push this to deep work"
    assert adapter._strip_deep_work_trigger("push this to deep work: please finish this", "push this to deep work") == "please finish this"
