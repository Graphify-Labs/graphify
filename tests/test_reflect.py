"""Tests for `graphify reflect` and the work-memory reflection layer.

`graphify reflect` reads the outcome-tagged Q&A docs that `graphify save-result`
files into graphify-out/memory/ and writes a deterministic lessons artifact
(graphify-out/reflections/LESSONS.md) an agent can load next session: preferred
sources, known dead ends, and corrections — optionally grouped by community.

Covers the pure aggregation/rendering helpers (deterministic, no LLM, no graph
required) and the end-to-end CLI, including the "second session benefits from the
first" worked example from the issue.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from graphify.ingest import save_query_result
from graphify.reflect import (
    aggregate_lessons,
    lessons_fresh,
    load_memory_docs,
    parse_memory_doc,
    reflect,
    render_lessons_md,
)

PYTHON = sys.executable
FIXTURES = Path(__file__).parent / "fixtures"

# Fixed clock so time-decay scoring is byte-stable in tests (reflect/aggregate take `now`).
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _days_before(n: int) -> str:
    return (_NOW - timedelta(days=n)).isoformat()


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd, capture_output=True, text=True,
    )


# --- frontmatter parsing -------------------------------------------------------


def test_parse_round_trips_a_saved_doc(tmp_path):
    """parse_memory_doc reads back exactly what save_query_result wrote, including
    an escaped question and the source_nodes flow list."""
    out = save_query_result(
        'what is "attention"?', "softmax", tmp_path / "memory",
        query_type="explain", source_nodes=["AttentionLayer", "SoftmaxFunc"],
        outcome="useful",
    )
    parsed = parse_memory_doc(out.read_text(encoding="utf-8"))
    assert parsed is not None
    assert parsed["type"] == "explain"
    assert parsed["question"] == 'what is "attention"?'
    assert parsed["outcome"] == "useful"
    assert parsed["source_nodes"] == ["AttentionLayer", "SoftmaxFunc"]


def test_parse_returns_none_for_foreign_doc():
    """A plain markdown file with no frontmatter is skipped, not crashed on."""
    assert parse_memory_doc("# just a note\n\nno frontmatter here\n") is None
    assert parse_memory_doc("") is None


def test_round_trip_survives_backslash_newline_and_quoted_node(tmp_path):
    """save -> parse preserves tricky characters in the question, the correction,
    and (the previously-unescaped) source-node names exactly."""
    out = save_query_result(
        r'path is C:\Users and a "quote"', "a", tmp_path / "memory",
        source_nodes=[r'Node"With\Quote'],
        outcome="corrected", correction="line1\nline2",
    )
    parsed = parse_memory_doc(out.read_text(encoding="utf-8"))
    assert parsed is not None
    assert parsed["question"] == r'path is C:\Users and a "quote"'
    assert parsed["correction"] == "line1\nline2"
    assert parsed["source_nodes"] == [r'Node"With\Quote']


def test_parse_handles_crlf():
    doc = "---\r\ntype: \"query\"\r\noutcome: \"useful\"\r\nsource_nodes: [\"A\"]\r\n---\r\n# body\r\n"
    parsed = parse_memory_doc(doc)
    assert parsed is not None
    assert parsed["outcome"] == "useful"
    assert parsed["source_nodes"] == ["A"]


def test_load_memory_docs_skips_foreign_and_sorts(tmp_path):
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "foreign.md").write_text("# not a memory doc\n", encoding="utf-8")
    save_query_result("first", "a", mem, outcome="useful")
    save_query_result("second", "b", mem, outcome="dead_end")
    docs = load_memory_docs(mem)
    # Foreign doc dropped; the two real docs survive.
    assert len(docs) == 2
    assert {d["outcome"] for d in docs} == {"useful", "dead_end"}


def test_load_memory_docs_missing_dir_is_empty(tmp_path):
    assert load_memory_docs(tmp_path / "nope") == []


def _write_raw_doc(mem: Path, filename: str, date: str, *, outcome="dead_end",
                   question="q", nodes=None):
    """Write a memory doc with a controlled date so ordering is deterministic to assert."""
    mem.mkdir(parents=True, exist_ok=True)
    nodes = nodes or []
    lines = ["---", 'type: "query"', f'date: "{date}"', f'question: "{question}"',
             'contributor: "graphify"', f'outcome: "{outcome}"']
    if nodes:
        lines.append("source_nodes: [" + ", ".join(f'"{n}"' for n in nodes) + "]")
    lines += ["---", "", f"# Q: {question}", ""]
    (mem / filename).write_text("\n".join(lines), encoding="utf-8")


def test_load_memory_docs_orders_by_date_then_filename(tmp_path):
    """Determinism hinges on this sort: docs come back oldest-first, filename as tiebreak."""
    mem = tmp_path / "memory"
    _write_raw_doc(mem, "z.md", "2026-03-01", question="march")
    _write_raw_doc(mem, "a.md", "2026-01-01", question="january")
    _write_raw_doc(mem, "b.md", "2026-02-01", question="february")
    # Same date, two filenames -> filename tiebreak.
    _write_raw_doc(mem, "c.md", "2026-01-01", question="january-2")
    dates = [d["date"] for d in load_memory_docs(mem)]
    assert dates == ["2026-01-01", "2026-01-01", "2026-02-01", "2026-03-01"]
    # Within the tied date, "a.md" precedes "c.md".
    tied = [d["_path"] for d in load_memory_docs(mem) if d["date"] == "2026-01-01"]
    assert tied == ["a.md", "c.md"]


# --- aggregation ---------------------------------------------------------------


def _doc(outcome=None, nodes=None, question="q", correction="", date="2026-01-01"):
    return {
        "outcome": outcome, "source_nodes": nodes or [],
        "question": question, "correction": correction, "date": date,
    }


def test_aggregate_counts_each_outcome():
    docs = [
        _doc("useful", ["A"]), _doc("useful", ["A", "B"]),
        _doc("dead_end", ["C"]), _doc("corrected", correction="use D"),
        _doc(None),
    ]
    agg = aggregate_lessons(docs)
    assert agg["total"] == 5
    assert agg["counts"] == {"useful": 2, "dead_end": 1, "corrected": 1, "unmarked": 1}


def test_sources_split_into_preferred_tentative_contested():
    """Corroboration (k>=2) + sign decide the bucket, not raw frequency:
    A is useful twice but also a dead end -> contested; B twice-useful -> preferred;
    C once-useful -> tentative."""
    docs = [
        _doc("useful", ["A", "B"]), _doc("useful", ["A", "B"]),
        _doc("useful", ["C"]),
        _doc("dead_end", ["A"]),  # gives A a negative signal
    ]
    agg = aggregate_lessons(docs, now=_NOW, min_corroboration=2)
    preferred = [e["node"] for e in agg["preferred"]]
    tentative = [e["node"] for e in agg["tentative"]]
    contested = [e["node"] for e in agg["contested"]]
    assert preferred == ["B"]            # 2 useful, no negatives
    assert tentative == ["C"]            # 1 useful only
    assert contested == ["A"]            # 2 useful + 1 dead end
    # A never silently appears as a plain preferred/tentative source.
    assert "A" not in preferred and "A" not in tentative


def test_corroboration_threshold_promotes_only_repeated_nodes():
    """One save can't mint a 'preferred' lesson; a second distinct result promotes it."""
    one = aggregate_lessons([_doc("useful", ["A"])], now=_NOW, min_corroboration=2)
    assert [e["node"] for e in one["tentative"]] == ["A"]
    assert one["preferred"] == []

    two = aggregate_lessons(
        [_doc("useful", ["A"]), _doc("useful", ["A"])], now=_NOW, min_corroboration=2)
    assert [e["node"] for e in two["preferred"]] == ["A"]
    assert two["tentative"] == []


