"""#3554 / #3732: an OpenCode upgrade must not leave a dead graphify plugin behind.

Until 0.9.74 `graphify opencode install` wrote a plugin with only a named
export, the OpenCode 1 shape. OpenCode 2 refuses it ("Plugin must export a
default definition ...") and also fails on the opencode.json entry written next
to it. Upgrading graphify did not touch either file, so the user had to know to
run the install again in every project. The CLI now rewrites such a plugin on
its next run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify.install import __version__, _OPENCODE_PLUGIN_JS

# The plugin exactly as 0.9.74 wrote it.
V1_PLUGIN = '''\
// graphify OpenCode plugin
// Injects a knowledge graph reminder before bash tool calls when the graph exists.
//
// IMPORTANT: keep the reminder string free of backticks and $(...) constructs.
// The hook prepends `echo "<reminder>" && <cmd>` to the user's bash command;
// backticks inside the double-quoted echo trigger bash command substitution,
// which both corrupts tool output and silently executes the very graphify
// command we are only suggesting. Plain words render fine in opencode's TUI.
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  let reminded = false;

  return {
    "tool.execute.before": async (input, output) => {
      if (reminded) return;
      if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;

      if (input.tool === "bash") {
        // ';' not '&&' — Windows PowerShell 5.1 rejects '&&' as a statement
        // separator, breaking the first bash command of the session (#1646).
        output.args.command =
          'echo "[graphify] knowledge graph at graphify-out/. For focused questions, run graphify query with your question (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context." ; ' +
          output.args.command;
        reminded = true;
      }
    },
  };
};
'''
ENTRY = ".opencode/plugins/graphify.js"


@pytest.fixture(autouse=True)
def _refresh_enabled(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_NO_AUTO_REFRESH", raising=False)


def _old_install(directory: Path, body: str = V1_PLUGIN, entry: bool = True) -> tuple[Path, Path]:
    """Lay down the plugin and the config entry as an older release left them."""
    plugin = directory / ".opencode" / "plugins" / "graphify.js"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_text(body, encoding="utf-8")
    config = directory / ".opencode" / "opencode.json"
    settings = {"model": "some/model", **({"plugin": [ENTRY]} if entry else {})}
    config.write_text(json.dumps(settings), encoding="utf-8")
    return plugin, config


def test_the_old_plugin_is_what_opencode_2_rejects():
    """Guard the fixture: the 0.9.74 file has no default export, and both
    files open with the line the refresh recognises graphify's plugin by."""
    assert "export default" not in V1_PLUGIN
    assert "export default" in _OPENCODE_PLUGIN_JS
    assert V1_PLUGIN.startswith(mainmod._OPENCODE_PLUGIN_HEADER)
    assert _OPENCODE_PLUGIN_JS.startswith(mainmod._OPENCODE_PLUGIN_HEADER)


def test_a_v1_plugin_in_the_working_directory_is_rewritten(tmp_path, monkeypatch, capsys):
    plugin, config = _old_install(tmp_path)
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == _OPENCODE_PLUGIN_JS
    assert json.loads(config.read_text(encoding="utf-8")) == {"model": "some/model"}
    out, err = capsys.readouterr()
    assert out == "", "stdout stays clean for --json and the MCP stdio server"
    assert f"graphify: refreshed {plugin.resolve()}" in err
    assert "GRAPHIFY_NO_AUTO_REFRESH=1" in err


def test_a_v1_plugin_in_the_home_directory_is_rewritten(tmp_path, monkeypatch, capsys):
    """`graphify opencode install` run from ~ puts the plugin in ~/.opencode,
    and OpenCode loads that for every project below home."""
    plugin, config = _old_install(Path.home())
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == _OPENCODE_PLUGIN_JS
    assert "plugin" not in json.loads(config.read_text(encoding="utf-8"))
    assert "graphify: refreshed" in capsys.readouterr().err


def test_a_second_run_is_silent(tmp_path, monkeypatch, capsys):
    _old_install(tmp_path)
    monkeypatch.chdir(tmp_path)
    mainmod._refresh_v1_opencode_plugins()
    capsys.readouterr()

    mainmod._refresh_v1_opencode_plugins()

    assert capsys.readouterr().err == ""


def test_running_from_home_checks_it_once(monkeypatch, capsys):
    plugin, _config = _old_install(Path.home())
    monkeypatch.chdir(Path.home())

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == _OPENCODE_PLUGIN_JS
    assert capsys.readouterr().err.count("graphify: refreshed") == 1


