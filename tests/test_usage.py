"""Tests for graphify.usage — synthetic transcripts only, never ~/.claude."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from graphify.usage import analyze, default_projects_dir, main, render_html, render_text

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
SECRET = "TOP-SECRET-BODY"


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

def _assistant(mid, ctx, *, out=10, ts="2026-06-20T10:00:00.000Z", model="claude-opus-4",
               cwd="/work/alpha", session="s1", blocks=None, req=None):
    """One assistant line. *ctx* = (input, cache_creation, cache_read)."""
    return {
        "type": "assistant", "timestamp": ts, "sessionId": session, "cwd": cwd,
        "requestId": req or f"req_{mid}",
        "message": {
            "id": mid, "model": model, "role": "assistant",
            "usage": {"input_tokens": ctx[0], "cache_creation_input_tokens": ctx[1],
                      "cache_read_input_tokens": ctx[2], "output_tokens": out},
            "content": blocks or [{"type": "text", "text": SECRET}],
        },
    }


def _tool_use(tid, name, **inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _result(tid, content, *, ts="2026-06-20T10:00:01.000Z", session="s1", cwd="/work/alpha"):
    return {
        "type": "user", "timestamp": ts, "sessionId": session, "cwd": cwd,
        "message": {"role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]},
    }


def _write(path: Path, lines) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line if isinstance(line, str) else json.dumps(line))
            fh.write("\n")
    return path


@pytest.fixture
def projects(tmp_path):
    """Two projects, three sessions; totals are spelled out in the tests."""
    root = tmp_path / "projects"
    # alpha/s1: 3 requests, contexts 40k, 150k, 450k
    _write(root / "-work-alpha" / "s1.jsonl", [
        _assistant("m1", (1_000, 9_000, 30_000), out=100,
                   blocks=[_tool_use("t1", "Read", file_path="/work/alpha/a.py")]),
        # same response written twice (streamed blocks) — must count once
        _assistant("m1", (1_000, 9_000, 30_000), out=100,
                   blocks=[_tool_use("t2", "Bash", command=SECRET)]),
        _result("t1", "x" * 500),
        _result("t2", [{"type": "text", "text": "y" * 200}, {"type": "text", "text": "z" * 100},
                       {"type": "image", "source": {"data": "ignored"}}]),
        "{this is not json",
        "[1, 2, 3]",
        "",
        _assistant("m2", (0, 50_000, 100_000), out=200, blocks=[
            _tool_use("t3", "Read", file_path="/work/alpha/a.py"),
            _tool_use("t4", "Read", file_path="/work/alpha/b.py"),
        ]),
        _result("t3", "x" * 700),
        _result("t4", "b" * 50),
        _assistant("m3", (0, 0, 450_000), out=300,
                   blocks=[_tool_use("t5", "Read", file_path="/work/alpha/a.py")]),
        _result("t5", "x" * 300),
        {"type": "assistant", "timestamp": "2026-06-20T10:05:00Z", "sessionId": "s1",
         "message": {"id": "syn", "model": "<synthetic>",
                     "usage": {"input_tokens": 0, "output_tokens": 0}, "content": []}},
    ])
    # alpha/s2: old session, 1 request of 60k, sonnet
    _write(root / "-work-alpha" / "s2.jsonl", [
        _assistant("m4", (60_000, 0, 0), out=50, ts="2026-06-01T08:00:00Z",
                   model="claude-sonnet-4", session="s2"),
    ])
    # beta/s3: 2 requests of 250k each, with a nested subagent file
    _write(root / "-work-beta" / "s3.jsonl", [
        _assistant("m5", (0, 0, 250_000), out=10, ts="2026-06-19T09:00:00Z",
                   cwd="/work/beta", session="s3",
                   blocks=[_tool_use("t6", "Read", file_path="/work/alpha/a.py")]),
        _result("t6", "q" * 40, session="s3", cwd="/work/beta"),
        _assistant("m6", (0, 0, 250_000), out=10, ts="2026-06-19T09:01:00Z",
                   cwd="/work/beta", session="s3"),
    ])
    _write(root / "-work-beta" / "s3" / "subagents" / "agent-a1.jsonl", [
        _assistant("m7", (10_000, 0, 0), out=5, ts="2026-06-19T09:02:00Z",
                   cwd="/work/beta", session="s3"),
    ])
    return root


@pytest.fixture
def report(projects):
    return analyze(projects, now=NOW)


# ---------------------------------------------------------------------------
# totals, dedup, malformed lines
# ---------------------------------------------------------------------------

def test_dedup_by_message_id_and_request_id(report):
    # m1 is written twice; <synthetic> is ignored
    assert report["totals"]["requests"] == 7
    assert report["totals"]["input_tokens"] == 1_000 + 60_000 + 10_000
    assert report["totals"]["output_tokens"] == 100 + 200 + 300 + 50 + 10 + 10 + 5


def test_same_message_id_different_request_counts_twice(tmp_path):
    root = tmp_path / "p"
    _write(root / "proj" / "s.jsonl", [
        _assistant("m1", (10, 0, 0), req="r1"),
        _assistant("m1", (10, 0, 0), req="r2"),
    ])
    assert analyze(root, now=NOW)["totals"]["requests"] == 2


def test_resumed_copy_in_another_file_counts_once(tmp_path):
    root = tmp_path / "p"
    line = _assistant("m1", (10, 0, 0), blocks=[_tool_use("t1", "Bash")])
    _write(root / "proj" / "a.jsonl", [line, _result("t1", "abc")])
    _write(root / "proj" / "b.jsonl", [line, _result("t1", "abc")])
    rep = analyze(root, now=NOW)
    assert rep["totals"]["requests"] == 1
    assert rep["sessions"]["count"] == 1
    assert rep["tools"]["by_tool"] == [
        {"tool": "Bash", "calls": 1, "results": 1, "chars": 3, "share": 1.0}]


def test_totals_by_token_type(report):
    t = report["totals"]
    assert t["cache_creation_input_tokens"] == 9_000 + 50_000
    assert t["cache_read_input_tokens"] == 30_000 + 100_000 + 450_000 + 500_000
    assert t["context_tokens"] == 40_000 + 150_000 + 450_000 + 60_000 + 500_000 + 10_000
    assert t["total_tokens"] == t["context_tokens"] + t["output_tokens"]
    assert t["avg_context_per_request"] == round(1_210_000 / 7)


def test_malformed_lines_are_skipped_and_counted(report):
    # "{this is not json" has no marker and is dropped before parsing; build a
    # line that passes the prefilter but is not valid JSON.
    assert report["totals"]["requests"] == 7
    assert report["source"]["malformed_lines"] == 0


def test_malformed_line_with_marker(tmp_path):
    root = tmp_path / "p"
    _write(root / "proj" / "s.jsonl", [
        '{"message": {"usage": {"input_tokens": 5',
        '["usage", 1]',
        '{"message": "usage"}',
        '{"message": {"id": "x", "usage": "nope", "content": "tool_use"}}',
        _assistant("ok", (5, 0, 0)),
    ])
    rep = analyze(root, now=NOW)
    assert rep["totals"]["requests"] == 1
    assert rep["source"]["malformed_lines"] == 2


# ---------------------------------------------------------------------------
# breakdowns
# ---------------------------------------------------------------------------

def test_by_model(report):
    models = {m["model"]: m for m in report["by_model"]}
    assert set(models) == {"claude-opus-4", "claude-sonnet-4"}
    assert models["claude-sonnet-4"]["requests"] == 1
    assert models["claude-sonnet-4"]["total_tokens"] == 60_050
    assert report["by_model"][0]["model"] == "claude-opus-4"


def test_by_day(report):
    days = {d["day"]: d for d in report["by_day"]}
    assert list(days) == ["2026-06-01", "2026-06-19", "2026-06-20"]
    assert days["2026-06-20"]["requests"] == 3
    assert days["2026-06-19"]["total_tokens"] == 510_000 + 25


def test_by_project_uses_cwd_as_name(report):
    projs = {p["slug"]: p for p in report["by_project"]}
    assert projs["-work-alpha"]["name"] == "/work/alpha"
    assert projs["-work-beta"]["name"] == "/work/beta"
    assert projs["-work-alpha"]["requests"] == 4
    assert projs["-work-alpha"]["sessions"] == 2
    assert projs["-work-beta"]["sessions"] == 2  # session + subagent transcript


def test_context_buckets(report):
    b = {row["bucket"]: row for row in report["context_buckets"]}
    assert [row["bucket"] for row in report["context_buckets"]] == [
        "<50k", "50-100k", "100-200k", "200-400k", "400k+"]
    assert (b["<50k"]["requests"], b["<50k"]["tokens"]) == (2, 50_000)
    assert (b["50-100k"]["requests"], b["50-100k"]["tokens"]) == (1, 60_000)
    assert (b["100-200k"]["requests"], b["100-200k"]["tokens"]) == (1, 150_000)
    assert (b["200-400k"]["requests"], b["200-400k"]["tokens"]) == (2, 500_000)
    assert (b["400k+"]["requests"], b["400k+"]["tokens"]) == (1, 450_000)
    assert b["400k+"]["token_share"] == round(450_000 / 1_210_000, 4)
    assert sum(row["requests"] for row in report["context_buckets"]) == 7


def test_bucket_boundaries(tmp_path):
    root = tmp_path / "p"
    _write(root / "proj" / "s.jsonl", [
        _assistant("a", (49_999, 0, 0)), _assistant("b", (50_000, 0, 0)),
        _assistant("c", (200_000, 0, 0)), _assistant("d", (400_000, 0, 0)),
    ])
    b = {r["bucket"]: r["requests"] for r in analyze(root, now=NOW)["context_buckets"]}
    assert b == {"<50k": 1, "50-100k": 1, "100-200k": 0, "200-400k": 1, "400k+": 1}


def test_per_session_stats(report):
    s = report["sessions"]
    assert s["count"] == 4
    by_id = {x["id"]: x for x in s["top"]}
    s1 = by_id["s1"]
    assert (s1["requests"], s1["context_tokens"]) == (3, 640_000)
    assert (s1["max_context"], s1["first_context"]) == (450_000, 40_000)
    assert s1["output_tokens"] == 600
    assert s1["project_name"] == "/work/alpha"
    assert by_id["agent-a1"]["subagent"] is True
    assert [x["id"] for x in s["top"]] == ["s1", "s3", "s2", "agent-a1"]
    assert (s["over_200k"], s["over_400k"]) == (2, 1)


def test_top_n_and_share(projects):
    rep = analyze(projects, top=2, now=NOW)
    s = rep["sessions"]
    assert s["top_n"] == 2 and len(s["top"]) == 2
    assert s["top_tokens"] == 640_000 + 500_000
    assert s["top_share"] == round(1_140_000 / 1_210_000, 4)


def test_overhead_estimate(report):
    o = report["overhead"]
    # s1: 40k x 3, s2: 60k x 1, agent: 10k x 1. s3 starts at 250k (a resumed
    # session), so its baseline is capped at 2x the median first request (60k).
    assert o["tokens"] == 120_000 + 60_000 + 240_000 + 10_000
    assert o["share"] == round(430_000 / 1_210_000, 4)
    assert o["avg_first_context"] == 57_500
    assert o["estimate"] is True


# ---------------------------------------------------------------------------
# tools and re-reads
# ---------------------------------------------------------------------------

def test_tool_result_chars_attributed_to_tool(report):
    tools = {t["tool"]: t for t in report["tools"]["by_tool"]}
    assert tools["Read"]["calls"] == 5
    assert tools["Read"]["chars"] == 500 + 700 + 50 + 300 + 40
    assert tools["Bash"] == {"tool": "Bash", "calls": 1, "results": 1, "chars": 300,
                             "share": round(300 / 1890, 4)}
    assert report["tools"]["total_chars"] == 1890
    assert report["tools"]["by_tool"][0]["tool"] == "Read"


def test_tool_result_without_tool_use_is_unknown(tmp_path):
    root = tmp_path / "p"
    _write(root / "proj" / "s.jsonl", [_assistant("a", (5, 0, 0)), _result("ghost", "12345")])
    tools = analyze(root, now=NOW)["tools"]["by_tool"]
    assert tools == [{"tool": "(unknown)", "calls": 0, "results": 1, "chars": 5, "share": 1.0}]


def test_reread_detection(report):
    r = report["rereads"]
    # a.py is read 3x in s1 (2 re-reads) and once in s3 (a different session)
    assert (r["reads"], r["rereads"]) == (5, 2)
    assert r["rate"] == 0.4
    assert r["chars_reread"] == 700 + 300
    assert r["top_files"] == [
        {"file_path": "/work/alpha/a.py", "reads": 4, "rereads": 2, "chars_reread": 1000}]


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------

def test_days_filter(projects):
    rep = analyze(projects, days=1, now=NOW)  # cutoff 2026-06-19T12:00Z
    assert rep["totals"]["requests"] == 3
    assert [d["day"] for d in rep["by_day"]] == ["2026-06-20"]
    assert rep["sessions"]["count"] == 1
    assert rep["source"]["days"] == 1
    assert analyze(projects, days=30, now=NOW)["totals"]["requests"] == 7


def test_project_filter_by_slug_and_cwd(tmp_path, projects):
    rep = analyze(projects, project="BETA", now=NOW)
    assert [p["slug"] for p in rep["by_project"]] == ["-work-beta"]
    assert rep["totals"]["requests"] == 3
    # cwd matches even when the directory slug does not
    _write(projects / "opaque-slug" / "s9.jsonl", [
        _assistant("m9", (7, 0, 0), cwd="/somewhere/gamma", session="s9")])
    rep = analyze(projects, project="gamma", now=NOW)
    assert [p["name"] for p in rep["by_project"]] == ["/somewhere/gamma"]
    assert analyze(projects, project="no-such-project", now=NOW)["totals"]["requests"] == 0


# ---------------------------------------------------------------------------
# recommendations and renderers
# ---------------------------------------------------------------------------

def test_recommendations_state_the_numbers(report):
    recs = report["recommendations"]
    text = " ".join(recs)
    assert all(isinstance(r, str) and r for r in recs)
    assert "79% of context tokens" in text  # 950k of 1.21M above 200k
    assert "40% of Read calls (2 of 5)" in text
    assert "Read results are 84%" in text
    assert "36% of all context" in text  # overhead


def test_render_text(report):
    text = render_text(report)
    for needle in ("Context size per request", "400k+", "Fixed overhead (estimate)",
                   "/work/alpha", "claude-opus-4", "Re-reads: 2 of 5", "Tool results"):
        assert needle in text
    assert SECRET not in text
    text.encode("ascii")  # terminal output stays ASCII


def test_no_transcript_content_in_any_output(report):
    assert SECRET not in json.dumps(report)
    assert SECRET not in render_html(report)


def test_html_is_self_contained(report):
    page = render_html(report)
    assert page.startswith("<!doctype html>")
    assert "<svg" in page and "<style>" in page
    assert "http://" not in page and "https://" not in page
    assert "<script" not in page and "<link" not in page and "@import" not in page
    assert not re.search(r"\b(src|href)\s*=", page)
    assert "prefers-color-scheme:dark" in page
    assert "/work/alpha/a.py" in page


def test_html_escapes_paths(tmp_path):
    root = tmp_path / "p"
    _write(root / "proj" / "s.jsonl", [
        _assistant("a", (5, 0, 0), cwd="/w/<script>alert(1)</script>",
                   blocks=[_tool_use("t1", "Read", file_path="/w/<b>.py"),
                           _tool_use("t2", "Read", file_path="/w/<b>.py")]),
    ])
    page = render_html(analyze(root, now=NOW))
    assert "<script>" not in page and "<b>.py" not in page
    assert "&lt;b&gt;.py" in page


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

JSON_KEYS = {
    "generated_at", "source", "totals", "by_model", "by_day", "by_project",
    "context_buckets", "sessions", "overhead", "tools", "rereads", "recommendations",
}


def test_main_text(projects, capsys):
    assert main(["--dir", str(projects)]) == 0
    out = capsys.readouterr().out
    assert "graphify usage - all transcripts" in out
    assert "Top 4 of 4 sessions" in out


def test_main_json_shape(projects, capsys):
    assert main(["--dir", str(projects), "--json", "--top", "3"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert set(doc) == JSON_KEYS
    assert set(doc["totals"]) == {
        "input_tokens", "output_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens", "context_tokens", "total_tokens", "requests",
        "sessions", "avg_context_per_request"}
    assert set(doc["sessions"]) == {
        "count", "top_n", "top_tokens", "top_share", "over_200k", "over_400k", "top"}
    assert set(doc["overhead"]) == {"estimate", "method", "tokens", "share", "avg_first_context"}
    assert set(doc["rereads"]) == {
        "reads", "rereads", "rate", "read_chars", "chars_reread", "top_files"}
    assert set(doc["tools"]) == {"total_chars", "by_tool"}
    assert len(doc["sessions"]["top"]) == 3
    assert doc["source"]["top"] == 3


def test_main_filters(projects, capsys):
    assert main(["--dir", str(projects), "--json", "--project", "beta", "--days", "100000"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["totals"]["requests"] == 3
    assert doc["source"]["project"] == "beta"


def test_main_html_default_path(projects, tmp_path, monkeypatch, capsys):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert main(["--dir", str(projects), "--html"]) == 0
    out = capsys.readouterr().out.strip()
    assert Path(out) == Path("graphify-out/usage.html")
    page = (cwd / "graphify-out" / "usage.html").read_text(encoding="utf-8")
    assert "Where the tokens went" in page
    assert "http://" not in page and "https://" not in page


def test_main_html_explicit_path(projects, tmp_path, capsys):
    target = tmp_path / "deep" / "dir" / "report.html"
    assert main(["--dir", str(projects), "--html", str(target)]) == 0
    assert capsys.readouterr().out.strip() == str(target)
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_main_json_and_html_keeps_stdout_json(projects, tmp_path, capsys):
    target = tmp_path / "r.html"
    assert main(["--dir", str(projects), "--json", "--html", str(target)]) == 0
    captured = capsys.readouterr()
    assert set(json.loads(captured.out)) == JSON_KEYS
    assert str(target) in captured.err
    assert target.exists()


def test_main_no_transcripts(tmp_path, capsys):
    empty = tmp_path / "nothing"
    assert main(["--dir", str(empty)]) == 0
    assert "No Claude Code transcripts found" in capsys.readouterr().out
    empty.mkdir()
    assert main(["--dir", str(empty), "--html", str(tmp_path / "x.html")]) == 0
    assert "No Claude Code transcripts found" in capsys.readouterr().out
    assert not (tmp_path / "x.html").exists()
    assert main(["--dir", str(empty), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["requests"] == 0


def test_default_projects_dir_honours_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert default_projects_dir() == tmp_path / "cfg" / "projects"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert default_projects_dir() == Path.home() / ".claude" / "projects"
