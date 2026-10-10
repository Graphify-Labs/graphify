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
    _preserve_jsonc_plugin_add,
    _preserve_jsonc_plugin_remove,
    _project_install,
    _project_uninstall,
    _strip_json_comments,
    _uninstall_mimo_plugin,
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


def test_install_entrypoint_project_without_project_dir_uses_cwd(tmp_path, monkeypatch):
    """install(platform="mimo", project=True) with project_dir=None is project-scoped at cwd.

    Regression: install()'s Optional project_dir was passed straight to
    _mimo_install(project_dir: Path), a type error and a latent None crash.
    """
    from graphify.install import install

    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("MIMOCODE_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(project)

    install(platform="mimo", project=True)

    assert (project / ".mimocode" / "plugins" / "graphify.js").exists()
    assert (project / "AGENTS.md").exists()
    assert not (home / ".config" / "mimocode").exists()


def test_install_entrypoint_global_ignores_project_dir(tmp_path, monkeypatch):
    """Global scope never writes under project_dir, even when one is supplied."""
    from graphify.install import install

    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("MIMOCODE_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(project)

    install(platform="mimo", project=False, project_dir=project)

    assert (home / ".config" / "mimocode" / "plugins" / "graphify.js").exists()
    assert not (project / ".mimocode").exists()


def test_mimo_install_atomicity_aborts_on_surgical_failure(tmp_path, monkeypatch):
    """Install aborts without modifying config or creating artifacts if surgical JSONC edit fails."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    valid_jsonc = (
        "{\n"
        "  // Important user comment\n"
        '  "$schema": "https://mimo.xiaomi.com/mimocode/config.json"\n'
        "}\n"
    )
    jsonc_file.write_text(valid_jsonc, encoding="utf-8")
    original_bytes = jsonc_file.read_bytes()

    def _failing_add(raw: str, entry: str) -> str:
        raise ValueError("simulated surgical JSONC insertion failure")

    monkeypatch.setattr("graphify.install._preserve_jsonc_plugin_add", _failing_add)

    with pytest.raises(SystemExit) as excinfo:
        _mimo_install(project, project=True)

    assert excinfo.value.code == 1
    # Config bytes must remain untouched
    assert jsonc_file.read_bytes() == original_bytes
    # No installation artifacts created or changed
    assert not (mimo_dir / "skills" / "graphify" / "SKILL.md").exists()
    assert not (mimo_dir / "plugins" / "graphify.js").exists()
    assert not (project / "AGENTS.md").exists()


def test_mimo_uninstall_atomicity_aborts_on_failed_surgical_removal(tmp_path, monkeypatch):
    """Uninstall aborts without changing config or artifacts if surgical removal fails."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    # Pre-seed installed state
    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    jsonc_file.write_text(
        "{\n"
        "  // Keep this user comment\n"
        '  "plugin": [\n'
        '    "./plugins/graphify.js"\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    original_config_bytes = jsonc_file.read_bytes()

    skill = mimo_dir / "skills" / "graphify" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# graphify skill\n", encoding="utf-8")

    plugin = mimo_dir / "plugins" / "graphify.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// graphify plugin\n", encoding="utf-8")

    agents_md = project / "AGENTS.md"
    agents_md.write_text("## graphify\nRule text here\n", encoding="utf-8")
    original_agents_bytes = agents_md.read_bytes()

    def _failing_remove(raw: str, possible_entries: set[str] | None = None) -> str:
        raise ValueError("simulated surgical JSONC removal failure")

    monkeypatch.setattr("graphify.install._preserve_jsonc_plugin_remove", _failing_remove)

    with pytest.raises(SystemExit) as excinfo:
        _mimo_uninstall(project, project=True)

    assert excinfo.value.code == 1
    # Config bytes and installation artifacts must remain unchanged
    assert jsonc_file.read_bytes() == original_config_bytes
    assert skill.exists()
    assert plugin.exists()
    assert agents_md.read_bytes() == original_agents_bytes


def test_mimo_uninstall_atomicity_aborts_on_duplicate_registrations(tmp_path, monkeypatch):
    """Uninstall aborts without changing config or artifacts if duplicate registrations remain."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    jsonc_file.write_text(
        "{\n"
        "  // User comment\n"
        '  "plugin": [\n'
        '    "./plugins/graphify.js",\n'
        '    "./plugins/graphify.js"\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    original_config_bytes = jsonc_file.read_bytes()

    skill = mimo_dir / "skills" / "graphify" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# graphify skill\n", encoding="utf-8")

    plugin = mimo_dir / "plugins" / "graphify.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// graphify plugin\n", encoding="utf-8")

    agents_md = project / "AGENTS.md"
    agents_md.write_text("## graphify\nRule text here\n", encoding="utf-8")
    original_agents_bytes = agents_md.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        _mimo_uninstall(project, project=True)

    assert excinfo.value.code == 1
    assert jsonc_file.read_bytes() == original_config_bytes
    assert skill.exists()
    assert plugin.exists()
    assert agents_md.read_bytes() == original_agents_bytes


def test_mimo_uninstall_scalar_graphify_entry_removed(tmp_path, monkeypatch):
    """Uninstall handles a scalar Graphify entry correctly without leaving a dangling registration."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    config = mimo_dir / "mimocode.json"
    config.write_text(
        json.dumps({"plugin": "./plugins/graphify.js", "theme": "dark"}, indent=2),
        encoding="utf-8",
    )

    skill = mimo_dir / "skills" / "graphify" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# skill\n", encoding="utf-8")

    plugin = mimo_dir / "plugins" / "graphify.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// plugin\n", encoding="utf-8")

    _mimo_uninstall(project, project=True)

    assert not skill.exists()
    assert not plugin.exists()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert "plugin" not in data, "Scalar Graphify entry must be removed without leaving dangling key"
    assert data.get("theme") == "dark"


def test_mimo_uninstall_scalar_unrelated_entry_preserved(tmp_path, monkeypatch):
    """Uninstall preserves unrelated scalar plugin values."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    config = mimo_dir / "mimocode.json"
    config.write_text(
        json.dumps({"plugin": "unrelated-custom-plugin.js", "theme": "dark"}, indent=2),
        encoding="utf-8",
    )

    _mimo_uninstall(project, project=True)

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data.get("plugin") == "unrelated-custom-plugin.js", "Unrelated scalar plugin value must be preserved"
    assert data.get("theme") == "dark"


def test_mimo_install_preserve_line_comment_only_array(tmp_path, monkeypatch):
    """Install preserves comments in an array that contains only line comments."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    jsonc_file.write_text(
        "{\n"
        '  "plugin": [\n'
        "    // Line comment 1: plugins must follow contract\n"
        "    // Line comment 2: do not delete\n"
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )

    _mimo_install(project, project=True)

    content = jsonc_file.read_text(encoding="utf-8")
    assert "// Line comment 1: plugins must follow contract" in content
    assert "// Line comment 2: do not delete" in content

    data = json.loads(_strip_json_comments(content))
    assert any("plugins/graphify.js" in p for p in data.get("plugin", []))


