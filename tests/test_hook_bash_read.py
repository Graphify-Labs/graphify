"""Reading code with cat/sed/head/tail/... in Bash gets the Read nudge.

The Read|Glob matcher gives the read nudge, but Bash goes to `hook-guard
search`, which only reacted to search commands (_bash_invokes_search, #3121).
`cat src/app.py`, `head -50 src/app.py` or `nl src/app.py` read indexed code
with no nudge at all, and `sed -n 1,80p src/app.py` got the generic search
nudge without the file's symbols. Now a Bash command that prints an in-project
code file gets the same Read nudge (with the file hint) through the same
per-agent budget, and is never denied, strict mode included.

Driven the way Claude Code drives it: `graphify hook-guard search` in a
subprocess with the PreToolUse JSON on stdin.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

SID = "3e1f0c2a-7b6d-4e5f-9a8b-1c2d3e4f5a6b"
GRAPH = {
    "nodes": [
        {"id": "app", "label": "app.py", "source_file": "src/app.py", "source_location": "L1"},
        {"id": "app_run", "label": "run()", "source_file": "src/app.py", "source_location": "L3"},
    ],
    "links": [],
}


def _project(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "app.py").write_text("import os\n\ndef run():\n    return os.getcwd()\n", encoding="utf-8")
    (proj / "README.md").write_text("# demo\n", encoding="utf-8")
    (proj / "package.json").write_text("{}\n", encoding="utf-8")
    (proj / "logo.png").write_bytes(b"\x89PNG")
    out = proj / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (out / "graph.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "other.py").write_text("x = 1\n", encoding="utf-8")
    return proj


def _env(proj, **extra):
    e = dict(os.environ)
    for k in ("GRAPHIFY_OUT", "GRAPHIFY_HOOK_STRICT", "GRAPHIFY_HOOK_NUDGE_CAP", "GRAPHIFY_HOOK_STRICT_TTL"):
        e.pop(k, None)
    e["CLAUDE_PROJECT_DIR"] = str(proj)
    e.update(extra)
    return e


def _bash(command, proj, *, sid=SID, agent=None, strict=False, tool_name="Bash", env=None):
    payload = {
        "session_id": sid,
        "transcript_path": f"/home/u/.claude/projects/p/{sid}.jsonl",
        "cwd": str(proj),
        "permission_mode": "auto",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"command": command, "description": "Read the file"},
        "tool_use_id": "toolu_01",
    }
    if tool_name is None:
        del payload["tool_name"]
    if agent:
        payload["agent_id"] = agent
    args = [sys.executable, "-m", "graphify", "hook-guard", "search"] + (["--strict"] if strict else [])
    r = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True,
                       cwd=proj, env=env or _env(proj))
    assert r.returncode == 0, r.stderr
    return r.stdout


def _read_tool(path, proj, *, sid=SID):
    payload = {"session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Read",
               "cwd": str(proj), "tool_input": {"file_path": str(path)}}
    r = subprocess.run([sys.executable, "-m", "graphify", "hook-guard", "read"], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=proj, env=_env(proj))
    return r.stdout


def _is_read_nudge(out):
    hso = json.loads(out)["hookSpecificOutput"]
    ctx = hso.get("additionalContext", "")
    return (hso["hookEventName"] == "PreToolUse" and "permissionDecision" not in hso
            and "reading source files one by one" in ctx)


def _nudges(proj):
    d = proj / "graphify-out" / "cache" / "hook_sessions"
    return {p.name: p.read_text() for p in d.glob("*.nudges")} if d.is_dir() else {}


READERS = [
    "cat src/app.py",
    "cat -n src/app.py",
    "sed -n 1,80p src/app.py",
    "sed -n '/def run/,/^$/p' src/app.py",
    "head -50 src/app.py",
    "head -n 20 src/app.py",
    "tail src/app.py",
    "tail -n +3 src/app.py",
    "nl -ba src/app.py",
    "less src/app.py",
    "more src/app.py",
    "bat --paging=never src/app.py",
    "cat < src/app.py",
    "cat src/app.py | grep run",
    "sudo cat ./src/app.py",
    "git status && cat src/app.py",
    "cat src/app.py 2>/dev/null",
    "head -50 src/app.py 2>&1",
    "cat {proj}/src/app.py",
]


@pytest.mark.parametrize("command", READERS)
def test_bash_reader_gets_the_read_nudge_with_the_file_hint(command, tmp_path):
    proj = _project(tmp_path)
    out = _bash(command.format(proj=proj), proj)
    assert out.count("\n") == 1, "exactly one nudge"
    assert _is_read_nudge(out), out
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert 'Start with: `graphify explain "app.py"`' in ctx
    assert "- run() (src/app.py L3)" in ctx
    assert _nudges(proj) == {f"{SID}.nudges": "1"}


SILENT = [
    "cat README.md",               # docs: orientation, not a code walk
    "cat package.json",            # not a graphed extension
    "cat logo.png",
    "cat src/missing.py",          # no such file
    "cat > src/new.py",            # writes
    "cat >> src/app.py",
    "cat src/app.py > /tmp/copy.py",
    "cat <<'EOF' > src/new.py\nimport os\nEOF",
    "sed -i 's/a/b/' src/app.py",  # edits in place
    "sed -ni 's/a/b/p' src/app.py",
    "echo x | cat",                # stdin, no file
    "git diff | head -50",
    "cat -",
    'echo "cat src/app.py"',       # prose, not an executed reader
    "# cat src/app.py",
    "cat ../elsewhere/other.py",   # outside the project (#1840)
    "cat {tmp}/elsewhere/other.py",
    "cat graphify-out/GRAPH_REPORT.md",  # graph output (#4961)
    "head graphify-out/graph.json",
    "cat $HOME/src/app.py",        # shell expansion: target unknown
    "cat src/*.py",
    "python src/app.py",           # runs code, does not print it
]


@pytest.mark.parametrize("command", SILENT)
def test_non_reads_stay_silent(command, tmp_path):
    proj = _project(tmp_path)
    assert _bash(command.format(tmp=tmp_path), proj) == ""
    assert _nudges(proj) == {}, "a silent call spends no budget"
    # Control in the same project and session: a real read nudges.
    assert _is_read_nudge(_bash("cat src/app.py", proj))


def test_bash_reads_share_the_read_budget(tmp_path):
    proj = _project(tmp_path)
    outs = [_bash("cat src/app.py", proj), _read_tool(proj / "src" / "app.py", proj),
            _bash("head -50 src/app.py", proj), _bash("sed -n 1,9p src/app.py", proj),
            _read_tool(proj / "src" / "app.py", proj)]
    assert all(outs) and _is_read_nudge(outs[0])
    assert _bash("tail src/app.py", proj) == "", "cap of 5 shared with the Read tool"
    sub = _bash("cat src/app.py", proj, agent="agent-7")
    assert _is_read_nudge(sub), "a subagent has its own budget (#3435)"


@pytest.mark.parametrize("tool_name", ["Bash", None])
def test_strict_mode_never_blocks_a_bash_read(tool_name, tmp_path):
    proj = _project(tmp_path)
    (proj / "graphify-out" / "manifest.json").write_text(json.dumps({"src/app.py": {"mtime": 1}}),
                                                         encoding="utf-8")
    os.utime(proj / "src" / "app.py", (1, 1))  # older than the graph: fresh, indexed
    for env in (None, _env(proj, GRAPHIFY_HOOK_STRICT="1")):
        out = _bash("cat src/app.py", proj, sid=f"strict-{env is None}", strict=True,
                    tool_name=tool_name, env=env)
        assert _is_read_nudge(out), out
    assert not list((proj / "graphify-out" / "cache" / "hook_sessions").glob("*.denied"))
    # The Read tool on the same file is still denied once.
    out = _read_tool(proj / "src" / "app.py", proj)
    assert out  # soft mode here (no --strict): the nudge
    r = subprocess.run([sys.executable, "-m", "graphify", "hook-guard", "read", "--strict"],
                       input=json.dumps({"session_id": "r", "tool_name": "Read",
                                         "tool_input": {"file_path": str(proj / "src" / "app.py")}}),
                       capture_output=True, text=True, cwd=proj, env=_env(proj))
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_relative_path_resolves_against_the_bash_cwd(tmp_path):
    proj = _project(tmp_path)
    payload = {"session_id": SID, "tool_name": "Bash", "cwd": str(proj / "src"),
               "tool_input": {"command": "cat app.py"}}
    r = subprocess.run([sys.executable, "-m", "graphify", "hook-guard", "search"], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=proj, env=_env(proj))
    assert _is_read_nudge(r.stdout)
    assert "- run() (src/app.py L3)" in r.stdout


def test_stale_file_gets_the_stale_read_nudge(tmp_path):
    proj = _project(tmp_path)
    (proj / "graphify-out" / "needs_update").write_text("1", encoding="utf-8")
    out = _bash("cat src/app.py", proj)
    assert "may be STALE" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("command", [
    "grep -rn run src",
    "rg run src/app.py",
    "sed 's/a/b/' src/app.py",     # no -n: still counts as a search
    "awk '/run/' src/app.py",
])
def test_searches_keep_the_search_nudge(command, tmp_path):
    proj = _project(tmp_path)
    out = _bash(command, proj)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "Finding where something lives is what the graph answers" in ctx
    # Control: the same session's read gets the read nudge.
    assert _is_read_nudge(_bash("cat src/app.py", proj))


def test_no_graph_no_nudge(tmp_path):
    proj = _project(tmp_path)
    (proj / "graphify-out" / "graph.json").unlink()
    assert _bash("cat src/app.py", proj) == ""
    (proj / "graphify-out" / "graph.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    assert _is_read_nudge(_bash("cat src/app.py", proj))
