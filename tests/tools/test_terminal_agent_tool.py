import json

from tools.terminal_agent_tool import _build_runtime_command, _infer_runtime, _run_terminal_agent


class DummyCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_infer_runtime_from_task_text():
    assert _infer_runtime("Use Claude Code to refactor auth") == "claude"
    assert _infer_runtime("Please use codex on this repo") == "codex"


def test_infer_runtime_rejects_missing_runtime_text():
    try:
        _infer_runtime("Refactor auth")
    except ValueError as exc:
        assert "Could not infer runtime" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_infer_runtime_rejects_multi_runtime_text():
    try:
        _infer_runtime("Compare Claude Code and Codex on this task")
    except ValueError as exc:
        assert "multiple runtimes" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_runtime_command_shapes():
    assert _build_runtime_command("claude", "Say hi", 5) == [
        "claude",
        "-p",
        "Say hi",
        "--output-format",
        "json",
        "--max-turns",
        "5",
    ]
    assert _build_runtime_command("codex", "Say hi", 5) == ["codex", "exec", "--full-auto", "Say hi"]


def test_dry_run_returns_launch_plan(monkeypatch, tmp_path):
    runtime_home = tmp_path / ".claude"
    runtime_home.mkdir()

    monkeypatch.setattr("tools.terminal_agent_tool.shutil.which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("tools.terminal_agent_tool._repo_root", lambda _args: tmp_path)
    monkeypatch.setattr("tools.terminal_agent_tool._runtime_home", lambda runtime, home=None: runtime_home)
    monkeypatch.setattr("tools.terminal_agent_tool._validate_home_override", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "tools.terminal_agent_tool._apply_loadout",
        lambda *args, **kwargs: {
            "manifest_path": str(runtime_home / "hermes-loadout.json"),
            "manifest": {"loadout": "research", "runtime": "claude"},
            "launch_notice": "CLAUDE CODE | loadout: research | session: fresh | cwd: tmp_path",
        },
    )

    payload = json.loads(
        _run_terminal_agent(task="Use Claude Code to analyze this", dry_run=True)
    )
    assert payload["success"] is True
    assert payload["runtime"] == "claude"
    assert payload["applied_loadout"] == "research"
    assert payload["dry_run"] is True
    assert payload["launch_notice"] == "CLAUDE CODE | loadout: research | session: fresh | cwd: tmp_path"
    assert payload["command"][0] == "claude"


def test_live_run_executes_codex_and_sets_codex_home(monkeypatch, tmp_path):
    runtime_home = tmp_path / ".codex"
    runtime_home.mkdir()
    recorded = {}

    monkeypatch.setattr("tools.terminal_agent_tool.shutil.which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr("tools.terminal_agent_tool._repo_root", lambda _args: tmp_path)
    monkeypatch.setattr("tools.terminal_agent_tool._runtime_home", lambda runtime, home=None: runtime_home)
    monkeypatch.setattr("tools.terminal_agent_tool._validate_home_override", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "tools.terminal_agent_tool._apply_loadout",
        lambda *args, **kwargs: {
            "manifest_path": str(runtime_home / "hermes-loadout.json"),
            "manifest": {"loadout": "builder", "runtime": "codex"},
            "launch_notice": "CODEX | loadout: builder | session: fresh | cwd: testdir",
        },
    )

    def fake_run(command, cwd, env, capture_output, text, check):
        recorded["command"] = command
        recorded["cwd"] = cwd
        recorded["env"] = env
        recorded["capture_output"] = capture_output
        recorded["text"] = text
        recorded["check"] = check
        return DummyCompleted(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr("tools.terminal_agent_tool.subprocess.run", fake_run)

    payload = json.loads(
        _run_terminal_agent(
            task="Use Codex to update tests",
            cwd=str(tmp_path),
            dry_run=False,
        )
    )
    assert payload["success"] is True
    assert payload["runtime"] == "codex"
    assert payload["exit_code"] == 0
    assert payload["stdout"] == "done"
    assert recorded["command"] == ["codex", "exec", "--full-auto", "Use Codex to update tests"]
    assert recorded["cwd"] == str(tmp_path)
    assert recorded["env"]["CODEX_HOME"] == str(runtime_home)
