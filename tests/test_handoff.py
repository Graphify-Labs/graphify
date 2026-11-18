"""Tests for graphify.handoff."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from graphify import handoff
from graphify.handoff import (
    build_handoff,
    find_transcript,
    git_state,
    graph_pointers,
    main,
    project_slug,
    redact,
    render_handoff,
    scan_transcript,
)


# ---------------------------------------------------------------------------
# Synthetic transcript helpers
# ---------------------------------------------------------------------------

def _user(text, ts="2026-01-01T10:00:00.000Z", **extra):
    return {"type": "user", "timestamp": ts, "sessionId": "sess-1", "cwd": "/proj",
            "message": {"role": "user", "content": text}, **extra}


def _tool_result(text="FILE BODY SHOULD NOT LEAK", ts="2026-01-01T10:01:00.000Z"):
    return {"type": "user", "timestamp": ts, "sessionId": "sess-1",
            "toolUseResult": {"stdout": text},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


def _assistant(*blocks, ts="2026-01-01T10:00:30.000Z", tokens=1000, rid=None, **extra):
    rec = {"type": "assistant", "timestamp": ts, "sessionId": "sess-1",
           "message": {"role": "assistant", "content": list(blocks),
                       "usage": {"input_tokens": 10, "cache_read_input_tokens": tokens,
                                 "cache_creation_input_tokens": 5, "output_tokens": 99}},
           **extra}
    if rid:
        rec["requestId"] = rid
    return rec


def _tool(name, **args):
    return {"type": "tool_use", "id": "t1", "name": name, "input": args}


def _prose(text="ASSISTANT PROSE SHOULD NOT LEAK"):
    return {"type": "text", "text": text}


def _write(path: Path, records, compact=False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sep = (",", ":") if compact else None
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=sep) + "\n")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch, _sandbox_home):
    """Throwaway config dir and cwd; returns (project dir, config dir).

    HOME is already sandboxed by conftest's autouse ``_sandbox_home``; the
    transcripts live under that home's ``.claude``.
    """
    config = _sandbox_home / ".claude"
    project = tmp_path / "My Proj"
    project.mkdir(parents=True)
    (config / "projects").mkdir(parents=True)
    monkeypatch.chdir(project)
    return project, config


def _session_dir(project: Path, config: Path) -> Path:
    return config / "projects" / project_slug(os.path.realpath(project))


# ---------------------------------------------------------------------------
# Slug resolution and session selection
# ---------------------------------------------------------------------------

def test_project_slug_replaces_non_alphanumerics():
    assert project_slug("/Users/a/My Proj") == "-Users-a-My-Proj"
    assert project_slug("/Users/a/app_v2.1") == "-Users-a-app-v2-1"


def test_config_dir_env_override(env, tmp_path, monkeypatch, _sandbox_home):
    project, _ = env
    assert handoff.claude_config_dir() == _sandbox_home / ".claude"
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    assert handoff.claude_config_dir() == cfg
    expected = _write(_session_dir(project, cfg) / "aaa.jsonl", [_user("hi")])
    assert find_transcript() == expected


def test_find_transcript_picks_newest_for_cwd(env):
    project, config = env
    sdir = _session_dir(project, config)
    old = _write(sdir / "aaa.jsonl", [_user("old")])
    new = _write(sdir / "bbb.jsonl", [_user("new")])
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))
    # A newer transcript of another project must not win.
    other = _write(config / "projects" / "-other" / "ccc.jsonl", [_user("x")])
    os.utime(other, (9_000, 9_000))
    assert find_transcript() == new


def test_find_transcript_from_subdirectory(env, monkeypatch):
    project, config = env
    expected = _write(_session_dir(project, config) / "aaa.jsonl", [_user("hi")])
    sub = project / "src" / "pkg"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert find_transcript() == expected


def test_find_transcript_by_session_id_and_prefix(env):
    project, config = env
    sdir = _session_dir(project, config)
    first = _write(sdir / "1111-aaaa.jsonl", [_user("a")])
    _write(sdir / "2222-bbbb.jsonl", [_user("b")])
    elsewhere = _write(config / "projects" / "-other" / "3333-cccc.jsonl", [_user("c")])
    assert find_transcript(session="1111-aaaa") == first
    assert find_transcript(session="1111") == first
    assert find_transcript(session="3333-cccc") == elsewhere
    assert find_transcript(session="nope") is None
    assert find_transcript(session="../1111-aaaa") is None


def test_find_transcript_explicit_path(env, tmp_path):
    path = _write(tmp_path / "elsewhere" / "t.jsonl", [_user("a")])
    assert find_transcript(transcript=path) == path
    assert find_transcript(transcript=tmp_path / "missing.jsonl") is None


def test_find_transcript_none_without_project_dir(env):
    assert find_transcript() is None


# ---------------------------------------------------------------------------
# Scan: human vs tool result, counts, ranking
# ---------------------------------------------------------------------------

def test_scan_separates_human_prompts_from_everything_else(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        {"type": "api-request-blob", "message": {"content": "noise"}},
        _user("first request"),
        _assistant(_prose(), _tool("Read", file_path="/proj/a.py")),
        _tool_result(),
        _user("meta noise", isMeta=True),
        _user("subagent prompt", isSidechain=True),
        _user("compaction summary text", isCompactSummary=True),
        _user("<task-notification>agent done</task-notification>"),
        _user("<local-command-stdout>out</local-command-stdout>"),
        _user("[Request interrupted by user]"),
        _user([{"type": "text", "text": "<system-reminder>x</system-reminder>"}]),
        _user([{"type": "text", "text": "block prompt <system-reminder>hidden</system-reminder>"}]),
        _user("<command-name>/compact</command-name><command-args>keep tests</command-args>"),
        _user("<div>pasted html</div>", ts="2026-01-02T11:00:00.000Z"),
    ])
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n\n", encoding="utf-8")
    s = scan_transcript(path)
    assert s.prompt_count == 4
    assert s.first_prompt == "first request"
    assert s.last_prompts == ["block prompt", "/compact keep tests", "<div>pasted html</div>"]
    assert s.compactions == 1
    assert s.session_id == "sess-1"
    assert s.first_ts.startswith("2026-01-01T10:00") and s.last_ts.startswith("2026-01-02T11:00")


def test_scan_handles_compact_json_separators(tmp_path):
    path = _write(tmp_path / "s.jsonl", [_user("hello"), _assistant(_prose())], compact=True)
    s = scan_transcript(path)
    assert (s.prompt_count, s.api_requests) == (1, 1)


def test_scan_counts_requests_and_last_context(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _user("go"),
        _assistant(_prose(), tokens=1000, rid="r1"),
        _assistant(_tool("Read", file_path="/p/a"), tokens=1000, rid="r1"),  # same response
        _assistant(_prose(), tokens=5000, rid="r2"),
        _assistant(_prose(), tokens=999_999, rid="r9", isSidechain=True),
    ])
    s = scan_transcript(path)
    assert s.api_requests == 2
    assert s.context_tokens == 10 + 5000 + 5


def test_scan_keeps_only_last_prompts(tmp_path):
    path = _write(tmp_path / "s.jsonl", [_user(f"prompt {i}") for i in range(20)])
    s = scan_transcript(path)
    assert s.prompt_count == 20
    assert s.first_prompt == "prompt 0"
    assert s.last_prompts == [f"prompt {i}" for i in range(15, 20)]


def test_edit_and_read_ranking(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _user("go"),
        _assistant(
            _tool("Edit", file_path="/proj/b.py", old_string="x", new_string="y"),
            _tool("Edit", file_path="/proj/a.py", old_string="x", new_string="y"),
            _tool("Write", file_path="/proj/a.py", content="SECRET BODY"),
            _tool("MultiEdit", file_path="/proj/a.py", edits=[]),
            _tool("NotebookEdit", notebook_path="/proj/n.ipynb"),
            _tool("Read", file_path="/proj/a.py"),
            _tool("Read", file_path="/proj/ref.md"),
            _tool("Read", file_path="/proj/ref.md"),
            _tool("Read", file_path="/proj/other.md"),
            _tool("Bash", command="cat /proj/zzz.py"),
        ),
    ])
    s = scan_transcript(path)
    assert s.edited == {"/proj/a.py": 3, "/proj/b.py": 1, "/proj/n.ipynb": 1}
    s.cwd = "/proj"
    text = render_handoff(s)
    edited = text.split("## Files edited")[1].split("##")[0]
    assert edited.index("`a.py` — 3 edits") < edited.index("`b.py` — 1 edit")
    reads = text.split("## Reference material")[1].split("##")[0]
    assert reads.index("`ref.md` — 2 reads") < reads.index("`other.md` — 1 read")
    assert "a.py" not in reads  # edited files are not reference material
    assert "SECRET BODY" not in text and "zzz.py" not in text


def test_reference_material_capped_at_ten(tmp_path):
    reads = [_tool("Read", file_path=f"/proj/f{i:02d}.py") for i in range(15)]
    s = scan_transcript(_write(tmp_path / "s.jsonl", [_user("go"), _assistant(*reads)]))
    s.cwd = "/proj"
    section = render_handoff(s).split("## Reference material")[1].split("##")[0]
    assert section.count(" read") == 10


def test_task_list_last_state(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _user("go"),
        _assistant(_tool("TodoWrite", todos=[{"content": "stale item", "status": "pending"}])),
        _assistant(_tool("TodoWrite", todos=[
            {"content": "write parser", "status": "completed"},
            {"content": "add tests", "status": "in_progress"},
            {"content": "wire cli", "status": "pending"},
        ])),
    ])
    s = scan_transcript(path)
    assert s.todos == [("completed", "write parser"), ("in_progress", "add tests"),
                       ("pending", "wire cli")]
    text = render_handoff(s)
    assert "- [x] write parser" in text and "- [~] add tests" in text and "- [ ] wire cli" in text
    assert "stale item" not in text


def test_task_list_plan_tool_advance(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _assistant(_tool("mcp__x__update_plan", items=[
            {"content": "one", "status": "in_progress"}, {"content": "two", "status": "pending"}])),
        _assistant(_tool("mcp__x__update_plan", advance=True)),
    ])
    assert scan_transcript(path).todos == [("completed", "one"), ("in_progress", "two")]


def test_task_create_and_update(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _assistant(_tool("TaskCreate", subject="alpha"), _tool("TaskCreate", subject="beta")),
        _assistant(_tool("TaskUpdate", taskId="1", status="completed")),
    ])
    assert scan_transcript(path).todos == [("completed", "alpha"), ("pending", "beta")]


# ---------------------------------------------------------------------------
# Privacy: no tool output / assistant prose, secrets redacted
# ---------------------------------------------------------------------------

def test_note_excludes_tool_output_and_assistant_prose(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _user("please fix the parser"),
        _assistant(_prose(), _tool("Bash", command="echo BASH COMMAND SHOULD NOT LEAK")),
        _tool_result(),
        _user("compacted", isCompactSummary=True),
    ])
    text = build_handoff(path, cwd=tmp_path)
    assert "please fix the parser" in text
    for leaked in ("SHOULD NOT LEAK", "compacted"):
        assert leaked not in text


@pytest.mark.parametrize("secret", [
    "ghp_" + "a1B2" * 9,
    "sk-ant-" + "x9Y8" * 8,
    "AKIA" + "ABCDEFGH12345678",
    "9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c",   # bare 40-hex token
    "Zx9Qw3Er7Ty1Ui5Op2As8Df4Gh6Jk0LzXc",          # bare mixed-case token
])
def test_redact_masks_token_shapes(secret):
    out = redact(f"use {secret} here")
    assert secret not in out and "[redacted]" in out


@pytest.mark.parametrize("text,gone", [
    ("API_KEY=hunter2hunter2", "hunter2hunter2"),
    ("export DB_PASSWORD='s3cr3tpw'", "s3cr3tpw"),
    ("password: correcthorse", "correcthorse"),
    ("my token = abcd1234", "abcd1234"),
    ("postgres://admin:pa55word@db.local/x", "pa55word"),
])
def test_redact_masks_assignments(text, gone):
    out = redact(text)
    assert gone not in out and "[redacted]" in out


@pytest.mark.parametrize("text", [
    "refactor graphify/handoff.py and tests/test_handoff.py please",
    "the monkey: banana keyboard: qwerty layout",
    "rename the-very-long-kebab-case-branch-name-version-2 soon",
    "see src/components/navigation/sidebar/SidebarItem.tsx",
])
def test_redact_leaves_ordinary_text(text):
    assert redact(text) == text


def test_prompt_excerpts_are_redacted_and_truncated(tmp_path):
    secret = "ghp_" + "a1B2" * 9
    path = _write(tmp_path / "s.jsonl", [
        _user(f"deploy with TOKEN={secret}\nand then\n\n  verify"),
        _user("x" * 50 + " word" * 500),
    ])
    text = build_handoff(path, cwd=tmp_path)
    assert secret not in text
    assert "- First: deploy with TOKEN=[redacted] and then verify" in text
    latest = [line for line in text.splitlines() if line.startswith("- xxxxx")][0]
    assert len(latest) <= 2 + handoff.PROMPT_MAX_CHARS and latest.endswith("…")


# ---------------------------------------------------------------------------
# Truncation under the cap
# ---------------------------------------------------------------------------

def _big_summary(tmp_path):
    edits = [_tool("Edit", file_path=f"/proj/src/module_{i:03d}.py") for i in range(60)]
    reads = [_tool("Read", file_path=f"/proj/docs/reference_{i:03d}.md") for i in range(40)]
    todos = [{"content": f"task number {i} " + "detail " * 10, "status": "pending"}
             for i in range(30)]
    path = _write(tmp_path / "s.jsonl", [
        _user("first " + "long request " * 60),
        *[_user(f"follow-up {i} " + "more words " * 60) for i in range(8)],
        _assistant(*edits, *reads, _tool("TodoWrite", todos=todos)),
    ])
    s = scan_transcript(path)
    s.cwd = "/proj"
    return s


@pytest.mark.parametrize("cap", [6000, 2500, 1200, 600, 200, 40])
def test_render_respects_cap_without_cutting_lines(tmp_path, cap):
    s = _big_summary(tmp_path)
    full = render_handoff(s, max_chars=10**9)
    text = render_handoff(s, max_chars=cap)
    assert len(text) <= cap
    assert text == "" or text.endswith("\n")
    full_lines = set(full.splitlines())
    for line in text.splitlines():
        assert line in full_lines or line.startswith("- … ")


def test_trimming_drops_least_important_first(tmp_path):
    s = _big_summary(tmp_path)
    text = render_handoff(s, max_chars=2500)
    assert text.startswith("# Session handoff")
    assert "## Resume" in text and "Read this file first" in text
    assert "## Requests" in text and "- First: first long request" in text
    assert "follow-up 7" in text       # newest prompt survives
    assert "module_000.py" in text     # top of the edited list survives
    assert "more not shown" in text
    assert "reference_039.md" not in text


def test_default_cap_and_small_session_untouched(tmp_path):
    path = _write(tmp_path / "s.jsonl", [_user("only request"), _assistant(_prose())])
    text = build_handoff(path, cwd=tmp_path)
    assert len(text) <= handoff.DEFAULT_MAX_CHARS
    assert "- Requests: 1 human prompt, 1 API request" in text
    assert "- Last context size: 1,015 tokens" in text
    assert "- Session: `sess-1`" in text
    for absent in ("## Files edited", "## Reference material", "## Graph pointers",
                   "## Task list", "## Uncommitted git state", "Latest, newest first"):
        assert absent not in text


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def test_git_state_none_outside_repo(tmp_path):
    assert git_state(tmp_path) is None


def test_git_missing_or_timeout_is_silent(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(handoff.subprocess, "run", boom)
    assert git_state(tmp_path) is None

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("git", 5)
    monkeypatch.setattr(handoff.subprocess, "run", slow)
    assert git_state(tmp_path) is None
    path = _write(tmp_path / "s.jsonl", [_user("hi")])
    assert "git state" not in build_handoff(path, cwd=tmp_path)


def test_git_section_rendered(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=tmp_path, check=True, capture_output=True)
    try:
        git("init", "-q", "-b", "work")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    (tmp_path / "tracked.py").write_text("a = 1\n", encoding="utf-8")
    git("add", "tracked.py")
    git("commit", "-q", "-m", "init")
    (tmp_path / "tracked.py").write_text("a = 2\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("b = 1\n", encoding="utf-8")
    path = _write(tmp_path.parent / (tmp_path.name + "-t") / "s.jsonl", [_user("hi")])
    text = build_handoff(path, cwd=tmp_path)
    section = text.split("## Uncommitted git state")[1].split("##")[0]
    assert "- Branch: `work`" in section
    assert "- Working tree: 1 modified, 1 untracked" in section
    assert "1 file changed" in section
    assert "tracked.py" in section and "new.py" in section


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def _graph(root: Path, nodes, links=(), labels=None) -> Path:
    out = root / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps({"nodes": nodes, "links": list(links)}),
                                    encoding="utf-8")
    if labels is not None:
        (out / ".graphify_labels.json").write_text(json.dumps(labels), encoding="utf-8")
    return out / "graph.json"


def test_graph_pointers_match_and_rank(tmp_path):
    gp = _graph(tmp_path, [
        {"id": "a", "label": "a.py", "source_file": "src/a.py", "community": 3},
        {"id": "a_parse", "label": "parse()", "source_file": "src/a.py", "community": 3},
        {"id": "a_odd", "label": 'bad "quoted"', "source_file": "./src/a.py", "community": 4},
        {"id": "b", "label": "b.py", "source_file": "src/b.py", "community_name": "Named"},
        {"id": "c", "label": "c.py", "source_file": str(tmp_path / "src" / "c.py")},
        {"label": "no source"}, "garbage",
    ], links=[
        {"source": "a_parse", "target": "b"}, {"source": "a_parse", "target": "a"},
        {"source": "a_parse", "target": "c"}, {"source": ["x"], "target": None},
    ], labels={"3": "Parsing", "4": {"label": "Odds"}})
    files = [str(tmp_path / "src" / n) for n in ("a.py", "b.py", "c.py", "untracked.py")]
    got = graph_pointers(gp, files, tmp_path)
    assert [p["file"] for p in got] == files[:3]
    assert got[0]["communities"] == ["Parsing", "Odds"]
    assert got[0]["node_count"] == 3
    assert got[0]["labels"] == ["parse()", "a.py"]  # best connected first, unsafe label skipped
    assert got[1]["communities"] == ["Named"]
    assert got[2]["communities"] == [] and got[2]["labels"] == ["c.py"]


def test_graph_pointers_tolerate_bad_graphs(tmp_path):
    files = [str(tmp_path / "a.py")]
    assert graph_pointers(tmp_path / "missing.json", files, tmp_path) == []
    for body in ("not json", "[]", '{"nodes": 5}', '{"nodes": [{"id": 1}], "links": 7}'):
        gp = tmp_path / "g.json"
        gp.write_text(body, encoding="utf-8")
        assert graph_pointers(gp, files, tmp_path) == []
    gp.write_text(json.dumps({"nodes": [{"source_file": "a.py"}]}), encoding="utf-8")
    assert graph_pointers(gp, files, tmp_path) == [
        {"file": files[0], "communities": [], "node_count": 1, "labels": []}]


def test_graph_section_in_note(tmp_path):
    root = Path(os.path.realpath(tmp_path)) / "proj"
    root.mkdir()
    _graph(root, [{"id": "a", "label": "Parser", "source_file": "src/a.py", "community": 0}])
    path = _write(tmp_path / "t" / "s.jsonl", [
        _user("go"), _assistant(_tool("Edit", file_path=str(root / "src" / "a.py")))])
    text = build_handoff(path, cwd=root)
    assert '- `src/a.py` — 1 node in Community 0: `graphify explain "Parser"`' in text


def test_missing_graph_omits_section(tmp_path):
    path = _write(tmp_path / "t" / "s.jsonl", [
        _user("go"), _assistant(_tool("Edit", file_path=str(tmp_path / "a.py")))])
    text = build_handoff(path, cwd=tmp_path)
    assert "## Files edited" in text and "Graph pointers" not in text


# ---------------------------------------------------------------------------
# CLI and atomic write
# ---------------------------------------------------------------------------

def test_main_writes_default_output(env, capsys):
    project, config = env
    _write(_session_dir(project, config) / "abc.jsonl", [
        _user("build the thing"), _assistant(_tool("Edit", file_path=str(project / "x.py")))])
    assert main([]) == 0
    out = project / "graphify-out" / "HANDOFF.md"
    text = out.read_text(encoding="utf-8")
    assert "build the thing" in text and "## Resume" in text
    assert "HANDOFF.md" in capsys.readouterr().out
    assert [p.name for p in out.parent.iterdir()] == ["HANDOFF.md"]  # no temp left behind


def test_main_stdout_writes_nothing(env, capsys):
    project, config = env
    _write(_session_dir(project, config) / "abc.jsonl", [_user("print me")])
    assert main(["--stdout"]) == 0
    assert "print me" in capsys.readouterr().out
    assert not (project / "graphify-out").exists()


def test_main_out_session_and_max_chars(env, tmp_path):
    project, config = env
    sdir = _session_dir(project, config)
    _write(sdir / "one.jsonl", [_user("from session one")])
    newer = _write(sdir / "two.jsonl", [_user("from session two " + "pad " * 400)])
    os.utime(newer, (4_000_000_000, 4_000_000_000))
    dest = tmp_path / "notes" / "H.md"
    assert main(["--session", "one", "--out", str(dest)]) == 0
    assert "from session one" in dest.read_text(encoding="utf-8")
    assert main(["--out", str(dest), "--max-chars", "900"]) == 0
    text = dest.read_text(encoding="utf-8")
    assert "from session two" in text and len(text) <= 900


def test_main_transcript_flag(env, tmp_path, capsys):
    path = _write(tmp_path / "x" / "t.jsonl", [_user("explicit transcript")])
    assert main(["--transcript", str(path), "--stdout"]) == 0
    assert "explicit transcript" in capsys.readouterr().out


def test_main_errors(env, tmp_path, capsys):
    assert main([]) == 1
    assert "no Claude Code transcript" in capsys.readouterr().err
    assert main(["--transcript", str(tmp_path / "nope.jsonl")]) == 1
    assert main(["--session", "nope"]) == 1
    assert main(["--max-chars", "0"]) == 2
    assert main(["--bogus"]) == 2


def test_failed_write_keeps_previous_note(env, monkeypatch, capsys):
    project, config = env
    _write(_session_dir(project, config) / "abc.jsonl", [_user("new content")])
    out = project / "graphify-out" / "HANDOFF.md"
    out.parent.mkdir()
    out.write_text("previous note\n", encoding="utf-8")

    def fail(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr("graphify.paths.os_replace_with_fallback", fail)
    assert main([]) == 1
    assert "cannot write" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "previous note\n"
    assert [p.name for p in out.parent.iterdir()] == ["HANDOFF.md"]
