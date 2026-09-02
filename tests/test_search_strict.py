"""Strict search gate: a recursive in-project corpus search issued through Bash or the
Grep tool is denied until this session/agent has recorded one accepted graph traversal.

The read gate (test_hook_strict.py) fires once per session unconditionally. This gate is
different on purpose: the way out is a query, not a retry. Query evidence is written by
`hook-guard mark-queried` (a PostToolUse hook on the MCP graph tools and on Bash commands
that run the recorded-interpreter query/explain/path) and keyed by session_id + agent_id.
Exact-file grep, stdin grep, out-of-project targets, git grep, prose, heredocs, malformed
input, soft mode, the env kill switch and a missing session_id never deny.
"""
import io
import json
import os
import subprocess
import sys
import time

import graphify.cli as cli


def _fixture(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps({"src/mod.py": {"mtime": 1}}), encoding="utf-8")
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _invoke(kind, payload, tmp_path, monkeypatch, *, strict=True, env=None):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("GRAPHIFY_HOOK_STRICT", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    data = json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else bytes(payload)

    class _Stdin:
        buffer = io.BytesIO(data)
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard(kind, strict=strict)
    return buf.getvalue()


def _search(command, sid="s1", agent=None):
    p = {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": command}}
    if agent:
        p["agent_id"] = agent
    return p


def _grep_tool(tool_input, sid="s1"):
    return {"session_id": sid, "tool_name": "Grep", "tool_input": tool_input}


def _mark(payload, tmp_path, monkeypatch):
    return _invoke("mark-queried", payload, tmp_path, monkeypatch)


def _queried_marker(tmp_path, sid):
    return tmp_path / "graphify-out" / "cache" / "hook_sessions" / f"{sid}.queried"


def _is_deny(out):
    return out.strip() != "" and json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_denies_recursive_grep_in_project(tmp_path, monkeypatch):
    _fixture(tmp_path)
    out = _invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch)
    assert _is_deny(out)
    assert "query_graph" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_quoted_directory_target(tmp_path, monkeypatch):
    """A quoted path argument must survive tokenizing (the nudge parser drops quoted spans)."""
    _fixture(tmp_path)
    assert _is_deny(_invoke("search", _search('grep -R foo "src/"'), tmp_path, monkeypatch))


def test_denies_default_recursive_tools(tmp_path, monkeypatch):
    _fixture(tmp_path)
    for command in ("rg foo", "rg foo src", "find . -name x", "fd bar", "ack needle", "ag needle"):
        assert _is_deny(_invoke("search", _search(command), tmp_path, monkeypatch)), command


def test_denies_again_before_query(tmp_path, monkeypatch):
    """Not once-per-session: without query evidence every recursive search is denied."""
    _fixture(tmp_path)
    assert _is_deny(_invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch))
    assert _is_deny(_invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch))


def test_allows_after_mcp_query(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _mark({"session_id": "s1", "tool_name": "mcp__graphify__query_graph",
           "tool_input": {"question": "x"}, "tool_response": {}}, tmp_path, monkeypatch)
    assert _queried_marker(tmp_path, "s1").exists()
    out = _invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch)
    assert not _is_deny(out) and "MANDATORY" in out


def test_allows_after_cli_query_via_bash(tmp_path, monkeypatch):
    _fixture(tmp_path)
    commands = (
        '"C:/py/python.exe" -m graphify query "hook guard"',
        "python -m graphify explain 'Some label'",
        "graphify path A B",
    )
    for i, command in enumerate(commands):
        sid = f"cli-{i}"
        _mark({"session_id": sid, "tool_name": "Bash", "tool_input": {"command": command},
               "tool_response": {}}, tmp_path, monkeypatch)
        out = _invoke("search", _search("grep -rn foo .", sid), tmp_path, monkeypatch)
        assert not _is_deny(out), command


def test_allows_after_project_sidecar_cli_query(tmp_path, monkeypatch):
    """The exact command the project-scoped skill emits must count as evidence."""
    _fixture(tmp_path)
    for i, command in enumerate((
        '"$(cat graphify-out/.graphify_python)" -m graphify query "hook guard"',
        'graphify update . && graphify query "x"',
    )):
        sid = f"sidecar-{i}"
        _mark({"session_id": sid, "tool_name": "Bash", "tool_input": {"command": command},
               "tool_response": {}}, tmp_path, monkeypatch)
        assert _queried_marker(tmp_path, sid).exists(), command


def test_quoted_parens_do_not_fragment_the_segment(tmp_path, monkeypatch):
    _fixture(tmp_path)
    # out-of-project target must survive a regex with parens -> nudge, not deny
    out = _invoke("search", _search('rg "def (a|b)" /somewhere/else'), tmp_path, monkeypatch)
    assert not _is_deny(out) and "MANDATORY" in out
    # in-project with quoted parens is still recognised as recursive -> deny
    assert _is_deny(_invoke("search", _search('grep -rn "foo(bar)" .'), tmp_path, monkeypatch))


