"""Dedicated Grep shares Read's once-per-session strict orientation gate."""
import io
import json
import time

import pytest

from tests.test_hook_strict import _fixture, _invoke, _is_deny, _read


def _grep(path=None, sid="s1"):
    tool_input = {"pattern": "load_config"}
    if path is not None:
        tool_input["path"] = str(path)
    return {"session_id": sid, "tool_name": "Grep", "tool_input": tool_input}


def test_first_grep_denies_then_nudges(tmp_path, monkeypatch):
    _fixture(tmp_path, indexed=False)  # directory searches need no manifest match
    payload = _grep(tmp_path / "src")
    first = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert _is_deny(first)
    reason = json.loads(first)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "graphify query" in reason and "Grep" in reason and "Read" not in reason
    second = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(second) and "knowledge graph at" in second


def test_fresh_query_bypasses_grep_deny(tmp_path, monkeypatch):
    _fixture(tmp_path)
    stamp = tmp_path / "graphify-out" / "cache" / "last_query_stamp"
    stamp.parent.mkdir(parents=True)
    stamp.write_text(str(time.time()), encoding="utf-8")
    out = _invoke("search", _grep(), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "knowledge graph at" in out
    assert _invoke("search", _grep(), tmp_path, monkeypatch, strict=True) == ""


@pytest.mark.parametrize("strict,env,denied", [
    (False, {}, False),
    (True, {}, True),
    (False, {"GRAPHIFY_HOOK_STRICT": "1"}, True),
    (True, {"GRAPHIFY_HOOK_STRICT": "0"}, False),
])
def test_grep_strict_flag_and_environment(tmp_path, monkeypatch, strict, env, denied):
    _fixture(tmp_path)
    out = _invoke("search", _grep(), tmp_path, monkeypatch, strict=strict, env=env)
    assert _is_deny(out) is denied
    assert "graphify query" in out


@pytest.mark.parametrize("first_kind", ["read", "search"])
def test_read_and_grep_share_one_deny(tmp_path, monkeypatch, first_kind):
    f = _fixture(tmp_path)
    calls = [("read", _read(f)), ("search", _grep())]
    if first_kind == "search":
        calls.reverse()
    first, second = calls
    assert _is_deny(_invoke(*first, tmp_path, monkeypatch, strict=True))
    out = _invoke(*second, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "knowledge graph at" in out


@pytest.mark.parametrize("target", ["external", "../outside", "graphify-out", "graphify-out/graph.json"])
def test_grep_external_and_output_paths_bypass(tmp_path, monkeypatch, target):
    _fixture(tmp_path)
    path = tmp_path.parent / "outside" if target == "external" else target
    assert _invoke("search", _grep(path), tmp_path, monkeypatch, strict=True) == ""
    # Bypassed searches must not consume the session's deny.
    assert _is_deny(_invoke("search", _grep(), tmp_path, monkeypatch, strict=True))


@pytest.mark.parametrize("target", ["external", "../outside", "graphify-out", "graphify-out/graph.json"])
def test_soft_grep_suppresses_irrelevant_path_nudges(tmp_path, monkeypatch, target):
    _fixture(tmp_path)
    path = tmp_path.parent / "outside" if target == "external" else target
    assert _invoke("search", _grep(path), tmp_path, monkeypatch, strict=False) == ""
    assert "knowledge graph at" in _invoke("search", _grep("src"), tmp_path, monkeypatch, strict=False)


def test_grep_on_one_unindexed_file_keeps_the_deny(tmp_path, monkeypatch):
    _fixture(tmp_path)  # manifest indexes src/mod.py only
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    out = _invoke("search", _grep("pyproject.toml"), tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "knowledge graph at" in out
    # The session's one deny is still available for an indexed target.
    assert _is_deny(_invoke("search", _grep("src/mod.py"), tmp_path, monkeypatch, strict=True))


def test_grep_custom_output_bypasses(tmp_path, monkeypatch):
    from graphify import paths
    _fixture(tmp_path)
    custom = tmp_path / "artifacts" / "graphify"
    custom.mkdir(parents=True)
    (custom / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    monkeypatch.setattr(paths, "GRAPHIFY_OUT", str(custom))
    assert _invoke("search", _grep("artifacts/graphify"), tmp_path, monkeypatch, strict=True) == ""
    assert _invoke("search", _grep("graphify-out"), tmp_path, monkeypatch, strict=True) == ""
    assert _is_deny(_invoke("search", _grep("src"), tmp_path, monkeypatch, strict=True))


@pytest.mark.parametrize("state", ["no_session", "no_graph", "needs_update", "marker_error"])
def test_grep_safe_without_gate_prerequisites(tmp_path, monkeypatch, state):
    _fixture(tmp_path)
    payload = _grep()
    out_dir = tmp_path / "graphify-out"
    if state == "no_session":
        payload.pop("session_id")
    elif state == "no_graph":
        (out_dir / "graph.json").unlink()
    elif state == "needs_update":
        (out_dir / "needs_update").touch()
    else:
        (out_dir / "cache").write_text("not a directory", encoding="utf-8")
    out = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out)
    assert not (out_dir / "cache" / "hook_sessions" / "s1.denied").exists()


@pytest.mark.parametrize("payload", [
    b"{not json", [], {"tool_input": []},
    {"session_id": "s1", "tool_name": "Grep", "tool_input": {"pattern": ["foo"]}},
    {"session_id": "s1", "tool_name": "Grep", "tool_input": {"pattern": "foo", "path": ["src"]}},
])
def test_grep_bad_payload_fails_open(tmp_path, monkeypatch, payload):
    _fixture(tmp_path)
    out = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out)


def test_non_grep_tool_with_a_pattern_cannot_consume_the_deny(tmp_path, monkeypatch):
    _fixture(tmp_path)
    payload = _grep()
    payload["tool_name"] = "Bash"
    assert _invoke("search", payload, tmp_path, monkeypatch, strict=True) == ""
    assert _is_deny(_invoke("search", _grep(), tmp_path, monkeypatch, strict=True))


@pytest.mark.parametrize("command", ["grep -rn foo .", "rg foo .", "git grep foo"])
def test_bash_search_stays_advisory_without_consuming_deny(tmp_path, monkeypatch, command):
    _fixture(tmp_path)
    payload = {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": command}}
    out = _invoke("search", payload, tmp_path, monkeypatch, strict=True)
    assert not _is_deny(out) and "knowledge graph at" in out
    assert _is_deny(_invoke("search", _grep(), tmp_path, monkeypatch, strict=True))


def test_cli_search_passes_strict_flag(tmp_path, monkeypatch, capsys):
    import graphify.cli as cli
    import sys
    _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "hook-guard", "search", "--strict"])
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(_grep()).encode())))
    with pytest.raises(SystemExit) as exc:
        cli.dispatch_command("hook-guard")
    assert exc.value.code == 0 and _is_deny(capsys.readouterr().out)
