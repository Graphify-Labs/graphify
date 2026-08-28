"""AdaL skill and lifecycle-hook integration tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

import graphify.install as installmod
from graphify.__main__ import main


def _settings(home: Path) -> Path:
    return home / ".adal" / "settings.json"


def _graphify_groups(settings: dict) -> list[dict]:
    return [
        group
        for group in settings["hooks"]["PreToolUse"]
        if installmod._is_adal_graphify_hook(group)
    ]


def test_adal_hook_install_is_safe_and_idempotent(tmp_path):
    home = tmp_path / "home"
    settings_path = _settings(home)
    settings_path.parent.mkdir(parents=True)
    lookalike = {
        "matcher": "bash",
        "hooks": [
            {"type": "command", "command": "echo graphify hook-guard search"}
        ],
    }
    post_group = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "post-audit"}],
    }
    settings_path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "hooks": {
                    "PreToolUse": [lookalike],
                    "PostToolUse": [post_group],
                },
            }
        ),
        encoding="utf-8",
    )
    settings_path.chmod(0o640)

    with (
        patch("graphify.install.Path.home", return_value=home),
        patch(
            "graphify.install._resolve_graphify_exe",
            return_value="/opt/Graphify Tools/graphify",
        ),
    ):
        installmod._install_adal_hook(strict=True)
        installmod._install_adal_hook(strict=True)

    installed = json.loads(settings_path.read_text(encoding="utf-8"))
    assert installed["theme"] == "dark"
    assert settings_path.stat().st_mode & 0o777 == 0o640
    assert installed["hooks"]["PostToolUse"] == [post_group]
    assert lookalike in installed["hooks"]["PreToolUse"]
    groups = _graphify_groups(installed)
    assert {group["matcher"] for group in groups} == {
        "bash|grep",
        "read_file|glob",
    }
    assert len(groups) == 2
    commands = [group["hooks"][0]["command"] for group in groups]
    assert any(command.endswith("hook-guard search") for command in commands)
    assert any(command.endswith("hook-guard read --strict") for command in commands)


def test_adal_hook_uninstall_removes_only_owned_groups(tmp_path):
    home = tmp_path / "home"
    settings_path = _settings(home)
    settings_path.parent.mkdir(parents=True)
    lookalike = {
        "matcher": "bash|grep",
        "hooks": [
            {"type": "command", "command": "echo graphify hook-guard search"}
        ],
    }
    owned = [
        {
            "matcher": "bash|grep",
            "hooks": [
                {
                    "type": "command",
                    "command": "/usr/local/bin/graphify hook-guard search",
                }
            ],
        },
        {
            "matcher": "read_file|glob",
            "hooks": [
                {
                    "type": "command",
                    "command": "/usr/local/bin/graphify hook-guard read --strict",
                }
            ],
        },
    ]
    original = {
        "model": "example",
        "hooks": {
            "PreToolUse": [lookalike, *owned],
            "Stop": [{"hooks": [{"type": "command", "command": "keep-stop"}]}],
        },
    }
    settings_path.write_text(json.dumps(original), encoding="utf-8")

    with patch("graphify.install.Path.home", return_value=home):
        installmod._uninstall_adal_hook()

    remaining = json.loads(settings_path.read_text(encoding="utf-8"))
    assert remaining["model"] == "example"
    assert remaining["hooks"]["Stop"] == original["hooks"]["Stop"]
    assert remaining["hooks"]["PreToolUse"] == [lookalike]


def test_adal_hook_install_refuses_malformed_settings(tmp_path):
    home = tmp_path / "home"
    settings_path = _settings(home)
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{broken", encoding="utf-8")

    with patch("graphify.install.Path.home", return_value=home):
        with pytest.raises(SystemExit):
            installmod._install_adal_hook()

    assert settings_path.read_text(encoding="utf-8") == "{broken"
    assert not settings_path.with_suffix(".json.tmp").exists()


def test_install_platform_adal_writes_thin_skill_and_hooks(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "--platform", "adal"])
    monkeypatch.setattr(
        installmod,
        "_resolve_graphify_exe",
        lambda: "/usr/local/bin/graphify",
    )

    with patch("graphify.install.Path.home", return_value=home):
        main()

    skill_dir = home / ".adal" / "skills" / "graphify"
    skill = skill_dir / "SKILL.md"
    assert skill.exists()
    assert not (skill_dir / "references").exists()
    content = skill.read_text(encoding="utf-8")
    assert "graphify query" in content
    assert all(
        unsupported not in content
        for unsupported in ("Task(", "Agent(", "spawn_agent", "agentic_search")
    )
    assert len(_graphify_groups(json.loads(_settings(home).read_text()))) == 2
    assert not (project / "AGENTS.md").exists()


def test_adal_user_subcommand_roundtrip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    agents_path = project / "AGENTS.md"
    agents_path.write_text("# Team rules\n\nKeep this.\n", encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        installmod,
        "_resolve_graphify_exe",
        lambda: "/usr/local/bin/graphify",
    )

    with patch("graphify.install.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "adal", "install"])
        main()
        assert (home / ".adal" / "skills" / "graphify" / "SKILL.md").exists()
        assert "## graphify" in agents_path.read_text(encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["graphify", "adal", "uninstall"])
        main()

    assert not (home / ".adal" / "skills" / "graphify").exists()
    assert agents_path.read_text(encoding="utf-8") == "# Team rules\n\nKeep this.\n"
    assert json.loads(_settings(home).read_text(encoding="utf-8")) == {}


def test_adal_project_roundtrip_stays_project_scoped(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    with patch("graphify.install.Path.home", return_value=home):
        monkeypatch.setattr(
            sys, "argv", ["graphify", "adal", "install", "--project"]
        )
        main()

    skill_dir = project / ".adal" / "skills" / "graphify"
    assert (skill_dir / "SKILL.md").exists()
    assert not (skill_dir / "references").exists()
    assert "## graphify" in (project / "AGENTS.md").read_text(encoding="utf-8")
    assert not (home / ".adal").exists()

    with patch("graphify.install.Path.home", return_value=home):
        monkeypatch.setattr(
            sys, "argv", ["graphify", "adal", "uninstall", "--project"]
        )
        main()

    assert not skill_dir.exists()
    assert not (project / "AGENTS.md").exists()


def test_adal_project_strict_requires_user_scope(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "adal", "install", "--project", "--strict"],
    )

    with pytest.raises(SystemExit):
        main()

    assert not (project / ".adal").exists()
    assert not (project / "AGENTS.md").exists()


def test_adal_hook_payload_nudges_on_search(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    payload = {
        "session_id": "adal-session",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "bash",
        "tool_input": {"command": "rg lifecycle_hooks src"},
    }
    env = dict(os.environ)
    env.pop("GRAPHIFY_OUT", None)
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (repo_root, env.get("PYTHONPATH", "")) if part
    )
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "search"],
        input=json.dumps(payload),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "graphify query" in output["hookSpecificOutput"]["additionalContext"]