def test_queried_markers_are_garbage_collected(tmp_path, monkeypatch):
    """Round 1 F1: a Bash-only session never reaches the .denied GC, so the
    .queried writer must sweep too — an old marker goes, a fresh one stays."""
    _fixture(tmp_path)
    d = tmp_path / "graphify-out" / "cache" / "hook_sessions"
    d.mkdir(parents=True)
    old = d / "stale-session.queried"
    old.write_text("", encoding="utf-8")
    os.utime(old, (time.time() - 90000, time.time() - 90000))  # 25h old
    _mark({"session_id": "fresh", "tool_name": "mcp__graphify__query_graph",
           "tool_input": {}}, tmp_path, monkeypatch)
    assert not old.exists()
    assert (d / "fresh.queried").exists()
    # a stale marker no longer pre-authorizes a reused session id
    assert _is_deny(_invoke("search", _search("grep -rn foo .", "stale-session"), tmp_path, monkeypatch))


def _ps(command, sid="s1"):
    return {"session_id": sid, "tool_name": "PowerShell", "tool_input": {"command": command}}


def test_powershell_recursive_search_denies(tmp_path, monkeypatch):
    """Round 1 F2: Claude Code's PowerShell tool (tool_name "PowerShell", tool_input.command)
    is matched by PreToolUse hooks; a recursive in-project search through it must gate too."""
    _fixture(tmp_path)
    for command in (
        "Get-ChildItem -Recurse -Filter *.py | Select-String foo",
        "gci -r . | sls foo",
        "ls -Recurse src | Select-String -Pattern foo",
        'Select-String -Path "src\\*" -Pattern foo',
        "Select-String -Pattern foo -Path src -Recurse",
    ):
        assert _is_deny(_invoke("search", _ps(command), tmp_path, monkeypatch)), command


