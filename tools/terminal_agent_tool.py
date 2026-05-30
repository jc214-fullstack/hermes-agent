#!/usr/bin/env python3
"""One-shot Claude/Codex runtime launch backed by Hermes loadouts."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hermes_cli.loadout_cli import (
    _apply_loadout,
    _default_runtime_home,
    _repo_root,
    _runtime_home,
)
from tools.registry import registry, tool_error, tool_result

RUNTIME_BINARIES = {
    "claude": "claude",
    "codex": "codex",
}

_RUNTIME_PATTERNS = [
    (re.compile(r"\bclaude(?:\s+code)?\b", re.IGNORECASE), "claude"),
    (re.compile(r"\bcodex\b", re.IGNORECASE), "codex"),
]


def _infer_runtime(task: str, runtime: str | None = None) -> str:
    if runtime:
        if runtime not in RUNTIME_BINARIES:
            raise ValueError(f"Unsupported runtime: {runtime}")
        return runtime
    matches = []
    for pattern, candidate in _RUNTIME_PATTERNS:
        if pattern.search(task or ""):
            matches.append(candidate)
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        raise ValueError(
            "Task mentions multiple runtimes. Pass runtime explicitly as `claude` or `codex`."
        )
    raise ValueError(
        "Could not infer runtime from task text. Mention Claude/Claude Code or Codex, "
        "or pass runtime explicitly."
    )


def _build_runtime_command(runtime: str, task: str, max_turns: int) -> list[str]:
    if runtime == "claude":
        return ["claude", "-p", task, "--output-format", "json", "--max-turns", str(max_turns)]
    if runtime == "codex":
        return ["codex", "exec", "--full-auto", task]
    raise ValueError(f"Unsupported runtime: {runtime}")


def _extract_claude_result(stdout: str) -> Any:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _validate_home_override(runtime: str, home: Path) -> None:
    if runtime != "claude":
        return
    default_home = _default_runtime_home("claude")
    if home != default_home:
        raise ValueError(
            "Claude launch currently supports only the default live home. "
            f"Use {default_home} or omit home."
        )


def _run_terminal_agent(
    *,
    task: str,
    runtime: str | None = None,
    cwd: str | None = None,
    explicit_loadout: str | None = None,
    repo: str | None = None,
    home: str | None = None,
    max_turns: int = 8,
    dry_run: bool = False,
) -> str:
    if not task or not task.strip():
        return tool_error("task is required", success=False)

    try:
        selected_runtime = _infer_runtime(task, runtime)
        args = type("Args", (), {"repo": repo})()
        repo_root = _repo_root(args)
        runtime_home = _runtime_home(selected_runtime, home)
        _validate_home_override(selected_runtime, runtime_home)
        workdir = str(Path(cwd).expanduser()) if cwd else os.getcwd()

        if not shutil.which(RUNTIME_BINARIES[selected_runtime]):
            return tool_error(
                f"Could not find `{RUNTIME_BINARIES[selected_runtime]}` on PATH",
                success=False,
            )

        apply_result = _apply_loadout(
            repo_root,
            selected_runtime,
            loadout=explicit_loadout,
            request_text=task,
            output_root=runtime_home,
            target_home=True,
            cwd=workdir,
        )
        manifest = apply_result.get("manifest") or {}
        command = _build_runtime_command(selected_runtime, task, max_turns)

        payload = {
            "success": True,
            "runtime": selected_runtime,
            "cwd": workdir,
            "home": str(runtime_home),
            "applied_loadout": manifest.get("loadout"),
            "manifest_path": apply_result.get("manifest_path"),
            "launch_notice": apply_result.get("launch_notice"),
            "command": command,
            "dry_run": dry_run,
        }
        if dry_run:
            return tool_result(payload)

        env = os.environ.copy()
        if selected_runtime == "codex":
            env["CODEX_HOME"] = str(runtime_home)

        completed = subprocess.run(
            command,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        payload.update(
            {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        if selected_runtime == "claude":
            payload["parsed_result"] = _extract_claude_result(completed.stdout)
        return tool_result(payload)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return tool_error(str(exc), success=False)


def check_terminal_agent_requirements() -> bool:
    return True


TERMINAL_AGENT_SCHEMA = {
    "name": "terminal_agent",
    "description": (
        "Launch a one-shot Claude Code or Codex task through the Hermes loadout system. "
        "Use this when the user explicitly asks you to use Claude Code or Codex. "
        "If runtime is omitted, infer it from the task text. The tool resolves the loadout, "
        "applies it to the runtime home, runs the task, and returns structured output for review."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The one-shot task to run inside Claude Code or Codex.",
            },
            "runtime": {
                "type": "string",
                "enum": ["claude", "codex"],
                "description": "Optional explicit runtime. Omit to infer it from the task text.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the runtime process.",
            },
            "explicit_loadout": {
                "type": "string",
                "description": "Optional explicit loadout override. Usually omit and let the resolver choose.",
            },
            "repo": {
                "type": "string",
                "description": "Optional path to the external loadout repo.",
            },
            "home": {
                "type": "string",
                "description": "Optional runtime home override. Codex only; Claude uses the default live home.",
            },
            "max_turns": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Claude max-turn limit for one-shot print mode. Ignored by Codex.",
                "default": 8,
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, resolve/apply and return the launch plan without executing the runtime.",
                "default": False,
            },
        },
        "required": ["task"],
    },
}


registry.register(
    name="terminal_agent",
    toolset="terminal",
    schema=TERMINAL_AGENT_SCHEMA,
    handler=_run_terminal_agent,
    check_fn=check_terminal_agent_requirements,
    requires_env=[],
    is_async=False,
    description="One-shot Claude Code/Codex launch through Hermes loadouts.",
    emoji="🧠",
)
