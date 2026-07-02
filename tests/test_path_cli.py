"""Regression tests for `graphify path` arrow direction (#849)."""
from __future__ import annotations
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts", "community": 0},
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts", "community": 0},
        ],
        "links": [
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, src, tgt, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", src, tgt, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_forward_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    assert "Shortest path (1 hops):" in out
    assert "createPatchHandler() --calls [EXTRACTED]--> validateSanitySession()" in out


def test_reverse_arrow(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", "createPatchHandler", capsys)
    assert "Shortest path (1 hops):" in out
    assert "validateSanitySession() <--calls [EXTRACTED]-- createPatchHandler()" in out
    assert "validateSanitySession() --calls [EXTRACTED]--> createPatchHandler()" not in out


# --- #1614: endpoint ambiguity is surfaced instead of silently guessed ---
# (port of #1613's `explain` fix into `path`'s endpoint resolution)

def _write_tied_endpoint_graph(tmp_path, runner_degree):
    """Two nodes both labeled 'widget' (a genuine score tie, same exact-match
    tier) as the source side; a single unambiguous 'consumer' target. Real
    repro shape: `path "filterRegistry" "useMediaLookups"` had
    filterRegistry.ts (degree 21) and filterRegistry.test.ts (degree 8) tied
    at the identical top score."""
    nodes = [
        {"id": "widget_real", "label": "widget", "source_file": "widget.ts", "community": 0},
        {"id": "widget_test", "label": "widget", "source_file": "widget.test.ts", "community": 0},
        {"id": "consumer", "label": "consumer", "source_file": "consumer.ts", "community": 1},
    ]
    links = [{"source": "consumer", "target": "widget_real", "relation": "imports", "confidence": "EXTRACTED"}]
    # Pad widget_real's degree with extra edges so degree-dominance math is
    # exercised deliberately by the caller via runner_degree.
    for i in range(9):
        nid = f"real_dep_{i}"
        nodes.append({"id": nid, "label": f"dep{i}", "source_file": f"dep{i}.ts", "community": 2})
        links.append({"source": nid, "target": "widget_real", "relation": "imports", "confidence": "EXTRACTED"})
    for i in range(runner_degree):
        nid = f"test_dep_{i}"
        nodes.append({"id": nid, "label": f"testdep{i}", "source_file": f"testdep{i}.ts", "community": 3})
        links.append({"source": nid, "target": "widget_test", "relation": "imports", "confidence": "EXTRACTED"})
    graph_data = {"directed": False, "multigraph": False, "graph": {}, "nodes": nodes, "links": links}
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_path_ambiguous_endpoint_lists_candidates_instead_of_guessing(monkeypatch, tmp_path, capsys):
    # widget_real degree 10 (1 consumer + 9 deps), widget_test degree 8 —
    # 8 > 10*0.34=3.4, so not degree-dominant: a genuine tie.
    p = _write_tied_endpoint_graph(tmp_path, runner_degree=8)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", "widget", "consumer", "--graph", str(p)])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Ambiguous: 2 nodes match 'widget' equally closely" in out
    assert "widget [src=widget.ts" in out
    assert "widget [src=widget.test.ts" in out
    assert "Shortest path" not in out


def test_path_degree_dominant_endpoint_resolves_without_prompting(monkeypatch, tmp_path, capsys):
    # widget_real degree 10, widget_test degree 2 — 2 <= 10*0.34=3.4, dominant.
    p = _write_tied_endpoint_graph(tmp_path, runner_degree=2)
    out = _run(monkeypatch, p, "widget", "consumer", capsys)
    assert "Ambiguous:" not in out
    assert "Shortest path" in out
    assert "widget --imports" in out or "widget <--imports" in out


def test_path_force_bypasses_ambiguity_guard(monkeypatch, tmp_path, capsys):
    p = _write_tied_endpoint_graph(tmp_path, runner_degree=8)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", "widget", "consumer", "--graph", str(p), "--force"])
    mainmod.main()
    out = capsys.readouterr().out
    assert "Ambiguous:" not in out
    assert "Shortest path" in out


def test_path_unambiguous_endpoints_unaffected(monkeypatch, tmp_path, capsys):
    """The original #849 fixture (one candidate per side) must resolve exactly
    as before — no ambiguity notice, existing arrow-direction assertions
    still the whole story."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", "validateSanitySession", capsys)
    assert "Ambiguous:" not in out
    assert "Shortest path (1 hops):" in out
