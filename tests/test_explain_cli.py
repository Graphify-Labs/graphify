"""Native ``graphify explain`` direction and learning-state tests."""

import graphify.__main__ as mainmod
from graphify.helix.state import new_state
from tests.native_helpers import make_loaded


def _store(tmp_path, *, learning=None):
    state = new_state(learning=learning or {})
    return make_loaded(
        tmp_path,
        nodes=[
            {"id": "validate", "label": "validateSanitySession()", "source_file": "server/validate.ts", "source_location": "L1", "file_type": "code"},
            {"id": "patch", "label": "createPatchHandler()", "source_file": "server/patch.ts", "file_type": "code"},
            {"id": "edit", "label": "createEditHandler()", "source_file": "server/edit.ts", "file_type": "code"},
            {"id": "stringify", "label": "stableStringify()", "source_file": "shared/stringify.ts", "file_type": "code"},
        ],
        edges=[
            {"source": "patch", "target": "validate", "relation": "calls"},
            {"source": "edit", "target": "validate", "relation": "calls"},
            {"source": "validate", "target": "stringify", "relation": "calls"},
        ],
        state=state,
    )


def _run(monkeypatch, capsys, store, query):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "explain", query, "--store", str(store)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_inbound_and_callee_outbound(monkeypatch, tmp_path, capsys):
    store = _store(tmp_path).store_path
    out = _run(monkeypatch, capsys, store, "validateSanitySession")
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out


def test_caller_shows_callee_outbound(monkeypatch, tmp_path, capsys):
    store = _store(tmp_path).store_path
    out = _run(monkeypatch, capsys, store, "createPatchHandler")
    assert "--> validateSanitySession() [calls]" in out


def test_source_path_exact_match_prefers_file_node(monkeypatch, tmp_path, capsys):
    loaded = make_loaded(
        tmp_path,
        nodes=[
            {"id": "route_get", "label": "GET()", "source_file": "app/route.ts", "source_location": "L42"},
            {"id": "route", "label": "route.ts", "source_file": "app/route.ts", "source_location": "L1"},
        ],
        edges=[{"source": "route", "target": "route_get", "relation": "contains"}],
    )
    out = _run(monkeypatch, capsys, loaded.store_path, "app/route.ts")
    assert "Node: route.ts" in out and "ID:        route" in out


def test_learning_state_is_rendered(monkeypatch, tmp_path, capsys):
    learning = {
        "version": 1,
        "nodes": {"validate": {"status": "preferred", "score": 2.4, "uses": 3}},
    }
    store = _store(tmp_path, learning=learning).store_path
    out = _run(monkeypatch, capsys, store, "validate")
    assert "Lesson: preferred source (start here) — 3 useful, score=2.4" in out


def test_unannotated_node_has_no_lesson(monkeypatch, tmp_path, capsys):
    out = _run(monkeypatch, capsys, _store(tmp_path).store_path, "validate")
    assert "Lesson:" not in out


def test_explain_connection_shows_call_site_line(monkeypatch, tmp_path, capsys):
    """BUG1: an explain connection shows the edge's call-SITE line (in the
    caller's file), not the caller's def line."""
    loaded = make_loaded(
        tmp_path,
        nodes=[
            {"id": "loader", "label": "load_state()",
             "source_file": "apollo.py", "source_location": "L90", "community": 0},
            {"id": "trans", "label": "transition_state()",
             "source_file": "state.py", "source_location": "L56", "community": 0},
        ],
        edges=[
            {"source": "loader", "target": "trans", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "apollo.py", "source_location": "L158"},
        ],
    )
    out = _run(monkeypatch, capsys, loaded.store_path, "transition_state")
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
    return make_loaded(tmp_path, nodes=nodes, edges=links).store_path


def test_explain_truncation_notice_present_for_high_degree_node(monkeypatch, tmp_path, capsys):
    """Baseline: the cut count is still announced (pre-existing behavior)."""
    p = _write_high_degree_graph(tmp_path, n_callers=30)
    out = _run(monkeypatch, capsys, p, "hub")
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
    out = _run(monkeypatch, capsys, p, "hub")
    assert "Grouped by file:" in out
    assert "<-- lib/workers/queue.py:" in out
    assert "<-- app/handlers/email.py:" in out
    assert "<-- app/jobs/retry.py:" in out
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
    out = _run(monkeypatch, capsys, p, "hub")
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
    out21 = _run(monkeypatch, capsys, p21, "hub")
    assert "Grouped by file:" in out21
    assert "<-- lib/only.py: 1 connection" in out21
    grouped_lines21 = [
        l for l in out21.splitlines() if l.strip().startswith(("<--", "-->")) and "connection" in l
    ]
    assert len(grouped_lines21) == 1  # exactly one grouped entry, not zero, not more

    p20 = _write_high_degree_graph(tmp_path, n_callers=20, files=["lib/only.py"])
    out20 = _run(monkeypatch, capsys, p20, "hub")
    assert "Grouped by file:" not in out20
    assert "more" not in out20
