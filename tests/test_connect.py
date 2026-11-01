"""`graphify connect`: MCP config for Cursor, Claude Code, Codex and VS Code.

Every test runs against a temporary HOME and an empty PATH, so nothing here can
read or write the real ~/.cursor, ~/.claude.json, ~/.codex or VS Code profile.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphify import connect as C

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

URL = C.HOSTED_URL


class FakeRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self.returncode, "", "boom" if self.returncode else "")


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("PATH", str(empty_bin))
    monkeypatch.setattr(C.Path, "home", classmethod(lambda cls: home))
    return home, proj


def on_path(monkeypatch, *names: str) -> None:
    """Pretend these executables are on PATH."""
    real = C.shutil.which
    monkeypatch.setattr(C.shutil, "which",
                        lambda n, *a, **k: f"/fake/bin/{n}" if n in names else real(n, *a, **k))


def run(proj: Path, *argv: str, runner=None, interactive=False) -> int:
    return C.run(list(argv), runner=runner or FakeRunner(), project_dir=proj, interactive=interactive)


# --------------------------------------------------------------------------- #
# JSON clients: Cursor, VS Code, Claude Code project scope
# --------------------------------------------------------------------------- #

def test_cursor_user_add_then_rerun_is_no_change(env):
    home, proj = env
    assert run(proj, "--client", "cursor", "--yes") == 0
    path = home / ".cursor" / "mcp.json"
    assert json.loads(path.read_text()) == {"mcpServers": {"graphify": {"url": URL}}}
    before = path.read_bytes()

    assert run(proj, "--client", "cursor", "--yes") == 0
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.bak")), "a no-change run must not back up"


def test_merge_keeps_other_servers_keys_and_crlf(env):
    home, proj = env
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {"theme": "dark", "mcpServers": {"other": {"command": "x", "args": ["y"]}}}
    path.write_bytes(json.dumps(original, indent=4).replace("\n", "\r\n").encode())

    assert run(proj, "--client", "cursor", "--yes") == 0
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    doc = json.loads(raw)
    assert doc["theme"] == "dark"
    assert doc["mcpServers"]["other"] == {"command": "x", "args": ["y"]}
    assert doc["mcpServers"]["graphify"] == {"url": URL}
    assert '\r\n    "theme"' in raw.decode(), "the file's own indent is kept"
    backups = list(path.parent.glob("mcp.json.graphify.*.bak"))
    assert len(backups) == 1 and json.loads(backups[0].read_bytes()) == original


def test_unparseable_file_is_never_written(env, capsys):
    home, proj = env
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text('{\n  // a comment\n  "mcpServers": {}\n}\n')
    before = path.read_bytes()

    assert run(proj, "--client", "cursor", "--yes") == 1
    assert path.read_bytes() == before
    err = capsys.readouterr().err
    assert "not valid JSON" in err and '"graphify"' in err and URL in err


def test_update_changes_only_the_connection_keys(env):
    home, proj = env
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"graphify": {
        "url": "https://old.example/mcp", "headers": {"X-Team": "a"}}}}))

    assert run(proj, "--client", "cursor", "--yes") == 0
    entry = json.loads(path.read_text())["mcpServers"]["graphify"]
    assert entry == {"headers": {"X-Team": "a"}, "url": URL}


def test_remove_deletes_only_our_key(env):
    home, proj = env
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"graphify": {"url": URL}, "keep": {"url": "u"}}}))

    assert run(proj, "--client", "cursor", "--remove", "--yes") == 0
    assert json.loads(path.read_text()) == {"mcpServers": {"keep": {"url": "u"}}}
    assert run(proj, "--client", "cursor", "--remove", "--yes") == 0  # idempotent


def test_backups_from_the_same_second_do_not_overwrite(env, monkeypatch):
    home, proj = env
    monkeypatch.setattr(C.time, "strftime", lambda _fmt: "20260101000000")
    path = home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"mcpServers": {"graphify": {"url": "https://old.example/mcp"}}}')
    assert run(proj, "--client", "cursor", "--yes") == 0
    assert run(proj, "--client", "cursor", "--remove", "--yes") == 0
    first = path.parent / "mcp.json.graphify.20260101000000.bak"
    second = path.parent / "mcp.json.graphify.20260101000000-1.bak"
    assert "old.example" in first.read_text(), "the original is still backed up"
    assert C.HOSTED_URL in second.read_text()


def test_vscode_and_claude_project_shapes(env):
    _, proj = env
    assert run(proj, "--client", "vscode,claude", "--scope", "project", "--yes") == 0
    assert json.loads((proj / ".vscode" / "mcp.json").read_text()) == {
        "servers": {"graphify": {"type": "http", "url": URL}}}
    assert json.loads((proj / ".mcp.json").read_text()) == {
        "mcpServers": {"graphify": {"type": "http", "url": URL}}}


def test_vscode_user_file_without_code_cli(env):
    home, proj = env
    assert run(proj, "--client", "vscode", "--yes") == 0
    files = list(home.rglob("Code/User/mcp.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["servers"]["graphify"]["url"] == URL


@pytest.mark.usefixtures("requires_symlinks")
def test_symlinked_config_is_written_through(env, tmp_path):
    home, proj = env
    target = tmp_path / "dotfiles" / "mcp.json"
    target.parent.mkdir()
    target.write_text("{}")
    (home / ".cursor").mkdir()
    link = home / ".cursor" / "mcp.json"
    link.symlink_to(target)

    assert run(proj, "--client", "cursor", "--yes") == 0
    assert link.is_symlink()
    assert json.loads(target.read_text())["mcpServers"]["graphify"]["url"] == URL


# --------------------------------------------------------------------------- #
# Codex TOML
# --------------------------------------------------------------------------- #

CODEX_CONFIG = """\
# my codex settings
model = "gpt-5"