def test_recency_decides_contested_verdict():
    """A fresh dead_end outweighs a stale useful (30d half-life), so the contested
    node leans 'dead end'; flip the dates and it leans 'useful'."""
    stale_useful = _doc("useful", ["N"], date=_days_before(120))
    fresh_deadend = _doc("dead_end", ["N"], date=_days_before(1))
    agg = aggregate_lessons([stale_useful, fresh_deadend], now=_NOW)
    contested = agg["contested"]
    assert len(contested) == 1 and contested[0]["node"] == "N"
    assert contested[0]["verdict"] == "dead end"

    flipped = aggregate_lessons(
        [_doc("useful", ["N"], date=_days_before(1)),
         _doc("dead_end", ["N"], date=_days_before(120))], now=_NOW)
    assert flipped["contested"][0]["verdict"] == "useful"


def test_node_existence_gate_drops_stale_nodes():
    """A cited node no longer in the graph is dropped from lessons entirely."""
    docs = [_doc("useful", ["Alive", "Deleted"]), _doc("useful", ["Alive", "Deleted"])]
    agg = aggregate_lessons(docs, now=_NOW, known_nodes={"Alive"})
    names = [e["node"] for e in agg["preferred"] + agg["tentative"] + agg["contested"]]
    assert "Deleted" not in names
    assert "Alive" in names


def test_corroboration_counts_distinct_docs_not_citations():
    """A node cited twice *within one doc* counts as ONE corroborating result, so it
    stays tentative under k=2 — guards the dict.fromkeys per-doc dedup."""
    agg = aggregate_lessons([_doc("useful", ["A", "A"])], now=_NOW, min_corroboration=2)
    assert agg["preferred"] == []
    assert [e["node"] for e in agg["tentative"]] == ["A"]
    assert agg["tentative"][0]["n"] == 1


def test_min_corroboration_is_honored_not_hardcoded():
    """Two distinct useful results -> preferred at k=2, but only tentative at k=3."""
    docs = [_doc("useful", ["A"]), _doc("useful", ["A"])]
    assert [e["node"] for e in aggregate_lessons(docs, now=_NOW, min_corroboration=2)["preferred"]] == ["A"]
    at_k3 = aggregate_lessons(docs, now=_NOW, min_corroboration=3)
    assert at_k3["preferred"] == []
    assert [e["node"] for e in at_k3["tentative"]] == ["A"]


def test_half_life_actually_feeds_decay():
    """Two stale useful + one fresh dead_end: a long half-life (≈no decay) lets the 2
    useful win; a short half-life lets the fresh dead end win. Proves the flag feeds
    the decay, not just the default."""
    docs = [
        _doc("useful", ["N"], date=_days_before(90)),
        _doc("useful", ["N"], date=_days_before(90)),
        _doc("dead_end", ["N"], date=_days_before(1)),
    ]
    long_hl = aggregate_lessons(docs, now=_NOW, half_life_days=100000)
    short_hl = aggregate_lessons(docs, now=_NOW, half_life_days=10)
    assert long_hl["contested"][0]["verdict"] == "useful"
    assert short_hl["contested"][0]["verdict"] == "dead end"


