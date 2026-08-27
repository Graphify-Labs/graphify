"""Regression tests for `graphify explain` arrow direction (#853)."""
from __future__ import annotations
import json
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts", "community": 0},
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts", "community": 0},
            {"id": "create_edit", "label": "createEditHandler()",
             "source_file": "server/create-edit-handler.ts", "community": 0},
            {"id": "stable_stringify", "label": "stableStringify()",
             "source_file": "shared/stringify.ts", "community": 0},
        ],
        "links": [
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "create_edit", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "validate", "target": "stable_stringify",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_as_inbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out
    assert "--> createPatchHandler() [calls]" not in out
    assert "--> createEditHandler() [calls]" not in out


def test_caller_shows_callee_as_outbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", capsys)
    assert "--> validateSanitySession() [calls]" in out
    assert "<-- " not in out


def test_explain_source_file_path_prefers_file_level_node(monkeypatch, tmp_path, capsys):
    source_file = "app/api/example/route.ts"
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "example_route_get", "label": "GET()",
             "source_file": source_file, "source_location": "L42", "community": 0},
            {"id": "example_route", "label": "route.ts",
             "source_file": source_file, "source_location": "L1", "community": 0},
        ],
        "links": [
            {"source": "example_route", "target": "example_route_get",
             "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))

    out = _run(monkeypatch, p, source_file, capsys)

    assert "Node: route.ts" in out
    assert "ID:        example_route" in out
    assert f"Source:    {source_file} L1" in out
    assert "Node: GET()" not in out


# --- work-memory overlay Lesson line ------------------------------------------

def _write_sidecar(tmp_path, nodes):
    (tmp_path / ".graphify_learning.json").write_text(
        json.dumps({"version": 1, "generated_at": "2026-06-01T00:00:00+00:00",
                    "nodes": nodes}),
        encoding="utf-8",
    )


def test_explain_shows_preferred_lesson_line(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    _write_sidecar(tmp_path, {
        "validate": {"status": "preferred", "score": 2.4, "uses": 3,
                     "label": "validateSanitySession()", "source_file": "",
                     "code_fingerprint": "", "provenance": []},
    })
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson: preferred source (start here) — 3 useful, score=2.4" in out
    assert "code changed" not in out


def test_explain_shows_contested_and_stale_lesson(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    # source_file points at a path that does not exist -> loader marks it stale.
    _write_sidecar(tmp_path, {
        "validate": {"status": "contested", "score": -0.1, "uses": 2, "neg": 1,
                     "verdict": "dead end", "label": "validateSanitySession()",
                     "source_file": "server/sanity-validate-session.ts",
                     "code_fingerprint": "deadbeef", "provenance": []},
    })
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson: contested (useful 2 / dead-end 1)" in out
    assert "[code changed since — re-verify]" in out


def test_explain_no_lesson_line_for_unannotated_node(monkeypatch, tmp_path, capsys):
    """No sidecar => no Lesson line; output identical to pre-feature."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson:" not in out


def test_explain_connection_shows_call_site_line(monkeypatch, tmp_path, capsys):
    """BUG1: an explain connection shows the edge's call-SITE line (in the
    caller's file), not the caller's def line."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "loader", "label": "load_state()",
             "source_file": "apollo.py", "source_location": "L90", "community": 0},
            {"id": "trans", "label": "transition_state()",
             "source_file": "state.py", "source_location": "L56", "community": 0},
        ],
        "links": [
            {"source": "loader", "target": "trans", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "apollo.py", "source_location": "L158"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    out = _run(monkeypatch, p, "transition_state", capsys)
    # The inbound caller line must cite the call site apollo.py:L158.
    caller_line = next(l for l in out.splitlines() if "<-- load_state()" in l)
    assert "apollo.py:L158" in caller_line, f"call site missing from: {caller_line!r}"
    assert "apollo.py:L90" not in caller_line  # never the caller's def line
    # The queried node's own header still shows its def line (correct).
    assert "state.py" in out and "L56" in out


# --- #2009: high-degree nodes must not silently hide the cut connections ------

def _write_high_degree_graph(tmp_path, n_callers=30, files=None):
    """A node with n_callers callers, spread across `files` (default: 3
    files, so counts land above 1 per file and truncation kicks in — the
    CLI shows the top 20 by neighbor degree, cutting the rest)."""
    files = files or ["app/handlers/email.py", "app/jobs/retry.py", "lib/workers/queue.py"]
    nodes = [{"id": "hub", "label": "hub()",
              "source_file": "lib/hub.py", "community": 0}]
    links = []
    for i in range(n_callers):
        fpath = files[i % len(files)]
        nid = f"caller_{i}"
        nodes.append({"id": nid, "label": f"caller_{i}()",
                       "source_file": fpath, "community": 0})
        links.append({"source": nid, "target": "hub", "relation": "calls",
                       "confidence": "EXTRACTED", "source_file": fpath,
                       "source_location": f"L{10 + i}"})
    graph_data = {"directed": False, "multigraph": False, "graph": {},
                  "nodes": nodes, "links": links}
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_truncation_notice_present_for_high_degree_node(monkeypatch, tmp_path, capsys):
    """Baseline: the cut count is still announced (pre-existing behavior)."""
    p = _write_high_degree_graph(tmp_path, n_callers=30)
    out = _run(monkeypatch, p, "hub", capsys)
    assert "Connections (30):" in out
    assert "... and 10 more" in out


def test_explain_groups_cut_callers_by_file_instead_of_dropping_them(monkeypatch, tmp_path, capsys):
    """#2009: past the top-20 cutoff, the remaining callers must still be
    accounted for — grouped by file with counts — instead of vanishing
    behind a bare '... and N more'. No caller may be lost silently: the
    per-file counts in the aggregation must sum back to the cut total."""
    p = _write_high_degree_graph(
        tmp_path, n_callers=30,
        files=["app/handlers/email.py", "app/jobs/retry.py", "lib/workers/queue.py"],
    )
    out = _run(monkeypatch, p, "hub", capsys)
    assert "Grouped by file:" in out
    assert "<-- lib/workers/queue.py: 4 connections" in out
    assert "<-- app/handlers/email.py: 3 connections" in out
    assert "<-- app/jobs/retry.py: 3 connections" in out
    # No silent loss: the aggregated counts must sum to the announced cut.
    grouped_lines = [
        l for l in out.splitlines() if l.strip().startswith(("<--", "-->")) and "connection" in l
    ]
    total = sum(int(l.rsplit(":", 1)[1].split()[0]) for l in grouped_lines)
    assert total == 10  # 30 connections - 20 shown = 10 cut, all accounted for


def test_explain_no_grouping_section_when_under_cutoff(monkeypatch, tmp_path, capsys):
    """Regression guard: nodes at or below the 20-connection cutoff keep the
    pre-#2009 output byte-for-byte (no new section, no behavior change)."""
    p = _write_high_degree_graph(tmp_path, n_callers=5)
    out = _run(monkeypatch, p, "hub", capsys)
    assert "Grouped by file:" not in out
    assert "more" not in out


def test_explain_grouping_boundary_at_exactly_21_vs_20_connections(monkeypatch, tmp_path, capsys):
    """Pin the exact `> 20` cutoff itself. The other #2009 tests use 30 and 5
    connections, both comfortably clear of the edge — nothing here fails if a
    future refactor shifts the boundary by one. One node at exactly 21
    connections (one past the cutoff) must show the grouped section with
    exactly one grouped entry; one node at exactly 20 (at the cutoff, not
    past it) must show neither."""
    p21 = _write_high_degree_graph(tmp_path, n_callers=21, files=["lib/only.py"])
    out21 = _run(monkeypatch, p21, "hub", capsys)
    assert "Grouped by file:" in out21
    assert "<-- lib/only.py: 1 connection" in out21
    grouped_lines21 = [
        l for l in out21.splitlines() if l.strip().startswith(("<--", "-->")) and "connection" in l
    ]
    assert len(grouped_lines21) == 1  # exactly one grouped entry, not zero, not more

    p20 = _write_high_degree_graph(tmp_path, n_callers=20, files=["lib/only.py"])
    out20 = _run(monkeypatch, p20, "hub", capsys)
    assert "Grouped by file:" not in out20
    assert "more" not in out20


# --- ambiguous label across files (#explain-ambiguity) -----------------------


def _write_ambiguous_graph(tmp_path, *, reverse: bool = False):
    """Two DIFFERENT symbols that happen to share a label, in different files.

    This is the monorepo shape: each workspace defines its own `MetricsPort`.
    Both land in `_find_node`'s `exact` tier, separated only by iteration order.
    """
    nodes = [
        {"id": "chat_metrics_port", "label": "MetricsPort",
         "source_file": "services/chat/src/application/ports/metrics.port.ts",
         "community": 0},
        {"id": "scraping_metrics_port", "label": "MetricsPort",
         "source_file": "services/scraping/src/application/ports/metrics.port.ts",
         "community": 0},
    ]
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": list(reversed(nodes)) if reverse else nodes,
        "links": [],
    }
    p = tmp_path / ("graph_rev.json" if reverse else "graph.json")
    p.write_text(json.dumps(graph_data))
    return p


def _run_capture(monkeypatch, graph_path, label, capsys):
    """Run explain, returning (stdout, stderr). Ambiguity is reported on stderr."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    try:
        mainmod.main()
    except SystemExit:
        pass
    captured = capsys.readouterr()
    return captured.out, captured.err


def test_explain_ambiguous_label_warns_naming_every_candidate(monkeypatch, tmp_path, capsys):
    """An unresolvable tie must name every candidate and still answer.

    Erroring out instead would make `explain` unusable wherever ambiguity is the
    normal case (worktrees indexed beside their canonical repo), so the contract
    is: warn on stderr, answer on stdout.
    """
    p = _write_ambiguous_graph(tmp_path)
    out, err = _run_capture(monkeypatch, p, "MetricsPort", capsys)
    assert "was ambiguous" in err
    assert "services/chat/src/application/ports/metrics.port.ts" in err
    assert "services/scraping/src/application/ports/metrics.port.ts" in err
    # The answer still comes, and the ambiguity never leaks into stdout.
    assert "Node: MetricsPort" in out
    assert "ambiguous" not in out.lower()


def test_explain_ambiguous_answer_does_not_depend_on_node_order(
    monkeypatch, tmp_path, capsys
):
    """The bug: reversing node order flipped which file was reported as fact."""
    forward_out, forward_err = _run_capture(
        monkeypatch, _write_ambiguous_graph(tmp_path), "MetricsPort", capsys)
    reverse_out, reverse_err = _run_capture(
        monkeypatch, _write_ambiguous_graph(tmp_path, reverse=True), "MetricsPort", capsys)
    # Same node chosen and same alternatives named, regardless of iteration order.
    assert [l for l in forward_out.splitlines() if l.startswith("  ID:")] == \
           [l for l in reverse_out.splitlines() if l.startswith("  ID:")]
    assert sorted(l.strip() for l in forward_err.splitlines() if "metrics.port.ts" in l) == \
           sorted(l.strip() for l in reverse_err.splitlines() if "metrics.port.ts" in l)


# --- cwd tie-break: worktree indexed beside its canonical repo ---------------


def _write_worktree_graph(tmp_path):
    """Same symbol in two sibling TOP-LEVEL dirs: a repo and one of its worktrees.

    The graph is written where a real build puts it (<root>/graphify-out/graph.json)
    so the scan root is derived the same way the CLI derives it.
    """
    out_dir = tmp_path / "graphify-out"
    out_dir.mkdir()
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "canonical", "label": "shared_handler",
             "source_file": "matching/svc.py", "community": 0},
            {"id": "worktree", "label": "shared_handler",
             "source_file": "matching-156294-ga-merge/svc.py", "community": 0},
        ],
        "links": [],
    }
    p = out_dir / "graph.json"
    p.write_text(json.dumps(graph_data))
    for sub in ("matching", "matching-156294-ga-merge"):
        (tmp_path / sub).mkdir()
    return p


def test_explain_prefers_the_top_level_dir_the_caller_is_standing_in(
    monkeypatch, tmp_path, capsys
):
    """Inside a worktree, `explain` must answer about THAT worktree, silently."""
    p = _write_worktree_graph(tmp_path)
    monkeypatch.chdir(tmp_path / "matching-156294-ga-merge")
    out, err = _run_capture(monkeypatch, p, "shared_handler", capsys)
    assert "ID:        worktree" in out
    assert "matching-156294-ga-merge/svc.py" in out
    # cwd resolved it, so there is nothing ambiguous left to report.
    assert "was ambiguous" not in err


def test_explain_cwd_tie_break_picks_the_canonical_repo_from_inside_it(
    monkeypatch, tmp_path, capsys
):
    """Mirror case: the tie-break follows cwd, it does not favour one name."""
    p = _write_worktree_graph(tmp_path)
    monkeypatch.chdir(tmp_path / "matching")
    out, err = _run_capture(monkeypatch, p, "shared_handler", capsys)
    assert "ID:        canonical" in out
    assert "was ambiguous" not in err


def test_explain_warns_when_cwd_is_outside_every_candidate(monkeypatch, tmp_path, capsys):
    """At the scan root, cwd singles out nothing -> warn and still answer."""
    p = _write_worktree_graph(tmp_path)
    monkeypatch.chdir(tmp_path)
    out, err = _run_capture(monkeypatch, p, "shared_handler", capsys)
    assert "was ambiguous" in err
    assert "matching/svc.py" in err
    assert "Node: shared_handler" in out


def test_explain_matches_within_one_file_are_not_ambiguous(monkeypatch, tmp_path, capsys):
    """A file node plus its members is ordinary precedence, not a tie."""
    source_file = "services/chat/src/application/ports/metrics.port.ts"
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "file_node", "label": "metrics.port.ts",
             "source_file": source_file, "source_location": "L1", "community": 0},
            {"id": "member", "label": "MetricsPort",
             "source_file": source_file, "source_location": "L4", "community": 0},
        ],
        "links": [{"source": "file_node", "target": "member",
                   "relation": "contains", "confidence": "EXTRACTED"}],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    out = _run(monkeypatch, p, "MetricsPort", capsys)
    assert "Ambiguous" not in out
    assert "Node: MetricsPort" in out