[mcp_servers.other]
command = "npx"
args = ["-y", "other"]

[profiles.fast]
model = "mini"
"""


def test_codex_toml_add_rerun_and_remove_roundtrip(env):
    home, proj = env
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(CODEX_CONFIG)

    assert run(proj, "--client", "codex", "--yes") == 0
    text = path.read_text()
    assert text.startswith(CODEX_CONFIG), "everything before our table is untouched"
    doc = tomllib.loads(text)
    assert doc["mcp_servers"]["graphify"] == {"url": URL}
    assert doc["mcp_servers"]["other"]["args"] == ["-y", "other"]
    assert doc["profiles"]["fast"]["model"] == "mini"

    assert run(proj, "--client", "codex", "--yes") == 0
    assert path.read_text() == text

    assert run(proj, "--client", "codex", "--remove", "--yes") == 0
    assert path.read_text() == CODEX_CONFIG


def test_codex_toml_update_replaces_subtables_and_stops_at_array_tables(env):
    home, proj = env
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        '[mcp_servers.graphify]\nurl = "https://old.example/mcp"\n\n'
        '[mcp_servers.graphify.http_headers]\nX-Team = "a"\n\n'
        '[[hooks]]\nname = "h"\n'
    )
    assert run(proj, "--client", "codex", "--yes") == 0
    doc = tomllib.loads(path.read_text())
    assert doc["mcp_servers"]["graphify"] == {"url": URL}
    assert doc["hooks"] == [{"name": "h"}]


def test_codex_toml_inline_entry_is_not_edited(env, capsys):
    home, proj = env
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    original = 'mcp_servers = { graphify = { url = "https://old.example/mcp" } }\n'
    path.write_text(original)

    assert run(proj, "--client", "codex", "--yes") == 1
    assert path.read_text() == original
    assert "edit it by hand" in capsys.readouterr().err


def test_codex_invalid_toml_is_skipped(env):
    home, proj = env
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text("[mcp_servers.graphify\n")
    assert run(proj, "--client", "codex", "--yes") == 1
    assert path.read_text() == "[mcp_servers.graphify\n"


def test_codex_home_env_is_honored(env, tmp_path, monkeypatch):
    _, proj = env
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    assert run(proj, "--client", "codex", "--yes") == 0
    assert tomllib.loads((codex_home / "config.toml").read_text())["mcp_servers"]["graphify"]["url"] == URL


def test_toml_value_escapes_round_trip():
    for s in ['C:\\Users\\a b\\graph.json', 'quote " and \t tab', "ünï 😀"]:
        assert tomllib.loads(f"k = {C._toml_value(s)}")["k"] == s


# --------------------------------------------------------------------------- #
# Client CLIs
# --------------------------------------------------------------------------- #

def test_claude_user_scope_needs_the_claude_cli(env, capsys):
    home, proj = env
    (home / ".claude.json").write_text('{"numStartups": 3}')
    assert run(proj, "--client", "claude", "--yes") == 1
    assert json.loads((home / ".claude.json").read_text()) == {"numStartups": 3}
    assert "claude" in capsys.readouterr().err


def test_claude_user_scope_uses_the_cli(env, monkeypatch):
    home, proj = env
    on_path(monkeypatch, "claude")
    runner = FakeRunner()
    assert run(proj, "--client", "claude", "--yes", runner=runner) == 0
    assert runner.calls == [["claude", "mcp", "add", "--transport", "http", "--scope", "user", "graphify", URL]]

    # A different URL already there: remove, then add.
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"graphify": {"type": "http", "url": "https://x/mcp"}}}))
    runner = FakeRunner()
    assert run(proj, "--client", "claude", "--yes", runner=runner) == 0
    assert [c[:3] for c in runner.calls] == [["claude", "mcp", "remove"], ["claude", "mcp", "add"]]

    # The same URL: nothing to run.
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"graphify": {"type": "http", "url": URL}}}))
    runner = FakeRunner()
    assert run(proj, "--client", "claude", "--yes", runner=runner) == 0
    assert runner.calls == []


def test_cli_failure_is_reported(env, monkeypatch, capsys):
    _, proj = env
    on_path(monkeypatch, "codex")
    assert run(proj, "--client", "codex", "--yes", runner=FakeRunner(returncode=1)) == 1
    assert "exited 1" in capsys.readouterr().err


def test_codex_cli_add_and_file_update(env, monkeypatch):
    home, proj = env
    on_path(monkeypatch, "codex")
    runner = FakeRunner()
    assert run(proj, "--client", "codex", "--yes", runner=runner) == 0
    assert runner.calls == [["codex", "mcp", "add", "graphify", "--url", URL]]

    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[mcp_servers.graphify]\nurl = "https://old.example/mcp"\n')
    runner = FakeRunner()
    assert run(proj, "--client", "codex", "--yes", runner=runner) == 0
    assert runner.calls == [], "an update edits only our table in the file"
    assert tomllib.loads(path.read_text())["mcp_servers"]["graphify"]["url"] == URL


@pytest.mark.skipif(sys.platform == "win32", reason="`code --add-mcp` is not used on Windows")
def test_vscode_user_add_uses_code_cli(env, monkeypatch):
    _, proj = env
    on_path(monkeypatch, "code")
    runner = FakeRunner()
    assert run(proj, "--client", "vscode", "--yes", runner=runner) == 0
    assert runner.calls[0][:2] == ["code", "--add-mcp"]
    assert json.loads(runner.calls[0][2]) == {"name": "graphify", "type": "http", "url": URL}


# --------------------------------------------------------------------------- #
# Duplicates, plugin, local server
# --------------------------------------------------------------------------- #

def test_warns_when_the_other_scope_has_it(env, capsys):
    home, proj = env
    (proj / ".cursor").mkdir()
    (proj / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"graphify": {"url": URL}}}))
    assert run(proj, "--client", "cursor", "--yes") == 0
    assert "twice" in capsys.readouterr().out


def test_cursor_plugin_already_provides_the_server(env):
    home, proj = env
    plugin = home / ".cursor" / "plugins" / "local" / "graphify"
    (plugin / ".cursor-plugin").mkdir(parents=True)
    (plugin / ".cursor-plugin" / "plugin.json").write_text('{"name": "graphify"}')
    (plugin / "mcp.json").write_text(json.dumps({"mcpServers": {"graphify": {"url": URL}}}))

    assert run(proj, "--client", "cursor", "--yes") == 0
    assert not (home / ".cursor" / "mcp.json").exists()


def test_local_server_project_scope_absolute_graph(env):
    _, proj = env
    graph = proj / "graphify-out" / "graph.json"
    graph.parent.mkdir()
    graph.write_text("{}")
    assert run(proj, "--client", "cursor", "--server", "local", "--yes") == 0
    entry = json.loads((proj / ".cursor" / "mcp.json").read_text())["mcpServers"]["graphify-local"]
    assert entry["type"] == "stdio"
    assert entry["args"][-2:] == ["--graph", str(graph.resolve())]
    assert Path(entry["command"]).is_absolute()


def test_local_server_needs_a_graph_and_explicit_user_scope_path(env):
    _, proj = env
    assert run(proj, "--client", "cursor", "--server", "local", "--yes") == 2
    assert run(proj, "--client", "cursor", "--server", "local", "--scope", "user", "--yes") == 2


def test_both_servers_default_scopes(env):
    home, proj = env
    graph = proj / "graphify-out" / "graph.json"
    graph.parent.mkdir()
    graph.write_text("{}")
    assert run(proj, "--client", "cursor", "--server", "both", "--yes") == 0
    assert "graphify" in json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]
    assert "graphify-local" in json.loads((proj / ".cursor" / "mcp.json").read_text())["mcpServers"]


# --------------------------------------------------------------------------- #
# Confirmation, dry run, JSON, detection, dispatch
# --------------------------------------------------------------------------- #

def test_non_interactive_without_yes_writes_nothing(env):
    home, proj = env
    assert run(proj, "--client", "cursor", interactive=False) == 2
    assert not (home / ".cursor" / "mcp.json").exists()


def test_declining_the_prompt_writes_nothing(env, monkeypatch):
    home, proj = env
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert run(proj, "--client", "cursor", interactive=True) == 1
    assert not (home / ".cursor" / "mcp.json").exists()


def test_dry_run_prints_diff_and_writes_nothing(env, capsys):
    home, proj = env
    assert run(proj, "--client", "cursor,codex", "--dry-run") == 0
    out = capsys.readouterr().out
    assert f'"url": "{URL}"' in out and "[mcp_servers.graphify]" in out
    assert not (home / ".cursor").exists() and not (home / ".codex").exists()


def test_json_output(env, capsys):
    _, proj = env
    assert run(proj, "--client", "cursor", "--yes", "--json") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["results"][0] | {"path": None, "backup": None} == {
        "client": "cursor", "server": "graphify", "scope": "user", "path": None,
        "action": "add", "via": "file", "status": "ok", "message": "", "warnings": [],
        "backup": None}
    assert C.VERIFY_DOCS_URL in result["next_steps"][-1]
    assert any("Cursor" in s for s in result["next_steps"])


def test_next_steps_list_sign_in_per_client(env, capsys):
    _, proj = env
    assert run(proj, "--client", "cursor,vscode", "--scope", "project", "--yes") == 0
    out = capsys.readouterr().out
    assert C.SIGN_IN_STEPS["cursor"] in out and C.SIGN_IN_STEPS["vscode"] in out
    assert C.VERIFY_DOCS_URL in out


def test_no_clients_detected(env):
    _, proj = env
    assert run(proj) == 2


def test_detects_clients_from_home(env):
    home, _ = env
    (home / ".cursor").mkdir()
    (home / ".codex").mkdir()
    assert C.detect_clients() == ["cursor", "codex"]


def test_unknown_client_is_a_usage_error(env):
    _, proj = env
    assert run(proj, "--client", "emacs") == 2


def test_cli_dispatch(env, monkeypatch, capsys):
    from graphify import __main__ as M

    monkeypatch.setattr(sys, "argv", ["graphify", C.COMMAND_NAME, "--help"])
    with pytest.raises(SystemExit) as exc:
        M._run_cli()
    assert exc.value.code == 0
    assert f"graphify {C.COMMAND_NAME}" in capsys.readouterr().out