def test_evenly_split_verdict_when_signals_cancel():
    """A same-date useful + dead_end on one node cancel to score 0 -> 'evenly split'."""
    day = _days_before(5)
    agg = aggregate_lessons(
        [_doc("useful", ["N"], date=day), _doc("dead_end", ["N"], date=day)], now=_NOW)
    assert agg["contested"][0]["verdict"] == "even"
    assert "evenly split" in render_lessons_md(agg)


def test_nonpositive_half_life_disables_decay():
    """half_life<=0 turns decay off (full weight), so a stale useful and a fresh
    dead_end weigh equally and cancel."""
    docs = [_doc("useful", ["N"], date=_days_before(365)),
            _doc("dead_end", ["N"], date=_days_before(1))]
    agg = aggregate_lessons(docs, now=_NOW, half_life_days=0)
    assert agg["contested"][0]["verdict"] == "even"


def test_negative_only_node_absent_from_sources():
    """A node seen only in dead_end docs never appears as a source bucket entry, but
    its dead-end question still renders."""
    agg = aggregate_lessons([_doc("dead_end", ["Bad"], question="why?")], now=_NOW)
    names = [e["node"] for e in agg["preferred"] + agg["tentative"] + agg["contested"]]
    assert "Bad" not in names
    assert agg["dead_ends"][0]["nodes"] == ["Bad"]


def test_dead_ends_and_corrections_collected():
    docs = [
        _doc("dead_end", ["RedisClient"], question="where is the cache?"),
        _doc("corrected", question="what hashes pw?", correction="bcrypt"),
    ]
    agg = aggregate_lessons(docs)
    assert agg["dead_ends"][0]["question"] == "where is the cache?"
    assert agg["dead_ends"][0]["nodes"] == ["RedisClient"]
    assert agg["corrections"][0]["correction"] == "bcrypt"


def test_dead_ends_and_corrections_follow_doc_order(tmp_path):
    """dead_ends/corrections are appended in doc order, so their determinism rides on
    load_memory_docs' (date, filename) sort — assert that, not just their presence."""
    mem = tmp_path / "memory"
    _write_raw_doc(mem, "later.md", "2026-02-01", outcome="dead_end", question="second")
    _write_raw_doc(mem, "earlier.md", "2026-01-01", outcome="dead_end", question="first")
    agg = aggregate_lessons(load_memory_docs(mem))
    assert [d["question"] for d in agg["dead_ends"]] == ["first", "second"]


def test_no_community_grouping_without_graph():
    agg = aggregate_lessons([_doc("useful", ["A"])])
    assert agg["by_community"] == {}


def test_doc_community_tie_breaks_to_smallest_label():
    """A doc whose source nodes split evenly across communities lands in the
    lexicographically-smallest one — deterministically, regardless of node order."""
    nc = {"x": "Zeta", "y": "Alpha"}
    agg1 = aggregate_lessons([_doc("useful", ["x", "y"])], nc)
    agg2 = aggregate_lessons([_doc("useful", ["y", "x"])], nc)
    assert "Alpha" in agg1["by_community"] and "Zeta" not in agg1["by_community"]
    assert agg1["by_community"].keys() == agg2["by_community"].keys()


def test_community_grouping_uses_plurality_community():
    node_community = {"A": "Auth", "B": "Auth", "C": "Cache"}
    docs = [
        _doc("useful", ["A", "B", "C"]),  # plurality Auth (2 vs 1)
        _doc("dead_end", ["C"]),          # Cache
        _doc("useful", ["Z"]),            # unknown node -> Uncategorized
    ]
    agg = aggregate_lessons(docs, node_community)
    assert set(agg["by_community"]) == {"Auth", "Cache", "Uncategorized"}
    assert agg["by_community"]["Auth"]["counts"]["useful"] == 1
    assert agg["by_community"]["Cache"]["counts"]["dead_end"] == 1
    assert agg["by_community"]["Uncategorized"]["counts"]["useful"] == 1


# --- rendering -----------------------------------------------------------------


def test_render_is_deterministic():
    docs = [_doc("useful", ["A", "B"]), _doc("dead_end", ["C"], question="dead?")]
    agg = aggregate_lessons(docs)
    assert render_lessons_md(agg) == render_lessons_md(agg)


def test_render_has_summary_and_sections():
    docs = [
        _doc("useful", ["AuthMiddleware"]),
        _doc("dead_end", ["RedisClient"], question="where is the cache?"),
        _doc("corrected", question="pw?", correction="bcrypt"),
    ]
    md = render_lessons_md(aggregate_lessons(docs))
    assert "# Lessons" in md
    assert "1 useful · 1 dead ends · 1 corrected" in md
    assert "`AuthMiddleware`" in md
    assert "where is the cache?" in md
    assert "bcrypt" in md
    # No graph -> no per-topic section.
    assert "## By topic" not in md


def test_render_includes_by_topic_when_graph_present():
    node_community = {"A": "Auth"}
    md = render_lessons_md(aggregate_lessons([_doc("useful", ["A"])], node_community))
    assert "## By topic" in md
    assert "### Auth" in md


def test_topic_sections_alpha_with_uncategorized_last():
    """Topic headers render alphabetically, with Uncategorized always last."""
    nc = {"a": "Zeta", "b": "Alpha"}
    docs = [_doc("useful", ["a"]), _doc("useful", ["b"]), _doc("useful", ["unknown"])]
    md = render_lessons_md(aggregate_lessons(docs, nc))
    headers = [line[4:] for line in md.splitlines() if line.startswith("### ")]
    assert headers == ["Alpha", "Zeta", "Uncategorized"]


