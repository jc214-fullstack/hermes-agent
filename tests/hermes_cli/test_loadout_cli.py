from __future__ import annotations

import argparse
import json
from pathlib import Path

from hermes_cli import loadout_cli


class DummyCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_real_user_home_prefers_gateway_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_LOADOUT_USER_HOME", str(tmp_path))
    assert loadout_cli._real_user_home() == tmp_path
    assert loadout_cli._default_loadout_repo() == tmp_path / "projects" / "hermes-coding-terminal-load-out-system"
    assert loadout_cli._default_runtime_home("claude") == tmp_path / ".claude"
    assert loadout_cli._default_runtime_home("codex") == tmp_path / ".codex"


def test_status_reads_manifest_from_runtime_home(monkeypatch, capsys, tmp_path):
    home = tmp_path / ".claude"
    home.mkdir()
    manifest = {"runtime": "claude", "loadout": "frontend-design", "managed_files": ["a", "b"]}
    (home / "hermes-loadout.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setenv("HERMES_LOADOUT_USER_HOME", str(tmp_path))

    args = argparse.Namespace(runtime="claude", json=True)
    assert loadout_cli._cmd_status(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime"] == "claude"
    assert payload["manifest"]["loadout"] == "frontend-design"


def test_resolve_uses_repo_script(monkeypatch, capsys, tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "apply_loadout.py").write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(
        loadout_cli,
        "_resolve_loadout",
        lambda repo_root, runtime, request_text, explicit_loadout=None: "research",
    )

    args = argparse.Namespace(repo=str(repo), runtime="claude", request="Research this", explicit_loadout=None, json=True)
    assert loadout_cli._cmd_resolve(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"runtime": "claude", "request": "Research this", "loadout": "research"}


def test_apply_parses_repo_json(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "apply_loadout.py").write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(
        loadout_cli,
        "_run_repo_script",
        lambda *_args, **_kwargs: DummyCompleted(
            returncode=0,
            stdout=json.dumps(
                {
                    "output_root": "/tmp/out/claude",
                    "manifest_path": "/tmp/out/claude/hermes-loadout.json",
                    "manifest": {"runtime": "claude", "loadout": "deep-coding"},
                    "launch_notice": "[hermes-terminal-loadout]",
                }
            ),
        ),
    )

    payload = loadout_cli._apply_loadout(
        repo,
        "claude",
        loadout="deep-coding",
        request_text=None,
        output_root=Path("/tmp/out"),
        target_home=False,
    )
    assert payload["manifest"]["loadout"] == "deep-coding"
    assert payload["launch_notice"] == "[hermes-terminal-loadout]"


def test_launch_env_applies_manifest_env_and_codex_home(tmp_path):
    home = tmp_path / ".codex"
    manifest = {"launch": {"env": {"HOME": "/real/home", "FOO": "bar"}}}
    env = loadout_cli._launch_env("codex", home, manifest)
    assert env["HOME"] == "/real/home"
    assert env["FOO"] == "bar"
    assert env["CODEX_HOME"] == str(home)


def test_launch_dry_run_applies_loadout_and_builds_command(monkeypatch, capsys, tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "apply_loadout.py").write_text("# stub\n", encoding="utf-8")

    home = tmp_path / ".codex"
    home.mkdir()
    workdir = tmp_path / "project"
    workdir.mkdir()
    captured = {}

    monkeypatch.setenv("HERMES_LOADOUT_USER_HOME", str(tmp_path))
    monkeypatch.setattr(loadout_cli, "_find_runtime_binary", lambda _: "/usr/bin/codex")

    def fake_apply(*args, **kwargs):
        captured.update(kwargs)
        return {
            "output_root": str(home),
            "manifest_path": str(home / "hermes-loadout.json"),
            "manifest": {
                "runtime": "codex",
                "loadout": "research",
                "launch": {"env": {"HOME": "/home/dylan-malik"}},
            },
            "launch_notice": "CODEX | loadout: research | session: fresh | cwd: project",
        }

    monkeypatch.setattr(loadout_cli, "_apply_loadout", fake_apply)

    args = argparse.Namespace(
        repo=str(repo),
        runtime="codex",
        loadout="research",
        request=None,
        home=None,
        cwd=str(workdir),
        dry_run=True,
        json=True,
        arg=["exec", "--help"],
    )
    assert loadout_cli._cmd_launch(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied_loadout"] == "research"
    assert payload["command"] == ["/usr/bin/codex", "exec", "--help"]
    assert payload["cwd"] == str(workdir)
    assert payload["launch_notice"] == "CODEX | loadout: research | session: fresh | cwd: project"
    assert payload["launch"]["env"]["HOME"] == "/home/dylan-malik"
    assert captured["cwd"] == str(workdir)


def test_launch_rejects_claude_custom_home(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "apply_loadout.py").write_text("# stub\n", encoding="utf-8")

    args = argparse.Namespace(
        repo=str(repo),
        loadout_command="launch",
        runtime="claude",
        loadout="default",
        request=None,
        home=str(tmp_path / "alt-claude-home"),
        cwd=None,
        dry_run=True,
        json=True,
        arg=[],
    )
    assert loadout_cli.loadout_command(args) == 1


def test_apply_requires_loadout_or_request(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "apply_loadout.py").write_text("# stub\n", encoding="utf-8")

    try:
        loadout_cli._apply_loadout(
            repo,
            "claude",
            loadout=None,
            request_text=None,
            output_root=tmp_path / "out",
            target_home=False,
        )
    except RuntimeError as exc:
        assert "Provide either --loadout or --request" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