def test_mimo_install_preserve_block_comment_only_array(tmp_path, monkeypatch):
    """Install preserves comments in an array that contains only block comments."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    jsonc_file.write_text(
        "{\n"
        '  "plugin": [\n'
        "    /* Block comment: plugins are loaded in order */\n"
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )

    _mimo_install(project, project=True)

    content = jsonc_file.read_text(encoding="utf-8")
    assert "/* Block comment: plugins are loaded in order */" in content

    data = json.loads(_strip_json_comments(content))
    assert any("plugins/graphify.js" in p for p in data.get("plugin", []))


def test_preserve_jsonc_plugin_add_empty_array_comment_variants():
    """Unit tests verifying _preserve_jsonc_plugin_add preserves line and block comments."""
    # Line comments only
    raw_line = "{\n  \"plugin\": [\n    // Line comment only\n  ]\n}"
    res_line = _preserve_jsonc_plugin_add(raw_line, "./plugins/graphify.js")
    assert "// Line comment only" in res_line
    assert json.loads(_strip_json_comments(res_line))["plugin"] == ["./plugins/graphify.js"]

    # Block comments only
    raw_block = "{\n  \"plugin\": [\n    /* Block comment only */\n  ]\n}"
    res_block = _preserve_jsonc_plugin_add(raw_block, "./plugins/graphify.js")
    assert "/* Block comment only */" in res_block
    assert json.loads(_strip_json_comments(res_block))["plugin"] == ["./plugins/graphify.js"]

    # Inline block comment
    raw_inline = "{\"plugin\": [/* inline block */]}"
    res_inline = _preserve_jsonc_plugin_add(raw_inline, "./plugins/graphify.js")
    assert "/* inline block */" in res_inline
    assert json.loads(_strip_json_comments(res_inline))["plugin"] == ["./plugins/graphify.js"]

def test_mimo_is_plugin_entry_exact_matches_only():
    """Ensure _is_mimo_plugin_entry does not use broad endswith fallback."""
    from graphify.install import _is_mimo_plugin_entry
    possible = {"./plugins/graphify.js", "C:/path/plugins/graphify.js"}
    assert _is_mimo_plugin_entry("./plugins/graphify.js", possible)
    assert _is_mimo_plugin_entry("C:/path/plugins/graphify.js", possible)
    assert not _is_mimo_plugin_entry("../plugins/graphify.js", possible)
    assert not _is_mimo_plugin_entry("https://example.com/plugins/graphify.js", possible)
    assert not _is_mimo_plugin_entry("vendor/plugins/graphify.js", possible)


def test_mimo_uninstall_preserves_third_party_urls(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    jsonc_file = mimo_dir / "mimocode.jsonc"
    jsonc_file.write_text(
        "{\n"
        '  "plugin": [\n'
        '    "./plugins/graphify.js",\n'
        '    "https://example.com/plugins/graphify.js"\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )

    from graphify.install import _mimo_uninstall
    _mimo_uninstall(project, project=True)

    content = jsonc_file.read_text(encoding="utf-8")
    assert "./plugins/graphify.js" not in content
    assert "https://example.com/plugins/graphify.js" in content


def test_mimo_uninstall_rejects_unsupported_plugin_type(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.json"
    json_file.write_text('{"plugin": 123}', encoding="utf-8")

    from graphify.install import _mimo_uninstall
    import pytest
    with pytest.raises(SystemExit) as excinfo:
        _mimo_uninstall(project, project=True)
    assert excinfo.value.code == 1
    assert "refusing to modify" in capsys.readouterr().err


def test_mimo_uninstall_ignores_nested_plugin_keys(tmp_path, monkeypatch):
    """Ensure we do not remove nested strings that happen to be inside a 'plugin' key deep in the config."""
    from graphify.install import _preserve_jsonc_plugin_remove

    raw = '''{
  "theme": "dark",
  "metadata": {
    "plugin": [
      "./plugins/graphify.js"
    ]
  },
  "plugin": [
    "./plugins/graphify.js"
  ]
}'''

    possible = {"./plugins/graphify.js"}
    result = _preserve_jsonc_plugin_remove(raw, possible)

    import json
    # Use our custom stripper if it exists, or just json.loads if no comments
    data = json.loads(result)
    assert data["metadata"]["plugin"] == ["./plugins/graphify.js"], "Nested plugin array should be ignored"
    # Wait, the root plugin array should either be empty or removed, actually the test above had it removed?
    # No, our script doesn't remove the array if it becomes empty, but we removed the element!
    assert "./plugins/graphify.js" not in data.get("plugin", []), "Root plugin should be removed"


def test_mimo_uninstall_ignores_nested_objects(tmp_path, monkeypatch):
    """Ensure depth tracking works and doesn't crash on objects inside the plugin array."""
    from graphify.install import _preserve_jsonc_plugin_remove
    raw = '''{
  "plugin": [
    {"name": "some-plugin", "path": "./plugins/graphify.js"},
    "./plugins/graphify.js"
  ]
}'''
    possible = {"./plugins/graphify.js"}
    result = _preserve_jsonc_plugin_remove(raw, possible)

    import json
    data = json.loads(result)
    assert data["plugin"][0]["path"] == "./plugins/graphify.js"
    assert "./plugins/graphify.js" not in data["plugin"][1:]

