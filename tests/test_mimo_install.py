"""Tests for Xiaomi MiMo Code (mimo) installer, uninstaller, CLI dispatch, and plugin."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

import graphify.__main__ as m
from graphify.install import (
    _MIMO_PLUGIN_JS,
    _mimo_install,
    _mimo_status,
    _mimo_uninstall,
    _project_install,
    _project_uninstall,
    dispatch_install_cli,
)


def test_mimo_global_install(tmp_path, monkeypatch):
    """Global install writes skill to ~/.config/mimocode/skills, plugin, config, and AGENTS.md."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    _mimo_install(project, project=False)

    skill = home / ".config" / "mimocode" / "skills" / "graphify" / "SKILL.md"
    ver_stamp = home / ".config" / "mimocode" / "skills" / "graphify" / ".graphify_version"
    plugin = home / ".config" / "mimocode" / "plugins" / "graphify.js"
    config = home / ".config" / "mimocode" / "mimocode.json"
    global_agents = home / ".config" / "mimocode" / "AGENTS.md"

    assert skill.exists(), "Global skill must be installed under ~/.config/mimocode/skills/"
    assert ver_stamp.exists(), ".graphify_version stamp must be written"
    assert plugin.exists(), "Plugin must be installed under ~/.config/mimocode/plugins/"
    assert config.exists(), "mimocode.json must exist"
    assert global_agents.exists(), "AGENTS.md must exist in global config directory"

    cfg_data = json.loads(config.read_text(encoding="utf-8"))
    plugins = cfg_data.get("plugin", [])
    assert any("plugins/graphify.js" in p for p in plugins)
    assert "## graphify" in global_agents.read_text(encoding="utf-8")


def test_mimo_project_install(tmp_path, monkeypatch):
    """Project-scoped install writes everything to project root and .mimocode/."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    _mimo_install(project, project=True)

    skill = project / ".mimocode" / "skills" / "graphify" / "SKILL.md"
    plugin = project / ".mimocode" / "plugins" / "graphify.js"
    config = project / ".mimocode" / "mimocode.json"
    agents_md = project / "AGENTS.md"

    assert skill.exists(), "Project skill must be under .mimocode/skills/"
    assert plugin.exists(), "Project plugin must be under .mimocode/plugins/"
    assert config.exists(), "Project mimocode.json must exist"
    assert agents_md.exists(), "Project AGENTS.md must exist"

    cfg_data = json.loads(config.read_text(encoding="utf-8"))
    assert any("plugins/graphify.js" in p for p in cfg_data.get("plugin", []))

    # Global directory must NOT have been touched
    assert not (home / ".config" / "mimocode").exists()


def test_mimo_install_idempotency(tmp_path, monkeypatch):
    """Installing twice causes no duplicates in mimocode.json or AGENTS.md."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    _mimo_install(project, project=True)
    _mimo_install(project, project=True)

    config = project / ".mimocode" / "mimocode.json"
    cfg_data = json.loads(config.read_text(encoding="utf-8"))
    plugins = cfg_data.get("plugin", [])
    matching = [p for p in plugins if "plugins/graphify.js" in p]
    assert len(matching) == 1

    agents_md = project / "AGENTS.md"
    content = agents_md.read_text(encoding="utf-8")
    assert content.count("## graphify") == 1


def test_mimo_project_uninstall_preserves_unrelated_content(tmp_path, monkeypatch):
    """Project uninstall clears graphify artifacts while preserving user config."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    # Pre-populate user configuration and AGENTS.md content
    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    config = mimo_dir / "mimocode.json"
    config.write_text(
        json.dumps({"plugin": ["my-custom-plugin.js"], "customKey": "keepMe"}, indent=2),
        encoding="utf-8",
    )
    agents_md = project / "AGENTS.md"
    agents_md.write_text("# Project Guidelines\n\nUser instructions here.\n", encoding="utf-8")

    # Install
    _mimo_install(project, project=True)
    # Uninstall
    _mimo_uninstall(project, project=True)

    assert not (project / ".mimocode" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (project / ".mimocode" / "plugins" / "graphify.js").exists()

    # User content preserved
    cfg_data = json.loads(config.read_text(encoding="utf-8"))
    assert cfg_data.get("customKey") == "keepMe"
    assert "my-custom-plugin.js" in cfg_data.get("plugin", [])
    assert ".mimocode/plugins/graphify.js" not in cfg_data.get("plugin", [])

    agents_text = agents_md.read_text(encoding="utf-8")
    assert "User instructions here." in agents_text
    assert "## graphify" not in agents_text


def test_mimo_global_uninstall(tmp_path, monkeypatch):
    """Global uninstall removes global skill, plugin, config entry, and AGENTS.md section."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    _mimo_install(project, project=False)
    _mimo_uninstall(project, project=False)

    skill = home / ".config" / "mimocode" / "skills" / "graphify" / "SKILL.md"
    plugin = home / ".config" / "mimocode" / "plugins" / "graphify.js"
    assert not skill.exists()
    assert not plugin.exists()

    config = home / ".config" / "mimocode" / "mimocode.json"
    if config.exists():
        cfg_data = json.loads(config.read_text(encoding="utf-8"))
        assert plugin.as_posix() not in cfg_data.get("plugin", [])

    global_agents = home / ".config" / "mimocode" / "AGENTS.md"
    if global_agents.exists():
        assert "## graphify" not in global_agents.read_text(encoding="utf-8")