def test_render_byte_stable_across_independent_aggregations(tmp_path):
    """The headline guarantee: identical memory/ contents + same `now` -> byte-identical
    output, built from scratch twice (not just render(agg)==render(agg))."""
    mem = tmp_path / "memory"
    _write_raw_doc(mem, "a.md", "2026-01-01", outcome="useful", nodes=["A", "B"])
    _write_raw_doc(mem, "b.md", "2026-01-02", outcome="dead_end", question="dead?")
    first = render_lessons_md(aggregate_lessons(load_memory_docs(mem), now=_NOW))
    second = render_lessons_md(aggregate_lessons(load_memory_docs(mem), now=_NOW))
    assert first == second


def test_contested_node_renders_once_under_contested():
    """A mixed-signal node appears in a single Contested line, not silently in both
    a positive bucket and elsewhere."""
    docs = [_doc("useful", ["N"]), _doc("dead_end", ["N"], question="bad?")]
    md = render_lessons_md(aggregate_lessons(docs, now=_NOW))
    assert "**Contested**" in md
    # Exactly one rendered line carries the node as a contested source.
    contested_lines = [l for l in md.splitlines()
                       if l.startswith("- `N` —") and "useful" in l and "dead end" in l]
    assert len(contested_lines) == 1


def test_header_is_cautious():
    """The header nudges verification, not blind reuse."""
    md = render_lessons_md(aggregate_lessons([_doc("useful", ["A"])], now=_NOW))
    assert "verify before relying" in md
    assert "reuse what worked" not in md


def test_lessons_artifact_cannot_be_globbed_back_into_memory(tmp_path):
    """Regression guard: the LESSONS.md output must never be re-ingested as a memory
    doc. It has no frontmatter, so parse_memory_doc rejects it and load_memory_docs
    skips it even if it lands inside memory/."""
    md = render_lessons_md(aggregate_lessons([_doc("useful", ["A"])], now=_NOW))
    assert parse_memory_doc(md) is None
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "LESSONS.md").write_text(md, encoding="utf-8")
    save_query_result("real", "a", mem, outcome="useful")
    docs = load_memory_docs(mem)
    assert len(docs) == 1 and docs[0]["question"] == "real"


def test_render_empty_memory_is_graceful():
    md = render_lessons_md(aggregate_lessons([], now=_NOW))
    assert "from 0 session memories" in md
    assert "_No marked outcomes yet._" in md


# --- orchestrator + CLI --------------------------------------------------------


def test_reflect_writes_lessons_file(tmp_path):
    mem = tmp_path / "memory"
    save_query_result("q1", "a1", mem, source_nodes=["A"], outcome="useful")
    out_path, agg = reflect(mem, tmp_path / "reflections" / "LESSONS.md")
    assert out_path.exists()
    assert agg["total"] == 1
    assert "`A`" in out_path.read_text(encoding="utf-8")


def test_second_session_benefits_from_the_first(tmp_path):
    """The issue's worked example: session 1 records a win and a dead end; session 2
    loads LESSONS.md and sees both."""
    out = tmp_path / "graphify-out"
    mem = out / "memory"

    # Session 1: one useful answer, one dead end.
    save_query_result(
        "how does auth work?", "JWT in middleware", mem,
        source_nodes=["AuthMiddleware"], outcome="useful",
    )
    save_query_result(
        "where is the cache?", "looked at RedisClient, not it", mem,
        source_nodes=["RedisClient"], outcome="dead_end",
    )

    # End of session 1 -> reflect.
    lessons = out / "reflections" / "LESSONS.md"
    reflect(mem, lessons)

    # Session 2 loads the lessons doc.
    body = lessons.read_text(encoding="utf-8")
    assert "`AuthMiddleware`" in body          # start here next time
    assert "where is the cache?" in body       # don't re-derive this dead end


def test_cli_reflect_end_to_end(tmp_path):
    cwd = tmp_path
    r1 = _run(["save-result", "--question", "how does auth work?",
               "--answer", "JWT", "--nodes", "AuthMiddleware",
               "--outcome", "useful"], cwd)
    assert r1.returncode == 0, r1.stderr
    r2 = _run(["reflect"], cwd)
    assert r2.returncode == 0, r2.stderr
    assert "Reflected 1 memories" in r2.stdout
    lessons = cwd / "graphify-out" / "reflections" / "LESSONS.md"
    assert lessons.exists()
    assert "`AuthMiddleware`" in lessons.read_text(encoding="utf-8")


def test_cli_save_result_rejects_bad_outcome(tmp_path):
    """argparse `choices` rejects an unknown outcome before save_query_result runs."""
    r = _run(["save-result", "--question", "q", "--answer", "a",
              "--outcome", "great"], tmp_path)
    assert r.returncode != 0
    assert "great" in (r.stderr + r.stdout)


def test_cli_save_result_reads_answer_from_file(tmp_path):
    """--answer-file lets callers pass a long/multiline answer via a file instead
    of a fragile inline arg (Windows/PowerShell quoting), #1502."""
    ans = tmp_path / "answer.txt"
    ans.write_text("line one\nline two with a \"quote\"\n", encoding="utf-8")
    r = _run(["save-result", "--question", "how does auth work?",
              "--answer-file", str(ans), "--outcome", "useful"], tmp_path)
    assert r.returncode == 0, r.stderr
    docs = list((tmp_path / "graphify-out" / "memory").glob("*.md"))
    assert docs, "save-result wrote no memory doc"
    body = docs[0].read_text(encoding="utf-8")
    assert "line one" in body and "line two" in body


