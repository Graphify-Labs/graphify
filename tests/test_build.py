import json
from pathlib import Path
from graphify.build import build_from_json, build

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

def _two_nodes():
    return [
        {"id": "a", "label": "a", "file_type": "document", "source_file": "a.md"},
        {"id": "b", "label": "b", "file_type": "document", "source_file": "b.md"},
    ]

def test_edge_missing_required_field_is_not_persisted():
    """A schema-invalid edge must not reach graph.json, even though it is warned about."""
    extraction = {
        "nodes": _two_nodes(),
        "edges": [{"source": "a", "target": "b", "confidence": "INFERRED", "source_file": "a.md"}],
    }
    G = build_from_json(extraction)
    assert G.number_of_edges() == 0

def test_valid_edges_survive_alongside_dropped_ones():
    extraction = {
        "nodes": _two_nodes(),
        "edges": [
            {"source": "a", "target": "b", "confidence": "INFERRED", "source_file": "a.md"},
            {"source": "a", "target": "b", "relation": "cites",
             "confidence": "EXTRACTED", "source_file": "a.md"},
        ],
    }
    G = build_from_json(extraction)
    assert G.number_of_edges() == 1
    assert G.edges["a", "b"]["relation"] == "cites"

def test_dropped_edge_is_reported_with_the_missing_field(capsys):
    extraction = {
        "nodes": _two_nodes(),
        "edges": [{"source": "a", "target": "b", "confidence": "INFERRED", "source_file": "a.md"}],
    }
    build_from_json(extraction)
    err = capsys.readouterr().err
    assert "Dropped 1 schema-invalid edge(s)" in err
    assert "'relation'" in err

def test_dangling_edge_is_not_reported_as_dropped(capsys):
    """Edges to external/stdlib nodes are expected and stay silent."""
    extraction = {
        "nodes": _two_nodes(),
        "edges": [{"source": "a", "target": "os", "relation": "imports",
                   "confidence": "EXTRACTED", "source_file": "a.md"}],
    }
    G = build_from_json(extraction)
    assert G.number_of_edges() == 0
    assert "Dropped" not in capsys.readouterr().err

def test_legacy_edge_alias_is_folded_before_validation():
    """A legacy "relationship" key is canonicalized, so the edge is not dropped."""
    extraction = {
        "nodes": _two_nodes(),
        "edges": [{"source": "a", "target": "b", "relationship": "cites",
                   "confidence": "EXTRACTED", "source_file": "a.md"}],
    }
    G = build_from_json(extraction)
    assert G.number_of_edges() == 1
    data = G.edges["a", "b"]
    assert data["relation"] == "cites"
    assert "relationship" not in data

def test_alias_folding_does_not_mutate_the_caller_extraction():
    edge = {"source": "a", "target": "b", "relationship": "cites",
            "confidence": "EXTRACTED", "source_file": "a.md"}
    build_from_json({"nodes": _two_nodes(), "edges": [edge]})
    assert "relation" not in edge
    assert edge["relationship"] == "cites"
