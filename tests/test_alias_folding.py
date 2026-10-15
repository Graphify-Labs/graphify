"""LLM field aliases: node file/path/filepath -> source_file, edge relationship -> relation."""
from __future__ import annotations

import io
from contextlib import redirect_stderr

from graphify.build import _fold_edge_aliases, _fold_node_aliases, build_from_json


def test_edge_relationship_folds_to_relation():
    edge = {"source": "a", "target": "b", "relationship": "calls"}
    _fold_edge_aliases(edge)
    assert edge["relation"] == "calls"
    assert "relationship" not in edge


def test_edge_relation_wins_over_relationship():
    edge = {"source": "a", "target": "b", "relation": "imports", "relationship": "calls"}
    _fold_edge_aliases(edge)
    assert edge["relation"] == "imports"


def test_node_file_folds_to_source_file():
    node = {"id": "a", "label": "A", "file": "foo.ts"}
    _fold_node_aliases(node)
    assert node["source_file"] == "foo.ts"
    assert "file" not in node


def test_node_path_folds_to_source_file():
    node = {"id": "a", "label": "A", "path": "bar.py"}
    _fold_node_aliases(node)
    assert node["source_file"] == "bar.py"
    assert "path" not in node


def test_node_filepath_folds_to_source_file():
    node = {"id": "a", "label": "A", "filepath": "baz.go"}
    _fold_node_aliases(node)
    assert node["source_file"] == "baz.go"


def test_node_source_file_wins_over_alias():
    node = {"id": "a", "label": "A", "source_file": "real.py", "file": "other.py"}
    _fold_node_aliases(node)
    assert node["source_file"] == "real.py"


def test_build_from_json_normalizes_without_validation_warnings():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "file": "foo.ts"},
            {"id": "b", "label": "B", "file_type": "code", "path": "bar.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relationship": "calls",
                "confidence": "EXTRACTED",
                "source_file": "foo.ts",
            }
        ],
    }
    err = io.StringIO()
    with redirect_stderr(err):
        G = build_from_json(extraction)
    out = err.getvalue()
    assert "missing required field" not in out
    assert G.nodes["a"]["source_file"] == "foo.ts"
    assert G.nodes["b"]["source_file"] == "bar.py"
    assert G.number_of_edges() == 1
    _, _, data = next(iter(G.edges(data=True)))
    assert data["relation"] == "calls"
