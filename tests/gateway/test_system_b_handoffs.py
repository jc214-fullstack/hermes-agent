from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

import pytest

from gateway.config import PlatformConfig
from gateway.handoff_registry import discord_handoff_routes_from_registry, load_external_handoff_registry


def _ensure_discord_mock() -> None:
    if "discord" in sys.modules and hasattr(sys.modules["discord"], "__file__"):
        return
    discord_mod = MagicMock()
    discord_mod.Intents.default.return_value = MagicMock()
    discord_mod.Client = MagicMock
    discord_mod.File = MagicMock
    discord_mod.DMChannel = type("DMChannel", (), {})
    discord_mod.Thread = type("Thread", (), {})
    discord_mod.ForumChannel = type("ForumChannel", (), {})
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

from plugins.platforms.discord.adapter import DiscordAdapter  # noqa: E402


HOOK_HANDLER_PATH = Path("/home/imagi/.hermes/hooks/system-b-handoffs/handler.py")
REGISTRY_PATH = Path("/home/imagi/.hermes/hooks/system-b-handoffs/config.yaml")


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("system_b_handoffs_handler", HOOK_HANDLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def adapter(monkeypatch):
    config = PlatformConfig(enabled=True, token="fake-token")
    adapter = DiscordAdapter(config)
    adapter._client = SimpleNamespace(user=SimpleNamespace(id=999))
    return adapter


def test_external_handoff_registry_contains_deep_work_and_system_b_routes():
    registry = load_external_handoff_registry(REGISTRY_PATH)
    names = {route.get("name") for route in registry["handoffs"]}
    assert names >= {"deep-work", "media-analysis-intake", "media-analysis-to-queued-kanban"}

    discord_routes = discord_handoff_routes_from_registry(registry)
    assert discord_routes == [
        {
            "name": "deep-work",
            "kind": "discord_thread_handoff",
            "enabled": True,
            "label": "Deep Work",
            "target_channel_id": "1510042356487950376",
            "trigger_phrases": ["push this to deep work", "push this to a deep work channel"],
            "auto_run_marker": "[AUTO_RUN_DEEP_WORK]",
            "thread_name_prefix": "Deep Work",
            "registry_path": str(REGISTRY_PATH),
        }
    ]


def test_discord_adapter_reads_external_handoff_registry(adapter, monkeypatch):
    monkeypatch.setenv("HERMES_HANDOFF_REGISTRY_PATH", str(REGISTRY_PATH))
    adapter.config.extra["handoff_routes"] = []
    adapter.config.extra["deep_work_channel_id"] = ""

    routes = adapter._discord_handoff_routes()

    assert routes[0]["name"] == "deep-work"
    assert routes[0]["target_channel_id"] == "1510042356487950376"
    assert routes[0]["auto_run_marker"] == "[AUTO_RUN_DEEP_WORK]"


@pytest.mark.asyncio
async def test_unified_hook_dispatches_agent_start_and_end(monkeypatch):
    monkeypatch.setenv("HERMES_HANDOFF_REGISTRY_PATH", str(REGISTRY_PATH))
    module = _load_hook_module()
    seen: list[tuple[str, str]] = []

    monkeypatch.setattr(
        module,
        "_run_media_analysis_workspace_init",
        lambda route, context: seen.append(("start", str(route.get("name")))),
    )
    monkeypatch.setattr(
        module,
        "_run_queued_kanban_thread_guard",
        lambda route, context: seen.append(("end", str(route.get("name")))),
    )

    await module.handle("agent:start", {"platform": "discord", "chat_id": "1509517024345194617"})
    await module.handle("agent:end", {"platform": "discord", "chat_id": "1510118014312255659"})

    assert ("start", "media-analysis-intake") in seen
    assert ("end", "media-analysis-to-queued-kanban") in seen