def test_a_stale_entry_beside_a_current_plugin_is_dropped(tmp_path, monkeypatch, capsys):
    """The entry can come back without the old plugin: a checkout that restores
    opencode.json, or an earlier run that wrote the plugin and then failed."""
    plugin, config = _old_install(tmp_path, _OPENCODE_PLUGIN_JS)
    stamp = plugin.stat().st_mtime_ns
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.stat().st_mtime_ns == stamp
    assert json.loads(config.read_text(encoding="utf-8")) == {"model": "some/model"}
    out, err = capsys.readouterr()
    assert out == ""
    assert f"graphify: removed the stale graphify entry from {config.resolve()}" in err

    mainmod._refresh_v1_opencode_plugins()
    assert capsys.readouterr().err == ""


def test_a_config_with_comments_gets_the_hint_once(tmp_path, monkeypatch, capsys):
    plugin, config = _old_install(tmp_path)
    commented = '{ // mine\n  "plugin": ["' + ENTRY + '"]\n}'
    config.write_text(commented, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == _OPENCODE_PLUGIN_JS
    assert config.read_text(encoding="utf-8") == commented
    out, err = capsys.readouterr()
    assert out == ""
    assert "graphify: refreshed" in err
    assert f'remove "{ENTRY}" from its plugin list by hand' in err

    mainmod._refresh_v1_opencode_plugins()
    assert capsys.readouterr().err == "", "no reminder on every later run"


def test_a_current_plugin_is_untouched_and_silent(tmp_path, monkeypatch, capsys):
    plugin, config = _old_install(tmp_path, _OPENCODE_PLUGIN_JS, entry=False)
    before = config.read_text(encoding="utf-8")
    stamp = plugin.stat().st_mtime_ns
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.stat().st_mtime_ns == stamp
    assert config.read_text(encoding="utf-8") == before
    assert capsys.readouterr().err == ""


def test_a_plugin_graphify_did_not_write_is_left_alone(tmp_path, monkeypatch, capsys):
    mine = "// my own plugin\nexport const Mine = async () => ({});\n"
    plugin, config = _old_install(tmp_path, mine)
    before = config.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == mine
    assert config.read_text(encoding="utf-8") == before
    assert capsys.readouterr().err == ""


def test_no_plugin_means_nothing_is_created(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    mainmod._refresh_v1_opencode_plugins()

    assert not (tmp_path / ".opencode").exists()
    assert not (Path.home() / ".opencode").exists()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_the_env_opt_out_disables_it(tmp_path, monkeypatch, capsys, value):
    plugin, _config = _old_install(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", value)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == V1_PLUGIN
    assert capsys.readouterr().err == ""


def test_a_failed_rewrite_never_breaks_the_command(tmp_path, monkeypatch, capsys):
    plugin, _config = _old_install(tmp_path)
    monkeypatch.chdir(tmp_path)

    def boom(_directory):
        raise PermissionError("read-only checkout")

    monkeypatch.setattr(mainmod, "_install_opencode_plugin", boom)

    mainmod._refresh_v1_opencode_plugins()

    assert plugin.read_text(encoding="utf-8") == V1_PLUGIN
    err = capsys.readouterr().err
    assert f"graphify: could not refresh {plugin.resolve()}: read-only checkout" in err
    assert "graphify: refreshed" not in err


def test_the_first_cli_run_after_an_upgrade_rewrites_it(tmp_path, monkeypatch, capsys):
    plugin, _config = _old_install(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "--version"])

    mainmod._run_cli()

    out, err = capsys.readouterr()
    assert out.strip() == f"graphify {__version__}"
    assert plugin.read_text(encoding="utf-8") == _OPENCODE_PLUGIN_JS
    assert "graphify: refreshed" in err


@pytest.mark.parametrize("cmd", ["install", "uninstall", "hook-check", "hook-guard"])
def test_install_and_hook_commands_skip_it(monkeypatch, cmd):
    calls = []
    monkeypatch.setattr(mainmod, "_refresh_v1_opencode_plugins", lambda: calls.append(cmd))
    monkeypatch.setattr(mainmod, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["graphify", cmd, "--help"])

    class _Stop(Exception):
        pass

    def stop(*_a, **_k):
        raise _Stop

    monkeypatch.setattr(mainmod, "dispatch_install_cli", stop)
    monkeypatch.setattr(mainmod, "dispatch_command", stop)
    try:
        mainmod._run_cli()
    except (_Stop, SystemExit):
        pass
    assert calls == []