def test_mimo_uninstall_rejects_unsupported_plugin_type_jsonc(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.jsonc"
    json_file.write_text('// comment\n{"plugin": 123}', encoding="utf-8")

    from graphify.install import _mimo_uninstall
    import pytest
    with pytest.raises(SystemExit) as excinfo:
        _mimo_uninstall(project, project=True)
    assert excinfo.value.code == 1
    assert "refusing to modify" in capsys.readouterr().err

def test_mimo_uninstall_project_json_unbound_local(tmp_path, monkeypatch):
    """Test project uninstall with non-JSONC config to prevent UnboundLocalError."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)

    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.json"
    json_file.write_text('{"plugin": ["./plugins/graphify.js", "other.js"], "theme": "dark"}', encoding="utf-8")

    global_dir = home / ".mimocode"
    global_dir.mkdir(parents=True)
    global_json = global_dir / "mimocode.json"
    global_json.write_text('{"plugin": ["./plugins/graphify.js"]}', encoding="utf-8")

    from graphify.install import _mimo_uninstall
    _mimo_uninstall(project, project=True)

    import json
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["plugin"] == ["other.js"]
    assert data["theme"] == "dark"
    assert json.loads(global_json.read_text(encoding="utf-8"))["plugin"] == ["./plugins/graphify.js"]

def test_mimo_install_creates_backup(tmp_path, monkeypatch):
    """Existing user settings are preserved and a .graphify-bak backup is created."""
    home = tmp_path / "home"
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    mimo_dir = home / ".config" / "mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.json"
    json_file.write_text('{"theme": "light"}', encoding="utf-8")

    from graphify.install import _mimo_install
    _mimo_install(tmp_path, project=False)

    bak_file = mimo_dir / "mimocode.json.graphify-bak"
    assert bak_file.exists()
    assert '{"theme": "light"}' in bak_file.read_text(encoding="utf-8")

def test_mimo_install_refuses_invalid_json(tmp_path, monkeypatch, capsys):
    """Invalid JSON is refused without clobbering the original bytes."""
    home = tmp_path / "home"
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    mimo_dir = home / ".config" / "mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.json"
    original_bytes = b'{"theme": "light", }'
    json_file.write_bytes(original_bytes)

    from graphify.install import _mimo_install
    import pytest
    with pytest.raises(SystemExit) as excinfo:
        _mimo_install(tmp_path, project=False)
    assert excinfo.value.code == 1
    assert json_file.read_bytes() == original_bytes

    from graphify.install import _mimo_uninstall
    with pytest.raises(SystemExit) as excinfo2:
        _mimo_uninstall(tmp_path, project=False)
    assert excinfo2.value.code == 1
    assert json_file.read_bytes() == original_bytes

def test_mimo_cli_scope_parsing(tmp_path, monkeypatch):
    """--scope project and --scope=project parsing works."""
    import sys
    from graphify.install import dispatch_install_cli
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)

    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "install", "--scope", "project"])
    assert dispatch_install_cli("mimo")
    assert (project / ".mimocode" / "skills" / "graphify" / "SKILL.md").exists()

    monkeypatch.setattr(sys, "argv", ["graphify", "mimo", "uninstall", "--scope=project"])
    assert dispatch_install_cli("mimo")
    assert not (project / ".mimocode" / "skills" / "graphify" / "SKILL.md").exists()

def test_mimo_uninstall_windows_paths(tmp_path, monkeypatch):
    """Windows path deregistration variants are handled."""
    from graphify.install import _preserve_jsonc_plugin_remove
    # The actual path in memory has single backslashes
    actual_path = r"C:\Users\name\.mimocode\skills\graphify\plugins\graphify.js"
    # In JSON it needs to be escaped with double backslashes
    json_path = actual_path.replace("\\", "\\\\")
    raw = f'{{\n  "plugin": [\n    "{json_path}"\n  ]\n}}'
    possible = {actual_path, actual_path.replace("\\", "/")}
    res = _preserve_jsonc_plugin_remove(raw, possible)
    assert json_path not in res

def test_mimo_install_jsonc_strings_with_syntax_chars():
    """JSONC strings containing ,} and ,] remain unchanged."""
    from graphify.install import _preserve_jsonc_plugin_add
    raw = '{\n  "custom_regex": "match,}or,]here",\n  "plugin": []\n}'
    res = _preserve_jsonc_plugin_add(raw, "./plugins/graphify.js")
    assert '"custom_regex": "match,}or,]here"' in res
    assert '"./plugins/graphify.js"' in res

def test_mimo_install_invalid_jsonc_trailing_commas(tmp_path, monkeypatch):
    """Repeated trailing commas remain invalid and invalid config bytes remain unchanged."""
    home = tmp_path / "home"
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    mimo_dir = home / ".config" / "mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.jsonc"
    # This is invalid even for our JSONC stripper if it's strictly parsed
    original_bytes = b'{\n  "theme": "light",,\n  "plugin": []\n}'
    json_file.write_bytes(original_bytes)

    from graphify.install import _mimo_install
    import pytest
    with pytest.raises(SystemExit) as excinfo:
        _mimo_install(tmp_path, project=False)
    assert excinfo.value.code == 1
    assert json_file.read_bytes() == original_bytes

def test_mimo_uninstall_preserves_comments(tmp_path, monkeypatch):
    """JSONC comments are preserved through uninstall."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.chdir(project)
    mimo_dir = project / ".mimocode"
    mimo_dir.mkdir(parents=True)
    json_file = mimo_dir / "mimocode.jsonc"
    json_file.write_text(
        '{\n'
        '  // My theme\n'
        '  "theme": "light",\n'
        '  "plugin": [\n'
        '    "./plugins/graphify.js"\n'
        '  ]\n'
        '}\n',
        encoding="utf-8"
    )

    from graphify.install import _mimo_uninstall
    _mimo_uninstall(project, project=True)

    res = json_file.read_text(encoding="utf-8")
    assert "// My theme" in res
    assert "./plugins/graphify.js" not in res