def test_mimo_cli_dispatch(tmp_path, monkeypatch):
    """Test graphify mimo install, uninstall, and status via dispatch_install_cli."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    # 1. install
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "install"])
    assert dispatch_install_cli("mimo")
    assert (home / ".config" / "mimocode" / "skills" / "graphify" / "SKILL.md").exists()

    # 2. status
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "status"])
    assert dispatch_install_cli("mimo")

    # 3. uninstall
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "uninstall"])
    assert dispatch_install_cli("mimo")
    assert not (home / ".config" / "mimocode" / "skills" / "graphify" / "SKILL.md").exists()


def test_mimo_cli_dispatch_project(tmp_path, monkeypatch):
    """Test graphify mimo install --project and uninstall --project."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    # 1. install --project
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "install", "--project"])
    assert dispatch_install_cli("mimo")
    assert (project / ".mimocode" / "skills" / "graphify" / "SKILL.md").exists()

    # 2. status --project
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "status", "--project"])
    assert dispatch_install_cli("mimo")

    # 3. uninstall --project
    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "uninstall", "--project"])
    assert dispatch_install_cli("mimo")
    assert not (project / ".mimocode" / "skills" / "graphify" / "SKILL.md").exists()


def test_mimo_status_output(tmp_path, monkeypatch, capsys):
    """Test output of _mimo_status with active graph."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    # Create dummy graph.json
    out_dir = project / "graphify-out"
    out_dir.mkdir(parents=True)
    (out_dir / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "n1"}], "edges": []}), encoding="utf-8"
    )

    _mimo_install(project, project=True)
    capsys.readouterr()  # clear buffer

    _mimo_status(project, project=True)
    out = capsys.readouterr().out
    assert "Xiaomi MiMo Code Integration Status (Project-scoped)" in out
    assert "Skill:        Installed" in out
    assert "Plugin:       Installed" in out
    assert "Config:       Registered in" in out
    assert "Instructions: Configured in" in out
    assert "Active graph with 1 nodes" in out


def test_mimo_plugin_js_spec():
    """Verify MiMo Code plugin JS contains verified hooks, safe execution, and limits."""
    # Lifecycle hooks
    assert '"chat.message": async (input, output)' in _MIMO_PLUGIN_JS
    assert '"tool.execute.before": async (input, output)' in _MIMO_PLUGIN_JS

    # Bounded query & safe execution
    assert "spawn(bin, args" in _MIMO_PLUGIN_JS
    assert "shell: false" in _MIMO_PLUGIN_JS
    assert "4000" in _MIMO_PLUGIN_JS  # safe timeout, under MiMo 5000ms hook timeout race
    assert "8000" in _MIMO_PLUGIN_JS  # max char limit
    assert "budget" in _MIMO_PLUGIN_JS

    # Untrusted data marker
    assert "Untrusted Project Data" in _MIMO_PLUGIN_JS

    # Deduplication
    assert "seenMessageIds" in _MIMO_PLUGIN_JS
    assert "lastQueriedPrompt" in _MIMO_PLUGIN_JS
    assert "await runGraphifyQuery" in _MIMO_PLUGIN_JS


def test_mimo_env_overrides(tmp_path, monkeypatch):
    """Test MIMOCODE_HOME and XDG_CONFIG_HOME environment variable overrides."""
    # 1. MIMOCODE_HOME override: base dirs resolve to <MIMOCODE_HOME>/config
    mimo_home = tmp_path / "custom_mimo_home"
    monkeypatch.setenv("MIMOCODE_HOME", str(mimo_home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    project = tmp_path / "project"
    project.mkdir()

    _mimo_install(project, project=False)
    assert (mimo_home / "config" / "skills" / "graphify" / "SKILL.md").exists()
    assert (mimo_home / "config" / "plugins" / "graphify.js").exists()
    assert (mimo_home / "config" / "mimocode.json").exists()
    assert (mimo_home / "config" / "AGENTS.md").exists()

    _mimo_uninstall(project, project=False)
    assert not (mimo_home / "config" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (mimo_home / "config" / "plugins" / "graphify.js").exists()

    # 2. XDG_CONFIG_HOME override: resolves to <XDG_CONFIG_HOME>/mimocode
    monkeypatch.delenv("MIMOCODE_HOME", raising=False)
    xdg_config = tmp_path / "custom_xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    # Pre-create mimocode.jsonc to verify .jsonc handling
    mimo_cfg_dir = xdg_config / "mimocode"
    mimo_cfg_dir.mkdir(parents=True)
    jsonc_file = mimo_cfg_dir / "mimocode.jsonc"
    jsonc_file.write_text('{\n  "$schema": "https://mimo.xiaomi.com/mimocode/config.json"\n}\n', encoding="utf-8")

    _mimo_install(project, project=False)
    assert (xdg_config / "mimocode" / "skills" / "graphify" / "SKILL.md").exists()
    assert (xdg_config / "mimocode" / "plugins" / "graphify.js").exists()
    assert jsonc_file.exists()
    data = json.loads(jsonc_file.read_text(encoding="utf-8"))
    assert any("plugins/graphify.js" in p for p in data.get("plugin", []))

    _mimo_uninstall(project, project=False)
    assert not (xdg_config / "mimocode" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (xdg_config / "mimocode" / "plugins" / "graphify.js").exists()
    data_after = json.loads(jsonc_file.read_text(encoding="utf-8"))
    assert not data_after.get("plugin")