def test_cli_save_result_requires_answer_or_answer_file(tmp_path):
    """Neither --answer nor --answer-file -> clean argparse error, not a crash."""
    r = _run(["save-result", "--question", "q", "--outcome", "useful"], tmp_path)
    assert r.returncode != 0
    assert "--answer" in (r.stderr + r.stdout)


def test_cli_reflect_cold_start_writes_empty_lessons(tmp_path):
    """First run with no graphify-out/memory/ still succeeds and writes a valid doc."""
    r = _run(["reflect"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Reflected 0 memories" in r.stdout
    lessons = tmp_path / "graphify-out" / "reflections" / "LESSONS.md"
    assert lessons.exists()
    assert "from 0 session memories" in lessons.read_text(encoding="utf-8")


def test_cli_reflect_respects_out_flag(tmp_path):
    cwd = tmp_path
    _run(["save-result", "--question", "q", "--answer", "a",
          "--outcome", "useful", "--nodes", "X"], cwd)
    dest = cwd / "custom" / "lessons.md"
    r = _run(["reflect", "--out", str(dest)], cwd)
    assert r.returncode == 0, r.stderr
    assert dest.exists()


def test_cli_reflect_groups_by_community_when_graph_present(tmp_path):
    """With a real graph.json present, reflect auto-detects it and groups lessons
    under the community of the cited node — including when the node is cited by its
    LABEL (what save-result records), not its id (regression guard: keying community
    lookup on ids alone collapsed every lesson into Uncategorized)."""
    out = _make_graph(tmp_path)
    graph = json.loads((out / "graph.json").read_text())
    node_label = graph["nodes"][0]["label"]

    _run(["save-result", "--question", "q", "--answer", "a",
          "--nodes", node_label, "--outcome", "useful"], tmp_path)
    r = _run(["reflect"], tmp_path)
    assert r.returncode == 0, r.stderr
    body = (out / "reflections" / "LESSONS.md").read_text(encoding="utf-8")
    assert "## By topic" in body
    # The label-cited node must land in a real community, not Uncategorized.
    assert "### Uncategorized" not in body


def test_cli_node_existence_gate_drops_stale_node_end_to_end(tmp_path):
    """Through reflect()/CLI with a real graph.json: a cited node that isn't in the
    graph is dropped from LESSONS.md; a real one stays. Exercises _load_known_nodes
    + the wiring, not just the known_nodes param."""
    out = _make_graph(tmp_path)
    # Cite the node by its LABEL — what an agent/`save-result` actually records —
    # not its id. The gate must match labels too, else every real citation is
    # silently dropped whenever a graph is present (regression guard).
    real = json.loads((out / "graph.json").read_text())["nodes"][0]["label"]

    _run(["save-result", "--question", "q", "--answer", "a",
          "--nodes", real, "GhostNode", "--outcome", "useful"], tmp_path)
    r = _run(["reflect"], tmp_path)
    assert r.returncode == 0, r.stderr
    body = (out / "reflections" / "LESSONS.md").read_text(encoding="utf-8")
    assert "GhostNode" not in body
    assert f"`{real}`" in body


def _make_graph(tmp_path: Path) -> Path:
    """Build a minimal graph.json + analysis/labels in tmp_path/graphify-out/.

    Mirrors tests/test_cli_export.py::_make_graph so reflect can be exercised with a
    real community structure.
    """
    out = tmp_path / "graphify-out"
    out.mkdir()
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.export import to_json

    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    to_json(G, communities, str(out / "graph.json"))
    (out / ".graphify_analysis.json").write_text(json.dumps({
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods, "surprises": surprises,
    }))
    (out / ".graphify_labels.json").write_text(
        json.dumps({str(cid): f"Community {cid}" for cid in communities})
    )
    return out


# --- lessons_fresh / `reflect --if-stale` -------------------------------------

def test_lessons_fresh_missing_output_is_not_fresh(tmp_path):
    mem = tmp_path / "memory"; mem.mkdir()
    (mem / "q.md").write_text("x", encoding="utf-8")
    assert lessons_fresh(tmp_path / "LESSONS.md", mem) is False  # must build


def test_lessons_fresh_true_when_output_newer_than_inputs(tmp_path):
    import os
    mem = tmp_path / "memory"; mem.mkdir()
    doc = mem / "q.md"; doc.write_text("x", encoding="utf-8")
    out = tmp_path / "LESSONS.md"; out.write_text("y", encoding="utf-8")
    os.utime(doc, (1000, 1000))
    os.utime(out, (2000, 2000))
    assert lessons_fresh(out, mem) is True


def test_lessons_fresh_false_when_memory_newer(tmp_path):
    import os
    mem = tmp_path / "memory"; mem.mkdir()
    doc = mem / "q.md"; doc.write_text("x", encoding="utf-8")
    out = tmp_path / "LESSONS.md"; out.write_text("y", encoding="utf-8")
    os.utime(out, (1000, 1000))
    os.utime(doc, (2000, 2000))  # a new outcome was saved after the last reflect
    assert lessons_fresh(out, mem) is False


def test_lessons_fresh_false_when_graph_newer(tmp_path):
    import os
    mem = tmp_path / "memory"; mem.mkdir()
    (mem / "q.md").write_text("x", encoding="utf-8")
    out = tmp_path / "LESSONS.md"; out.write_text("y", encoding="utf-8")
    graph = tmp_path / "graph.json"; graph.write_text("{}", encoding="utf-8")
    os.utime(mem / "q.md", (1000, 1000))
    os.utime(out, (1500, 1500))
    os.utime(graph, (2000, 2000))  # graph rebuilt since last reflect -> stale
    assert lessons_fresh(out, mem, graph) is False


@pytest.mark.parametrize("sidecar_name", [".graphify_analysis.json", ".graphify_labels.json"])
def test_lessons_fresh_false_when_graph_sidecar_newer(tmp_path, sidecar_name):
    import os
    mem = tmp_path / "memory"; mem.mkdir()
    (mem / "q.md").write_text("x", encoding="utf-8")
    out = tmp_path / "LESSONS.md"; out.write_text("y", encoding="utf-8")
    graph = tmp_path / "graph.json"; graph.write_text("{}", encoding="utf-8")
    analysis = tmp_path / ".graphify_analysis.json"; analysis.write_text("{}", encoding="utf-8")
    labels = tmp_path / ".graphify_labels.json"; labels.write_text("{}", encoding="utf-8")
    for p in [mem / "q.md", graph, analysis, labels]:
        os.utime(p, (1000, 1000))
    os.utime(out, (1500, 1500))
    os.utime(tmp_path / sidecar_name, (2000, 2000))
    assert lessons_fresh(out, mem, graph, analysis, labels) is False


def test_cli_reflect_if_stale_skips_when_fresh(tmp_path):
    """`reflect --if-stale` skips the rebuild when LESSONS.md is already current,
    and still runs when a new outcome arrives."""
    out = _make_graph(tmp_path)
    real = json.loads((out / "graph.json").read_text())["nodes"][0]["label"]
    _run(["save-result", "--question", "q", "--answer", "a",
          "--nodes", real, "--outcome", "useful"], tmp_path)
    first = _run(["reflect"], tmp_path)
    assert first.returncode == 0
    lessons = out / "reflections" / "LESSONS.md"
    body_before = lessons.read_text(encoding="utf-8")

    # Second call with --if-stale: nothing changed -> skipped, file untouched.
    skipped = _run(["reflect", "--if-stale"], tmp_path)
    assert skipped.returncode == 0
    assert "up to date" in (skipped.stdout + skipped.stderr).lower()
    assert lessons.read_text(encoding="utf-8") == body_before

    # A new outcome makes it stale -> --if-stale runs again.
    _run(["save-result", "--question", "q2", "--answer", "a",
          "--nodes", real, "--outcome", "useful"], tmp_path)
    ran = _run(["reflect", "--if-stale"], tmp_path)
    assert ran.returncode == 0
    assert "up to date" not in (ran.stdout + ran.stderr).lower()


def test_cli_reflect_if_stale_reruns_when_labels_newer(tmp_path):
    """A label refresh changes LESSONS.md topic headings, so --if-stale must rebuild."""
    out = _make_graph(tmp_path)
    graph_data = json.loads((out / "graph.json").read_text())
    node = graph_data["nodes"][0]
    real = node["label"]
    community = str(node["community"])
    _run(["save-result", "--question", "q", "--answer", "a",
          "--nodes", real, "--outcome", "useful"], tmp_path)
    first = _run(["reflect"], tmp_path)
    assert first.returncode == 0, first.stderr

    lessons = out / "reflections" / "LESSONS.md"
    labels_path = out / ".graphify_labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels[community] = "Renamed Topic"
    labels_path.write_text(json.dumps(labels), encoding="utf-8")

    import os
    os.utime(lessons, (1500, 1500))
    os.utime(labels_path, (2000, 2000))
    ran = _run(["reflect", "--if-stale"], tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert "up to date" not in (ran.stdout + ran.stderr).lower()
    assert "### Renamed Topic" in lessons.read_text(encoding="utf-8")


def test_dead_ends_and_corrections_dedupe_by_question():
    """Saving the same Q&A more than once must not duplicate lines in the dead-ends
    / corrections lists; for a re-corrected question the most recent text wins."""
    docs = [
        _doc("dead_end", question="ws server?", date="2026-01-01"),
        _doc("dead_end", question="ws server?", date="2026-01-02"),   # duplicate
        _doc("corrected", question="hash?", correction="SHA-1", date="2026-01-01"),
        _doc("corrected", question="hash?", correction="SHA-256", date="2026-01-03"),  # newer
    ]
    agg = aggregate_lessons(docs, now=_NOW)
    assert [d["question"] for d in agg["dead_ends"]] == ["ws server?"]
    assert len(agg["corrections"]) == 1
    assert agg["corrections"][0]["correction"] == "SHA-256"  # recency wins


# --- work-memory overlay sidecar (.graphify_learning.json) --------------------
#
# The sidecar is a DERIVED experiential layer written next to graph.json; the
# durable structural truth in graph.json is never stamped with learning_* fields.
# It projects the reflect aggregate (preferred/tentative/contested) into a
# per-node-id map with a code fingerprint for staleness and a provenance trail.

from graphify.reflect import (  # noqa: E402
    LEARNING_SIDECAR_NAME,
    build_learning_overlay,
    load_learning_overlay,
    write_learning_sidecar,
)


def _overlay_graph(out: Path, nodes: list[dict]) -> None:
    """Write a minimal graph.json under ``out`` with the given node dicts."""
    out.mkdir(parents=True, exist_ok=True)
    graph = {"directed": True, "multigraph": False, "graph": {},
             "nodes": nodes, "links": []}
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _overlay_corpus(mem: Path) -> None:
    """A corpus with: a PREFERRED node (2 useful), a TENTATIVE node (1 useful),
    a CONTESTED node (useful + dead_end), and a DEAD-END-ONLY node."""
    _write_raw_doc(mem, "p1.md", "2026-05-01", outcome="useful",
                   question="how do I auth?", nodes=["login()"])
    _write_raw_doc(mem, "p2.md", "2026-05-10", outcome="useful",
                   question="auth again", nodes=["login()"])
    _write_raw_doc(mem, "t1.md", "2026-05-02", outcome="useful",
                   question="cache?", nodes=["RedisClient"])
    _write_raw_doc(mem, "c1.md", "2026-05-03", outcome="useful",
                   question="contested useful", nodes=["Contested"])
    _write_raw_doc(mem, "c2.md", "2026-05-04", outcome="dead_end",
                   question="contested dead", nodes=["Contested"])
    _write_raw_doc(mem, "d1.md", "2026-05-05", outcome="dead_end",
                   question="led nowhere", nodes=["DeadEnd"])


def test_sidecar_write_classifies_and_keys_by_canonical_id(tmp_path):
    """reflect with a graph writes .graphify_learning.json next to graph.json with
    the preferred/tentative/contested nodes keyed by canonical node id; the
    dead-end-only node is NOT present; score/uses/provenance are carried."""
    out = tmp_path / "graphify-out"
    src = tmp_path / "auth.py"
    src.write_text("def login(): pass\n", encoding="utf-8")
    _overlay_graph(out, [
        {"id": "auth_login", "label": "login()", "source_file": str(src), "community": 0},
        {"id": "redis_client", "label": "RedisClient", "source_file": "", "community": 0},
        {"id": "contested_node", "label": "Contested", "source_file": "", "community": 0},
        {"id": "deadend_node", "label": "DeadEnd", "source_file": "", "community": 0},
    ])
    mem = out / "memory"
    _overlay_corpus(mem)

    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    sidecar = json.loads((out / LEARNING_SIDECAR_NAME).read_text(encoding="utf-8"))

    assert sidecar["version"] == 1
    assert sidecar["generated_at"] == _NOW.isoformat()
    nodes = sidecar["nodes"]
    # Keyed by canonical node id, not label.
    assert nodes["auth_login"]["status"] == "preferred"
    assert nodes["auth_login"]["uses"] == 2
    assert nodes["auth_login"]["label"] == "login()"
    assert isinstance(nodes["auth_login"]["score"], float)
    assert nodes["auth_login"]["provenance"]  # captured during aggregation
    assert nodes["redis_client"]["status"] == "tentative"
    assert nodes["contested_node"]["status"] == "contested"
    assert nodes["contested_node"]["verdict"] in ("useful", "dead end", "even")
    # Dead-end-only node stays query-scoped — never in the overlay.
    assert "deadend_node" not in nodes
    # And learning_* is NOT stamped into graph.json (durable truth untouched).
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    for n in graph["nodes"]:
        assert not any(k.startswith("learning") for k in n)


def test_sidecar_is_byte_identical_across_runs(tmp_path):
    """Two reflect runs on identical input + fixed `now` produce a byte-identical
    sidecar (sorted keys, stable indent)."""
    out = tmp_path / "graphify-out"
    src = tmp_path / "auth.py"
    src.write_text("def login(): pass\n", encoding="utf-8")
    _overlay_graph(out, [
        {"id": "auth_login", "label": "login()", "source_file": str(src), "community": 0},
    ])
    mem = out / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["login()"])
    _write_raw_doc(mem, "b.md", "2026-05-10", outcome="useful", nodes=["login()"])

    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    first = (out / LEARNING_SIDECAR_NAME).read_bytes()
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    second = (out / LEARNING_SIDECAR_NAME).read_bytes()
    assert first == second


def test_loader_marks_entry_stale_when_source_file_changes(tmp_path):
    """load_learning_overlay recomputes the file fingerprint: unchanged source =>
    stale=False; an edit to that source => stale=True."""
    out = tmp_path / "graphify-out"
    src = tmp_path / "auth.py"
    src.write_text("def login(): pass\n", encoding="utf-8")
    _overlay_graph(out, [
        {"id": "auth_login", "label": "login()", "source_file": str(src), "community": 0},
    ])
    mem = out / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["login()"])
    _write_raw_doc(mem, "b.md", "2026-05-10", outcome="useful", nodes=["login()"])
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)

    fresh = load_learning_overlay(out / "graph.json")
    assert fresh["auth_login"]["stale"] is False

    src.write_text("def login(): return 1  # changed\n", encoding="utf-8")
    after = load_learning_overlay(out / "graph.json")
    assert after["auth_login"]["stale"] is True


