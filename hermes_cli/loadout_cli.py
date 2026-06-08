"""`hermes loadout` — route, apply, inspect, and launch terminal loadouts."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_LOADOUT_REPO = Path.home() / "projects" / "hermes-coding-terminal-load-out-system"
DEFAULT_RUNTIME_HOMES = {
    "claude": Path.home() / ".claude",
    "codex": Path.home() / ".codex",
}
RUNTIME_BINARIES = {
    "claude": "claude",
    "codex": "codex",
}


def _repo_root(args) -> Path:
    repo = Path(
        getattr(args, "repo", None)
        or os.environ.get("HERMES_LOADOUT_REPO")
        or DEFAULT_LOADOUT_REPO
    ).expanduser()
    script = repo / "scripts" / "apply_loadout.py"
    if not script.exists():
        raise FileNotFoundError(
            f"Loadout repo not found or incomplete at {repo} "
            f"(missing {script.relative_to(repo)})"
        )
    return repo


def _runtime_home(runtime: str, explicit: str | None = None) -> Path:
    if runtime not in DEFAULT_RUNTIME_HOMES:
        raise KeyError(f"Unknown runtime: {runtime}")
    return Path(explicit).expanduser() if explicit else DEFAULT_RUNTIME_HOMES[runtime]


def _default_runtime_home(runtime: str) -> Path:
    return DEFAULT_RUNTIME_HOMES[runtime]


def _manifest_path(runtime: str, home: Path | None = None) -> Path:
    return (home or _default_runtime_home(runtime)) / "hermes-loadout.json"


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_repo_script(
    repo_root: Path,
    script_name: str,
    extra_args: list[str],
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(repo_root / "scripts" / script_name), *extra_args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )


def _parse_repo_json(result: subprocess.CompletedProcess[str], action: str) -> dict[str, Any]:
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"loadout {action} failed")
    text = (result.stdout or "").strip()
    if not text:
        raise RuntimeError(f"loadout {action} returned no output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"loadout {action} returned invalid JSON: {exc}") from exc


def _resolve_loadout(
    repo_root: Path,
    runtime: str,
    request_text: str,
    explicit_loadout: str | None = None,
) -> str:
    cmd = ["--runtime", runtime, "--request", request_text]
    if explicit_loadout:
        cmd += ["--explicit-loadout", explicit_loadout]
    result = _run_repo_script(repo_root, "resolve_route.py", cmd)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "loadout resolution failed")
    return result.stdout.strip().splitlines()[-1].strip()


def _apply_loadout(
    repo_root: Path,
    runtime: str,
    *,
    loadout: str | None,
    request_text: str | None,
    output_root: Path,
    target_home: bool,
    cwd: str | None = None,
) -> dict[str, Any]:
    if not loadout and not request_text:
        raise RuntimeError("Provide either --loadout or --request")
    cmd = [
        "--runtime",
        runtime,
        "--output-root",
        str(output_root),
        "--format",
        "json",
    ]
    if loadout:
        cmd += ["--loadout", loadout]
    if request_text:
        cmd += ["--request", request_text]
    if cwd:
        cmd += ["--cwd", cwd]
    if target_home:
        cmd.append("--target-home")
    result = _run_repo_script(repo_root, "apply_loadout.py", cmd)
    payload = _parse_repo_json(result, "apply")
    payload.setdefault(
        "manifest_path",
        str(_manifest_path(runtime, output_root if target_home else output_root / runtime)),
    )
    return payload


def _print_payload(payload: dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            print(f"{key}: {json.dumps(value, indent=2)}")
        else:
            print(f"{key}: {value}")
    return 0


def _status_payload(runtime: str, home: Path) -> dict[str, Any]:
    manifest_path = _manifest_path(runtime, home)
    manifest = _read_manifest(manifest_path)
    return {
        "runtime": runtime,
        "home": str(home),
        "manifest_path": str(manifest_path),
        "exists": manifest is not None,
        "manifest": manifest,
    }


def _cmd_status(args) -> int:
    runtime_arg = getattr(args, "runtime", "all")
    as_json = bool(getattr(args, "json", False))
    runtimes = [runtime_arg] if runtime_arg != "all" else ["claude", "codex"]
    payload = [_status_payload(runtime, _runtime_home(runtime)) for runtime in runtimes]
    if as_json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2))
        return 0
    for item in payload:
        print(f"runtime: {item['runtime']}")
        print(f"home: {item['home']}")
        print(f"manifest_path: {item['manifest_path']}")
        if not item["exists"]:
            print("status: missing")
        else:
            manifest = item["manifest"] or {}
            print(f"status: active loadout={manifest.get('loadout')} runtime={manifest.get('runtime')}")
            print(f"managed_files: {len(manifest.get('managed_files') or [])}")
        if len(payload) > 1 and item is not payload[-1]:
            print()
    return 0


def _cmd_resolve(args) -> int:
    repo_root = _repo_root(args)
    loadout = _resolve_loadout(repo_root, args.runtime, args.request, args.explicit_loadout)
    if args.json:
        print(json.dumps({"runtime": args.runtime, "request": args.request, "loadout": loadout}, indent=2))
        return 0
    print(loadout)
    return 0


def _cmd_apply(args) -> int:
    repo_root = _repo_root(args)
    runtime = args.runtime
    output_root = _runtime_home(runtime, args.home) if args.target_home else Path(args.output_root).expanduser()
    result = _apply_loadout(
        repo_root,
        runtime,
        loadout=args.loadout,
        request_text=args.request,
        output_root=output_root,
        target_home=args.target_home,
    )
    payload = {
        "runtime": runtime,
        "home": str(output_root) if args.target_home else None,
        "output_root": result.get("output_root"),
        "manifest_path": result.get("manifest_path"),
        "manifest": result.get("manifest"),
        "launch_notice": result.get("launch_notice"),
    }
    return _print_payload(payload, args.json)


def _claude_home_override_allowed(runtime: str, home: Path) -> None:
    if runtime != "claude":
        return
    default_home = _default_runtime_home("claude")
    if home != default_home:
        raise RuntimeError(
            "Claude launch currently supports only the default live home. "
            f"Use {default_home} or omit --home."
        )


def _cmd_launch(args) -> int:
    repo_root = _repo_root(args)
    runtime = args.runtime
    home = _runtime_home(runtime, args.home)
    _claude_home_override_allowed(runtime, home)
    cwd = str(Path(args.cwd).expanduser()) if args.cwd else os.getcwd()

    if args.dry_run:
        with tempfile.TemporaryDirectory(prefix=f"hermes-loadout-{runtime}-") as tmp_dir:
            result = _apply_loadout(
                repo_root,
                runtime,
                loadout=args.loadout,
                request_text=args.request,
                output_root=Path(tmp_dir),
                target_home=False,
                cwd=cwd,
            )
            binary = shutil.which(RUNTIME_BINARIES[runtime])
            if not binary:
                raise FileNotFoundError(f"Could not find `{RUNTIME_BINARIES[runtime]}` on PATH")
            child_args = list(args.arg or [])
            payload = {
                "runtime": runtime,
                "home": str(home),
                "cwd": cwd,
                "applied_loadout": (result.get("manifest") or {}).get("loadout"),
                "manifest_path": result.get("manifest_path"),
                "launch_notice": result.get("launch_notice"),
                "command": [binary, *child_args],
                "dry_run": True,
            }
            return _print_payload(payload, args.json)

    result = _apply_loadout(
        repo_root,
        runtime,
        loadout=args.loadout,
        request_text=args.request,
        output_root=home,
        target_home=True,
        cwd=cwd,
    )
    binary = shutil.which(RUNTIME_BINARIES[runtime])
    if not binary:
        raise FileNotFoundError(f"Could not find `{RUNTIME_BINARIES[runtime]}` on PATH")

    child_args = list(args.arg or [])
    cmd = [binary, *child_args]
    env = os.environ.copy()
    if runtime == "codex":
        env["CODEX_HOME"] = str(home)

    payload = {
        "runtime": runtime,
        "home": str(home),
        "cwd": cwd,
        "applied_loadout": (result.get("manifest") or {}).get("loadout"),
        "manifest_path": result.get("manifest_path"),
        "launch_notice": result.get("launch_notice"),
        "command": cmd,
    }

    if result.get("launch_notice"):
        print(result["launch_notice"])
    print(f"launching: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    return completed.returncode


def loadout_command(args) -> int:
    sub = getattr(args, "loadout_command", None)
    try:
        if sub in {None, "", "status"}:
            return _cmd_status(args)
        if sub == "resolve":
            return _cmd_resolve(args)
        if sub == "apply":
            return _cmd_apply(args)
        if sub == "launch":
            return _cmd_launch(args)
        print(f"Unknown loadout subcommand: {sub}", file=sys.stderr)
        return 1
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "loadout",
        help="Resolve, apply, inspect, and launch Claude/Codex loadouts",
        description=(
            "Use the external Hermes coding terminal loadout repo to resolve a request, "
            "apply a runtime surface, inspect active manifests, or launch Claude/Codex "
            "after a live-home apply."
        ),
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=f"Path to the loadout repo (default: {DEFAULT_LOADOUT_REPO})",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output when supported")
    sub = parser.add_subparsers(dest="loadout_command")

    p_status = sub.add_parser("status", help="Show active live-home loadout manifests")
    p_status.add_argument("--runtime", choices=["claude", "codex", "all"], default="all")
    p_status.add_argument("--json", action="store_true", help="Print JSON output")

    p_resolve = sub.add_parser("resolve", help="Resolve a request into a loadout name")
    p_resolve.add_argument("--runtime", required=True, choices=["claude", "codex"])
    p_resolve.add_argument("--request", required=True)
    p_resolve.add_argument("--explicit-loadout", default=None)
    p_resolve.add_argument("--json", action="store_true", help="Print JSON output")

    p_apply = sub.add_parser("apply", help="Apply a loadout to output or a live runtime home")
    p_apply.add_argument("--runtime", required=True, choices=["claude", "codex"])
    p_apply.add_argument("--loadout", default=None)
    p_apply.add_argument("--request", default=None)
    p_apply.add_argument("--output-root", default="output")
    p_apply.add_argument("--target-home", action="store_true")
    p_apply.add_argument("--home", default=None, help="Override runtime home when using --target-home")
    p_apply.add_argument("--json", action="store_true", help="Print JSON output")

    p_launch = sub.add_parser("launch", help="Apply a live-home loadout, then launch Claude or Codex")
    p_launch.add_argument("runtime", choices=["claude", "codex"])
    p_launch.add_argument("--loadout", default=None)
    p_launch.add_argument("--request", default=None)
    p_launch.add_argument("--home", default=None, help="Override runtime home path")
    p_launch.add_argument("--cwd", default=None, help="Working directory for the launched runtime")
    p_launch.add_argument("--dry-run", action="store_true", help="Show the apply+launch plan without spawning the runtime")
    p_launch.add_argument("--json", action="store_true", help="Print JSON output")
    p_launch.add_argument("--arg", action="append", default=[], help="Argument forwarded to the runtime binary (repeatable)")

    parser.set_defaults(func=loadout_command)
