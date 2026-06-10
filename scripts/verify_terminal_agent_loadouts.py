#!/usr/bin/env python3
"""Smoke-test terminal_agent loadout metadata across Claude and Codex."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.display import build_tool_preview, get_cute_tool_message
from model_tools import handle_function_call

DEFAULT_PROJECT_CWD = Path.cwd()

CASES = [
    {
        "id": "claude-default",
        "runtime": "claude",
        "loadout": "default",
        "task": "Reply with exactly: CLAUDE DEFAULT TERMINAL_AGENT SMOKE OK",
        "expected_result": "CLAUDE DEFAULT TERMINAL_AGENT SMOKE OK",
        "expected_label": "Claude Code",
    },
    {
        "id": "claude-deep-coding",
        "runtime": "claude",
        "loadout": "deep-coding",
        "task": "Reply with exactly: CLAUDE DEEP TERMINAL_AGENT SMOKE OK",
        "expected_result": "CLAUDE DEEP TERMINAL_AGENT SMOKE OK",
        "expected_label": "Claude Code",
    },
    {
        "id": "codex-default",
        "runtime": "codex",
        "loadout": "default",
        "task": "Reply with exactly: CODEX DEFAULT TERMINAL_AGENT SMOKE OK",
        "expected_result": "CODEX DEFAULT TERMINAL_AGENT SMOKE OK",
        "expected_label": "Codex",
    },
    {
        "id": "codex-research",
        "runtime": "codex",
        "loadout": "research",
        "task": "Reply with exactly: CODEX RESEARCH TERMINAL_AGENT SMOKE OK",
        "expected_result": "CODEX RESEARCH TERMINAL_AGENT SMOKE OK",
        "expected_label": "Codex",
    },
]


class SmokeFailure(RuntimeError):
    pass


def _extract_result_text(payload: dict) -> str:
    parsed = payload.get("parsed_result")
    if isinstance(parsed, dict):
        result = str(parsed.get("result") or "").strip()
        if result:
            return result
    stdout = str(payload.get("stdout") or "").strip()
    return stdout


def _verify_case(case: dict, cwd: str, live: bool) -> dict:
    args = {
        "task": case["task"],
        "runtime": case["runtime"],
        "cwd": cwd,
        "explicit_loadout": case["loadout"],
        "dry_run": not live,
    }
    if case["runtime"] == "claude":
        args["max_turns"] = 1

    raw = handle_function_call("terminal_agent", args, task_id=f"smoke-{case['id']}")
    payload = json.loads(raw)
    if not payload.get("success"):
        raise SmokeFailure(f"{case['id']}: terminal_agent returned success=false: {payload}")

    applied = str(payload.get("applied_loadout") or "").strip()
    if applied != case["loadout"]:
        raise SmokeFailure(f"{case['id']}: expected applied_loadout={case['loadout']!r}, got {applied!r}")

    launch_notice = str(payload.get("launch_notice") or "")
    expected_notice = f"loadout: {case['loadout']}"
    if expected_notice not in launch_notice:
        raise SmokeFailure(f"{case['id']}: launch_notice missing {expected_notice!r}: {launch_notice!r}")

    preview = build_tool_preview("terminal_agent", args)
    cute = get_cute_tool_message("terminal_agent", args, 0.1, result=json.dumps(payload))
    expected_preview = f"{case['expected_label']} · loadout {case['loadout']}"
    if preview != expected_preview:
        raise SmokeFailure(f"{case['id']}: preview mismatch: expected {expected_preview!r}, got {preview!r}")
    if expected_preview not in cute:
        raise SmokeFailure(f"{case['id']}: cute message missing {expected_preview!r}: {cute!r}")

    result_text = None
    if live:
        result_text = _extract_result_text(payload)
        if result_text != case["expected_result"]:
            raise SmokeFailure(
                f"{case['id']}: live result mismatch: expected {case['expected_result']!r}, got {result_text!r}"
            )
        if int(payload.get("exit_code", 1)) != 0:
            raise SmokeFailure(f"{case['id']}: non-zero exit code: {payload.get('exit_code')!r}")

    return {
        "id": case["id"],
        "runtime": case["runtime"],
        "loadout": case["loadout"],
        "dry_run": payload.get("dry_run"),
        "launch_notice": launch_notice,
        "preview": preview,
        "cute_message": cute,
        "result_text": result_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=str(DEFAULT_PROJECT_CWD), help="Project directory to launch inside.")
    parser.add_argument("--live", action="store_true", help="Run the real one-shot Claude/Codex commands instead of dry-run.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output.")
    args = parser.parse_args()

    cwd = str(Path(args.cwd).expanduser())
    results = []
    try:
        for case in CASES:
            results.append(_verify_case(case, cwd=cwd, live=args.live))
    except SmokeFailure as exc:
        if args.json:
            print(json.dumps({"success": False, "error": str(exc), "results": results}, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
            for result in results:
                print(f"PASS: {result['id']} -> {result['launch_notice']}")
        return 1

    if args.json:
        print(json.dumps({"success": True, "cwd": cwd, "live": args.live, "results": results}, indent=2))
    else:
        mode = "live" if args.live else "dry-run"
        print(f"terminal_agent loadout smoke passed ({mode})")
        for result in results:
            suffix = f" -> {result['result_text']}" if result.get("result_text") else ""
            print(f"PASS: {result['id']} :: {result['launch_notice']} :: {result['cute_message']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