def test_relative_source_file_not_spuriously_stale_in_graphify_out_layout(tmp_path):
    """Regression: with a RELATIVE source_file and graph.json under graphify-out/,
    a freshly-written verdict must NOT be flagged stale. The fingerprint resolves
    the file relative to the PROJECT root (tmp_path), not graph.json's own dir
    (graphify-out/) — otherwise every node looked unfindable and was marked stale.
    The edit case must still flip stale=True."""
    out = tmp_path / "graphify-out"          # graph.json lives here
    (tmp_path / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    _overlay_graph(out, [
        # source_file is RELATIVE to the project root (tmp_path), as `extract` writes it
        {"id": "auth_login", "label": "login()", "source_file": "auth.py", "community": 0},
    ])
    mem = out / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["login()"])
    _write_raw_doc(mem, "b.md", "2026-05-10", outcome="useful", nodes=["login()"])
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)

    fresh = load_learning_overlay(out / "graph.json")
    assert fresh["auth_login"]["status"] == "preferred"
    assert fresh["auth_login"]["stale"] is False  # the bug: was spuriously True

    (tmp_path / "auth.py").write_text("def login(): return 1  # changed\n", encoding="utf-8")
    assert load_learning_overlay(out / "graph.json")["auth_login"]["stale"] is True


