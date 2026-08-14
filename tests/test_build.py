import json
from pathlib import Path
from graphify.build import build_from_json, build, patch_graph

FIXTURES = Path(__file__).parent / "fixtures"

def load_extraction():
    return json.loads((FIXTURES / "extraction.json").read_text())

def test_build_from_json_node_count():
    G = build_from_json(load_extraction())
    assert G.number_of_nodes() == 4

def test_build_from_json_edge_count():
    G = build_from_json(load_extraction())
    assert G.number_of_edges() == 4

def test_nodes_have_label():
    G = build_from_json(load_extraction())
    assert G.nodes["n_transformer"]["label"] == "Transformer"

def test_edges_have_confidence():
    G = build_from_json(load_extraction())
    data = G.edges["n_attention", "n_concept_attn"]
    assert data["confidence"] == "INFERRED"

def test_ambiguous_edge_preserved():
    G = build_from_json(load_extraction())
    data = G.edges["n_layernorm", "n_concept_attn"]
    assert data["confidence"] == "AMBIGUOUS"

def test_build_merges_multiple_extractions():
    ext1 = {"nodes": [{"id": "n1", "label": "A", "file_type": "code", "source_file": "a.py"}],
            "edges": [], "input_tokens": 0, "output_tokens": 0}
    ext2 = {"nodes": [{"id": "n2", "label": "B", "file_type": "document", "source_file": "b.md"}],
            "edges": [{"source": "n1", "target": "n2", "relation": "references",
                       "confidence": "INFERRED", "source_file": "b.md", "weight": 1.0}],
            "input_tokens": 0, "output_tokens": 0}
    G = build([ext1, ext2])
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1


# ── patch_graph: incremental updates ─────────────────────────────────────────

def _extraction(nodes, edges, hyperedges=None):
    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges or [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_patch_graph_removes_stale_nodes():
    G = build_from_json(_extraction(
        [{"id": "a", "label": "A", "source_file": "old.py"},
         {"id": "b", "label": "B", "source_file": "keep.py"}],
        [],
    ))
    patch_graph(G, {"old.py"}, [])
    assert set(G.nodes) == {"b"}


def test_patch_graph_drops_edges_declared_by_stale_file():
    """An edge whose endpoints both survive must still go if its declaring file changed."""
    G = build_from_json(_extraction(
        [{"id": "a", "label": "A", "source_file": "keep1.py"},
         {"id": "b", "label": "B", "source_file": "keep2.py"}],
        [{"source": "a", "target": "b", "type": "uses", "source_file": "stale.py"}],
    ))
    assert G.number_of_edges() == 1
    patch_graph(G, {"stale.py"}, [])
    assert G.number_of_edges() == 0, "edge outlived the file that asserted it"


def test_patch_graph_preserves_cross_file_edge_into_changed_file():
    """app.py --uses--> core.py must survive core.py being re-extracted.

    Regression: removing the changed file's nodes took this edge as collateral,
    and re-extracting only that file could never recreate it, so cross-file
    relationships silently disappeared on every incremental update.
    """
    G = build_from_json(_extraction(
        [{"id": "app", "label": "App", "source_file": "app.py"},
         {"id": "engine", "label": "Engine", "source_file": "core.py"}],
        [{"source": "app", "target": "engine", "type": "uses", "source_file": "app.py"}],
    ))
    new = _extraction([{"id": "engine", "label": "Engine", "source_file": "core.py"}], [])
    patch_graph(G, {"core.py"}, [new])
    assert G.has_edge("app", "engine"), "cross-file edge lost during incremental update"


def test_patch_graph_drops_edge_when_endpoint_really_disappears():
    G = build_from_json(_extraction(
        [{"id": "app", "label": "App", "source_file": "app.py"},
         {"id": "engine", "label": "Engine", "source_file": "core.py"}],
        [{"source": "app", "target": "engine", "type": "uses", "source_file": "app.py"}],
    ))
    # core.py changed and no longer defines Engine at all.
    patch_graph(G, {"core.py"}, [_extraction([], [])])
    assert "engine" not in G.nodes
    assert not G.has_edge("app", "engine")


def test_patch_graph_evicts_stale_hyperedges():
    """Hyperedges live on the graph attr dict, so node removal never touched them."""
    G = build_from_json(_extraction(
        [{"id": "a", "label": "A", "source_file": "old.py"}],
        [],
        hyperedges=[{"id": "h1", "nodes": ["a"], "source_file": "old.py"}],
    ))
    assert len(G.graph.get("hyperedges", [])) == 1
    patch_graph(G, {"old.py"}, [])
    assert G.graph.get("hyperedges", []) == [], "stale hyperedges accumulate forever"


def test_patch_graph_matches_full_rebuild():
    """The whole point: patching must be indistinguishable from rebuilding."""
    v1_core = [{"id": "engine", "label": "Engine", "source_file": "core.py"}]
    v2_core = [{"id": "engine", "label": "Engine", "source_file": "core.py"},
               {"id": "turbo", "label": "Turbo", "source_file": "core.py"}]
    app = [{"id": "app", "label": "App", "source_file": "app.py"}]
    app_edges = [{"source": "app", "target": "engine", "type": "uses", "source_file": "app.py"}]

    patched = build_from_json(_extraction(app + v1_core, app_edges))
    patch_graph(patched, {"core.py"}, [_extraction(v2_core, [])])

    full = build_from_json(_extraction(app + v2_core, app_edges))

    assert set(patched.nodes) == set(full.nodes)
    assert set(patched.edges) == set(full.edges)
