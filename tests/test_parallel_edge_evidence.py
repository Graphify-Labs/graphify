"""Regression tests: parallel edges sharing one relation must each survive
filtering, with their own source locations intact (#4503 follow-up).

The #4503 fixture pairs two *different* relations (contains + calls). That
leaves a gap: when a relation filter matches several parallel edges with the
*same* relation, the response must still return every one of them — the old
``edge_data()`` code returned only the first. Edge count alone does not catch
that; each edge's source location has to be checked too, so the evidence
behind every relationship stays attached to the right edge.
"""

import json

from graphify.serve import _load_graph, _neighbor_lines


def _same_relation_graph_json(tmp_path):
    """A graph.json with two parallel ``calls`` edges between one pair,
    from two different call sites. Serialized flag says multigraph:false,
    like the #4500 reporter's file."""
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "src_app_app", "label": "App()"},
            {"id": "src_app_app_applyseed", "label": "applySeed()"},
        ],
        "links": [
            {"source": "src_app_app", "target": "src_app_app_applyseed",
             "relation": "calls", "confidence": "EXTRACTED",
             "source_file": "src/App.tsx", "source_location": "163"},
            {"source": "src_app_app", "target": "src_app_app_applyseed",
             "relation": "calls", "confidence": "EXTRACTED",
             "source_file": "src/App.tsx", "source_location": "201"},
        ],
    }))
    return str(p)


def test_filtered_neighbors_return_every_same_relation_edge(tmp_path):
    G = _load_graph(_same_relation_graph_json(tmp_path))
    assert G.number_of_edges() == 2
    lines = _neighbor_lines(G, "src_app_app", rel_filter="calls")
    # the filter matches both parallel edges: returning only the first
    # would silently drop a real call site from the MCP response
    assert len(lines) == 2, lines
    assert any("[calls]" in l for l in lines)


def test_each_parallel_edge_keeps_its_own_source_location(tmp_path):
    G = _load_graph(_same_relation_graph_json(tmp_path))
    lines = _neighbor_lines(G, "src_app_app", rel_filter="calls")
    calls_lines = [l for l in lines if "[calls]" in l]
    assert len(calls_lines) == 2, lines
    # each relationship cites its own call site: the evidence is per-edge,
    # never merged onto one line or attached to the wrong edge
    assert sum("App.tsx:163" in l for l in calls_lines) == 1, calls_lines
    assert sum("App.tsx:201" in l for l in calls_lines) == 1, calls_lines