def test_relative_source_file_resolved_via_graphify_root_marker(tmp_path):
    """When a committed .graphify_root marker records the project root (e.g. a
    GRAPHIFY_OUT override pointing the output dir elsewhere), the fingerprint
    resolves source_file against that root, not graph.json's own dir."""
    proj = tmp_path / "project"
    proj.mkdir()
    (proj / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    out = tmp_path / "elsewhere-out"          # output dir NOT under the project
    _overlay_graph(out, [
        {"id": "auth_login", "label": "login()", "source_file": "auth.py", "community": 0},
    ])
    (out / ".graphify_root").write_text(str(proj), encoding="utf-8")  # the marker
    mem = out / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["login()"])
    _write_raw_doc(mem, "b.md", "2026-05-10", outcome="useful", nodes=["login()"])
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    assert load_learning_overlay(out / "graph.json")["auth_login"]["stale"] is False


def test_flat_layout_does_not_match_same_named_file_one_dir_up(tmp_path):
    """In a flat layout (graph.json at the project root), the resolver must use the
    graph's own dir, not its parent — otherwise a same-named file one level up
    would be fingerprinted instead, producing a wrong staleness verdict."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "util.py").write_text("REAL = 1\n", encoding="utf-8")
    # A decoy same-named file in the parent dir (tmp_path / util.py).
    (tmp_path / "util.py").write_text("DECOY = 2\n", encoding="utf-8")
    # Flat layout: graph.json sits directly in proj/ (not a graphify-out subdir).
    proj.joinpath("graph.json").write_text(json.dumps({
        "nodes": [{"id": "util", "label": "util.py", "source_file": "util.py",
                   "source_location": "L1", "community": 0}],
        "links": [],
    }), encoding="utf-8")
    mem = proj / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["util.py"])
    _write_raw_doc(mem, "b.md", "2026-05-10", outcome="useful", nodes=["util.py"])
    reflect(mem, proj / "reflections" / "LESSONS.md",
            graph_path=proj / "graph.json", now=_NOW)
    # Not stale on a clean build...
    assert load_learning_overlay(proj / "graph.json")["util"]["stale"] is False
    # ...and editing the REAL file (proj/util.py) flips it, while editing the
    # decoy (parent) does not — proving the resolver bound to the right file.
    (tmp_path / "util.py").write_text("DECOY = 999\n", encoding="utf-8")
    assert load_learning_overlay(proj / "graph.json")["util"]["stale"] is False
    (proj / "util.py").write_text("REAL = 999\n", encoding="utf-8")
    assert load_learning_overlay(proj / "graph.json")["util"]["stale"] is True


def test_provenance_capped_to_five_most_recent(tmp_path):
    """A node cited by >5 useful results keeps exactly the 5 most-recent in
    provenance (recent-first)."""
    out = tmp_path / "graphify-out"
    src = tmp_path / "auth.py"
    src.write_text("x\n", encoding="utf-8")
    _overlay_graph(out, [
        {"id": "auth_login", "label": "login()", "source_file": str(src), "community": 0},
    ])
    mem = out / "memory"
    for i in range(7):
        _write_raw_doc(mem, f"u{i}.md", f"2026-05-{10 + i:02d}",
                       outcome="useful", question=f"q{i}", nodes=["login()"])
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    sidecar = json.loads((out / LEARNING_SIDECAR_NAME).read_text(encoding="utf-8"))
    prov = sidecar["nodes"]["auth_login"]["provenance"]
    assert len(prov) == 5
    # Most-recent first.
    assert prov[0]["date"] == "2026-05-16"
    assert prov[-1]["date"] == "2026-05-12"


def test_ambiguous_or_unresolved_citation_is_skipped(tmp_path):
    """A label shared by >1 node id (ambiguous) or absent from the graph
    (unresolved) is skipped — it can't be displayed against a single node."""
    out = tmp_path / "graphify-out"
    _overlay_graph(out, [
        {"id": "dup_a", "label": "Dup", "source_file": "", "community": 0},
        {"id": "dup_b", "label": "Dup", "source_file": "", "community": 0},
        {"id": "solo", "label": "Solo", "source_file": "", "community": 0},
    ])
    mem = out / "memory"
    _write_raw_doc(mem, "a.md", "2026-05-01", outcome="useful", nodes=["Dup"])
    _write_raw_doc(mem, "b.md", "2026-05-02", outcome="useful", nodes=["Dup"])
    _write_raw_doc(mem, "c.md", "2026-05-03", outcome="useful", nodes=["Solo"])
    _write_raw_doc(mem, "d.md", "2026-05-04", outcome="useful", nodes=["Solo"])
    reflect(mem, out / "reflections" / "LESSONS.md",
            graph_path=out / "graph.json", now=_NOW)
    nodes = json.loads((out / LEARNING_SIDECAR_NAME).read_text(encoding="utf-8"))["nodes"]
    # Ambiguous "Dup" skipped; only the unambiguous "Solo" survives.
    assert "dup_a" not in nodes and "dup_b" not in nodes
    assert "solo" in nodes
