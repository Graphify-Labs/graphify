"""Regression tests for `graphify path` arrow direction (#849)."""
from __future__ import annotations
import json
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


def _write_multiword_graph(tmp_path):
    """src --contains--> a multi-word concept node, plus a single-token decoy that
    the per-token lexical scorer ranks first but that is isolated from src."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "src", "label": "alpha", "source_file": "a.py", "community": 0},
            {"id": "tgt", "label": "beta gamma delta", "source_file": "b.py", "community": 0},
            # EXACT-matches the "delta" token (1000 * idf) so it outscores the real
            # multi-token node (prefix 100 + substring 1 + ...); isolated from src.
            {"id": "decoy", "label": "delta", "source_file": "c.py", "community": 0},
        ],
        "links": [
            {"source": "src", "target": "tgt",
             "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_path_resolves_multiword_endpoint_whole_string(monkeypatch, tmp_path, capsys):
    """A multi-word / natural-language endpoint must resolve whole-string (the
    same exact > prefix > substring precedence `explain` uses via _find_node),
    not via the per-token lexical scorer. Otherwise a single-token EXACT decoy
    outscores the real node and `path` reports a spurious "No path found" for a
    pair that is one hop apart."""
    p = _write_multiword_graph(tmp_path)
    out = _run(monkeypatch, p, "alpha", "beta gamma delta", capsys)
    assert "No path found" not in out
    assert "Shortest path (1 hops):" in out
    assert "alpha --contains [EXTRACTED]--> beta gamma delta" in out


def test_path_falls_back_to_lexical_scorer_when_no_whole_string_match(
    monkeypatch, tmp_path, capsys
):
    """When no node matches the endpoint whole-string, `path` still resolves it
    via the lexical scorer — partial/fuzzy endpoints keep working."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "src", "label": "alpha", "source_file": "a.py", "community": 0},
            {"id": "tgt", "label": "payment processor service",
             "source_file": "b.py", "community": 0},
        ],
        "links": [
            {"source": "src", "target": "tgt",
             "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    # "payment" only prefix-matches the real label — no whole-string hit.
    out = _run(monkeypatch, p, "alpha", "payment", capsys)
    assert "No path found" not in out
    assert "Shortest path (1 hops):" in out
    assert "payment processor service" in out