def test_powershell_bounded_and_outside_only_nudge_or_stay_silent(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    for command in (
        f"Select-String -Path {f} -Pattern foo",           # exact file
        "Select-String -Path src/mod.py -Pattern foo",      # exact file, relative
        "Get-Content src/mod.py | Select-String foo",       # stdin
        "Get-ChildItem -Recurse C:/somewhere/else | Select-String foo",  # outside project
    ):
        out = _invoke("search", _ps(command), tmp_path, monkeypatch)
        assert not _is_deny(out), command
        assert "MANDATORY" in out, command
    assert _invoke("search", _ps("Get-Process | Select-Object Id"), tmp_path, monkeypatch).strip() == ""


def test_powershell_allowed_after_query(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _mark({"session_id": "s1", "tool_name": "mcp__graphify__query_graph", "tool_input": {}},
          tmp_path, monkeypatch)
    out = _invoke("search", _ps("gci -r . | sls foo"), tmp_path, monkeypatch)
    assert not _is_deny(out) and "MANDATORY" in out


def test_search_matcher_covers_powershell():
    from graphify.install import _claude_pretooluse_hooks
    m = next(h for h in _claude_pretooluse_hooks(strict=True) if "Bash" in h["matcher"])["matcher"]
    assert m == "Bash|Grep|PowerShell"


def test_mark_queried_ignores_non_query_calls(tmp_path, monkeypatch):
    _fixture(tmp_path)
    for payload in (
        {"session_id": "n1", "tool_name": "mcp__graphify__graph_stats", "tool_input": {}},
        {"session_id": "n1", "tool_name": "Bash", "tool_input": {"command": "python -m graphify update ."}},
        {"session_id": "n1", "tool_name": "Bash", "tool_input": {"command": "echo graphify query"}},
        {"session_id": "n1", "tool_name": "Read", "tool_input": {"file_path": "x.py"}},
    ):
        _mark(payload, tmp_path, monkeypatch)
    assert not _queried_marker(tmp_path, "n1").exists()


def test_sibling_agents_have_own_query_evidence(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _mark({"session_id": "shared", "tool_name": "mcp__graphify__query_graph",
           "tool_input": {}}, tmp_path, monkeypatch)  # parent queried
    parent = _invoke("search", _search("grep -rn foo .", "shared"), tmp_path, monkeypatch)
    child = _invoke("search", _search("grep -rn foo .", "shared", agent="child-1"), tmp_path, monkeypatch)
    assert not _is_deny(parent)
    assert _is_deny(child)


def test_denies_compound_with_recursive_segment(tmp_path, monkeypatch):
    _fixture(tmp_path)
    assert _is_deny(_invoke("search", _search("ls; grep -rn foo ."), tmp_path, monkeypatch))


def test_bounded_searches_only_nudge(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    for command in (
        f"grep -n foo {f}",                 # exact file, absolute
        "grep -n foo src/mod.py",           # exact file, relative
        "cat src/mod.py | grep foo",        # stdin grep
        "git grep foo",                     # repo-scoped, stays a nudge
        "grep -rn foo /somewhere/else",     # outside project
    ):
        out = _invoke("search", _search(command), tmp_path, monkeypatch)
        assert not _is_deny(out), command
        assert "MANDATORY" in out, command


def test_prose_and_heredoc_never_deny(tmp_path, monkeypatch):
    _fixture(tmp_path)
    heredoc = "cat > notes.md <<'EOT'\nrun grep -rn foo .\nEOT\n"
    for command in ('git commit -m "grep -r everything"', heredoc):
        assert _invoke("search", _search(command), tmp_path, monkeypatch).strip() == "", command


def test_grep_tool_directory_denies_file_nudges(tmp_path, monkeypatch):
    f = _fixture(tmp_path)
    assert _is_deny(_invoke("search", _grep_tool({"pattern": "foo"}), tmp_path, monkeypatch))
    assert _is_deny(_invoke("search", _grep_tool({"pattern": "foo", "path": "src"}), tmp_path, monkeypatch))
    out = _invoke("search", _grep_tool({"pattern": "foo", "path": str(f)}), tmp_path, monkeypatch)
    assert not _is_deny(out) and "MANDATORY" in out


def test_safety_valves_never_deny(tmp_path, monkeypatch):
    _fixture(tmp_path)
    no_sid = {"tool_name": "Bash", "tool_input": {"command": "grep -rn foo ."}}
    assert not _is_deny(_invoke("search", no_sid, tmp_path, monkeypatch))
    assert _invoke("search", b"{not json", tmp_path, monkeypatch) == ""
    assert not _is_deny(_invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch,
                                env={"GRAPHIFY_HOOK_STRICT": "0"}))
    assert not _is_deny(_invoke("search", _search("grep -rn foo ."), tmp_path, monkeypatch, strict=False))


def test_deny_reason_is_constant(tmp_path, monkeypatch):
    """Nothing from the command may be echoed back into the hook payload."""
    _fixture(tmp_path)
    out = _invoke("search", _search('grep -rn "$(rm -rf /)" .'), tmp_path, monkeypatch)
    assert _is_deny(out) and "rm -rf" not in out


def test_installed_strict_search_hook_executes_and_denies(tmp_path):
    from graphify.install import _claude_pretooluse_hooks

    _fixture(tmp_path)
    (tmp_path / "graphify-out" / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("GRAPHIFY_HOOK_STRICT", None)
    for project in (False, True):
        entry = next(
            h for h in _claude_pretooluse_hooks(strict=True, project=project)
            if h["matcher"] == "Bash|Grep|PowerShell"
        )["hooks"][0]
        command = entry["commandWindows"] if os.name == "nt" else entry["command"]
        result = subprocess.run(
            command, input=json.dumps(_search("grep -rn foo .", f"inst-{int(project)}")),
            text=True, capture_output=True, shell=True, cwd=tmp_path, timeout=15, env=env,
        )
        assert result.returncode == 0, result.stderr
        assert _is_deny(result.stdout), result.stdout or result.stderr


def test_installed_posttooluse_marks_query(tmp_path):
    from graphify.install import _claude_posttooluse_hooks

    _fixture(tmp_path)
    (tmp_path / "graphify-out" / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    for project in (False, True):
        entry = _claude_posttooluse_hooks(project=project)[0]
        assert "mcp__graphify__" in entry["matcher"] and "Bash" in entry["matcher"]
        hook = entry["hooks"][0]
        command = hook["commandWindows"] if os.name == "nt" else hook["command"]
        sid = f"post-{int(project)}"
        payload = {"session_id": sid, "tool_name": "mcp__graphify__query_graph",
                   "tool_input": {"question": "x"}, "tool_response": {}}
        result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True,
                                shell=True, cwd=tmp_path, timeout=15)
        assert result.returncode == 0, result.stderr
        assert _queried_marker(tmp_path, sid).exists()


def test_install_and_uninstall_round_trip(tmp_path, monkeypatch):
    from graphify.install import _install_claude_hook, _uninstall_claude_hook

    monkeypatch.chdir(tmp_path)
    _install_claude_hook(tmp_path, strict=True)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    search = next(h for h in settings["hooks"]["PreToolUse"] if h["matcher"] == "Bash|Grep|PowerShell")
    assert "hook-guard search --strict" in search["hooks"][0]["command"]
    assert any("graphify" in str(h) for h in settings["hooks"]["PostToolUse"])
    _uninstall_claude_hook(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert not any("graphify" in str(h) for h in settings["hooks"].get("PreToolUse", []))
    assert not any("graphify" in str(h) for h in settings["hooks"].get("PostToolUse", []))
