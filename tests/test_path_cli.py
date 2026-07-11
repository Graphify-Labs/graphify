"""Regression tests for `graphify path` arrow direction (#849)."""
from __future__ import annotations
import json
import networkx as nx
import pytest
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


def _write_misranking_graph(tmp_path):
    """Graph where IDF scoring ranks a partial-token decoy above the full match.

    Query "Reject-everything judge": the decoy "Rejection Summary" prefix-matches
    the rare token "reject" and out-scores "Degenerate Reject-Everything Judge"
    (whose full-query tier never fires — the query is a token subset of the
    label, not a prefix). The filler nodes make "judge"/"everything" common so
    their IDF stays low. Decoy and target live in different components: resolving
    the source to the decoy yields a false "No path found".
    """
    nodes = [
        {"id": "target", "label": "Degenerate Reject-Everything Judge", "community": 0},
        {"id": "decoy", "label": "Rejection Summary", "community": 0},
    ]
    for i in range(30):
        nodes.append({"id": f"j{i}", "label": f"Judge Helper {i}", "community": 0})
        nodes.append({"id": f"e{i}", "label": f"Everything Widget {i}", "community": 0})
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": nodes,
        "links": [
            {"source": "target", "target": "j0",
             "relation": "verified_by", "confidence": "EXTRACTED"},
            {"source": "decoy", "target": "e0",
             "relation": "mentions", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_endpoint_prefers_full_token_match(monkeypatch, tmp_path, capsys):
    """A token-subset query resolves to the full-match node, not the IDF head."""
    p = _write_misranking_graph(tmp_path)
    out = _run(monkeypatch, p, "Reject-everything judge", "Judge Helper 0", capsys)
    assert "Shortest path (1 hops):" in out
    assert "Degenerate Reject-Everything Judge" in out
    assert "No path found" not in out


def test_endpoint_falls_back_to_score_head(monkeypatch, tmp_path, capsys):
    """No full-token candidate -> behavior identical to the old scored[0] pick."""
    p = _write_misranking_graph(tmp_path)
    # "Rejection judge" full-matches nothing ("rejection" only appears in the
    # decoy, "judge" never joins it), so the IDF head (the decoy) still wins,
    # and the disconnected components make that a "No path found" exit(0).
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "path", "Rejection judge", "Judge Helper 0", "--graph", str(p)])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 0
    assert "No path found" in capsys.readouterr().out
