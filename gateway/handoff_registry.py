from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from hermes_constants import get_hermes_home


DEFAULT_REGISTRY_RELATIVE_PATH = Path("hooks") / "system-b-handoffs" / "config.yaml"


def default_handoff_registry_path() -> Path:
    override = os.getenv("HERMES_HANDOFF_REGISTRY_PATH", "").strip()
    if override:
        return Path(os.path.expanduser(override)).resolve()
    return get_hermes_home() / DEFAULT_REGISTRY_RELATIVE_PATH


def load_external_handoff_registry(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    registry_path = Path(path).expanduser() if path else default_handoff_registry_path()
    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "handoffs": [], "path": str(registry_path)}
    except Exception:
        return {"version": 1, "handoffs": [], "path": str(registry_path)}

    if not isinstance(raw, dict):
        return {"version": 1, "handoffs": [], "path": str(registry_path)}

    routes = raw.get("handoffs")
    if not isinstance(routes, list):
        routes = raw.get("routes")
    if not isinstance(routes, list):
        routes = []

    return {
        "version": raw.get("version") or 1,
        "handoffs": [route for route in routes if isinstance(route, dict)],
        "path": str(registry_path),
    }


def iter_external_handoffs(
    *,
    kind: str | None = None,
    enabled_only: bool = True,
    registry: dict[str, Any] | None = None,
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    loaded = registry or load_external_handoff_registry(path)
    handoffs = loaded.get("handoffs") or []
    results: list[dict[str, Any]] = []
    for raw in handoffs:
        if not isinstance(raw, dict):
            continue
        if enabled_only and raw.get("enabled", True) is False:
            continue
        if kind and str(raw.get("kind") or "").strip() != kind:
            continue
        route = dict(raw)
        route.setdefault("registry_path", loaded.get("path", ""))
        results.append(route)
    return results


def discord_handoff_routes_from_registry(
    registry: dict[str, Any] | None = None,
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for raw in iter_external_handoffs(kind="discord_thread_handoff", registry=registry, path=path):
        target = str(
            raw.get("target_channel_id")
            or raw.get("target_id")
            or raw.get("channel_id")
            or ""
        ).strip()
        if not target:
            continue
        route = dict(raw)
        route["target_channel_id"] = target
        routes.append(route)
    return routes
