"""Tests for issue #3472:
Same file, two path forms: absolute source_file from semantic extraction collides with
the relative AST id and the semantic node is dropped.
"""
import json
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build, build_merge


def test_semantic_absolute_path_same_file_retains_attributes(tmp_path, capsys):
    """AST node in graph.json has relative source_file; incoming semantic node has
    absolute source_file. Both encode the same physical file and ID.
    The collision logic must recognize them as the same file:
    - no 'minted by two different files' warning
    - shorter/canonical AST label survives
    - source_file is repo-relative
    - semantic attributes (rationale, summary) are merged onto survivor
    """
    root = tmp_path.resolve()
    graph_path = root / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)

    ast_node = {
        "id": "docs_architecture_retrieval",
        "label": "Retrieval",
        "file_type": "document",
        "source_file": "docs/ARCHITECTURE.md",
        "source_location": "L42",
        "_origin": "ast",
    }
    G0 = build([{"nodes": [ast_node], "edges": []}], dedup=False)
    graph_path.write_text(json.dumps(nx.node_link_data(G0, edges="edges")), encoding="utf-8")

    abs_sf = str((root / "docs" / "ARCHITECTURE.md").resolve())
    sem_node = {
        "id": "docs_architecture_retrieval",
        "label": "Hybrid Retrieval",
        "file_type": "document",
        "source_file": abs_sf,
        "source_location": None,
        "rationale": "Detailed hybrid search rationale",
        "summary": "Hybrid search architecture",
    }

    G = build_merge([{"nodes": [sem_node], "edges": []}], graph_path=graph_path, root=root)

    assert G.number_of_nodes() == 1
    surv = G.nodes["docs_architecture_retrieval"]
    assert surv["label"] == "Retrieval"
    assert surv["source_file"] == "docs/ARCHITECTURE.md"
    assert surv["source_location"] == "L42"
    assert surv["_origin"] == "ast"
    assert surv["rationale"] == "Detailed hybrid search rationale"
    assert surv["summary"] == "Hybrid search architecture"

    err = capsys.readouterr().err
    assert "minted by two different files" not in err
    assert "WARNING" not in err
    assert "note:" in err


def test_semantic_absolute_path_inverse_arrival_order(tmp_path, capsys):
    """Arrival order independence: if semantic chunk arrives before AST chunk,
    the canonical AST label and merged attributes must be identical.
    """
    root = tmp_path.resolve()
    abs_sf = str((root / "docs" / "ARCHITECTURE.md").resolve())

    sem_node = {
        "id": "docs_architecture_retrieval",
        "label": "Hybrid Retrieval",
        "file_type": "document",
        "source_file": abs_sf,
        "source_location": None,
        "rationale": "Detailed hybrid search rationale",
        "summary": "Hybrid search architecture",
    }
    ast_node = {
        "id": "docs_architecture_retrieval",
        "label": "Retrieval",
        "file_type": "document",
        "source_file": "docs/ARCHITECTURE.md",
        "source_location": "L42",
        "_origin": "ast",
    }

    # Semantic chunk first, AST chunk second
    G = build(
        [{"nodes": [sem_node], "edges": []}, {"nodes": [ast_node], "edges": []}],
        root=root,
        dedup=True,
    )

    assert G.number_of_nodes() == 1
    surv = G.nodes["docs_architecture_retrieval"]
    assert surv["label"] == "Retrieval"
    assert surv["source_file"] == "docs/ARCHITECTURE.md"
    assert surv["source_location"] == "L42"
    assert surv["_origin"] == "ast"
    assert surv["rationale"] == "Detailed hybrid search rationale"
    assert surv["summary"] == "Hybrid search architecture"

    err = capsys.readouterr().err
    assert "minted by two different files" not in err
    assert "WARNING" not in err


def test_build_merge_infers_root_for_semantic_absolute_path(tmp_path, capsys):
    """When root is omitted, build_merge infers _eff_root and passes it downstream,
    so absolute source_file from semantic chunks still collapses with stored relative keys.
    """
    root = tmp_path.resolve()
    graph_path = root / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)

    ast_node = {
        "id": "docs_architecture_retrieval",
        "label": "Retrieval",
        "file_type": "document",
        "source_file": "docs/ARCHITECTURE.md",
        "source_location": "L42",
        "_origin": "ast",
    }
    G0 = build([{"nodes": [ast_node], "edges": []}], dedup=False)
    graph_path.write_text(json.dumps(nx.node_link_data(G0, edges="edges")), encoding="utf-8")

    abs_sf = str((root / "docs" / "ARCHITECTURE.md").resolve())
    sem_node = {
        "id": "docs_architecture_retrieval",
        "label": "Hybrid Retrieval",
        "file_type": "document",
        "source_file": abs_sf,
        "source_location": None,
        "rationale": "Detailed hybrid search rationale",
    }

    # Call build_merge WITHOUT root parameter
    G = build_merge([{"nodes": [sem_node], "edges": []}], graph_path=graph_path)

    assert G.number_of_nodes() == 1
    surv = G.nodes["docs_architecture_retrieval"]
    assert surv["label"] == "Retrieval"
    assert surv["source_file"] == "docs/ARCHITECTURE.md"
    assert surv["rationale"] == "Detailed hybrid search rationale"

    err = capsys.readouterr().err
    assert "minted by two different files" not in err
    assert "WARNING" not in err


def test_genuine_cross_file_collision_remains_isolated(tmp_path, capsys):
    """Two genuinely different files that happen to mint the same ID must still
    be treated as a cross-file collision:
    - warning is emitted
    - attributes from the loser are NOT merged into the survivor
    """
    root = tmp_path.resolve()
    abs_sf_b = str((root / "docs" / "DESIGN.md").resolve())

    node_a = {
        "id": "docs_retrieval",
        "label": "Retrieval",
        "file_type": "document",
        "source_file": "docs/ARCHITECTURE.md",
        "source_location": "L10",
        "summary": "Architecture retrieval",
    }
    node_b = {
        "id": "docs_retrieval",
        "label": "Detailed Retrieval",
        "file_type": "document",
        "source_file": abs_sf_b,
        "source_location": "L25",
        "summary": "Design retrieval",
        "rationale": "Design rationale",
    }

    G = build([{"nodes": [node_a, node_b], "edges": []}], root=root, dedup=True)

    assert G.number_of_nodes() == 1
    surv = G.nodes["docs_retrieval"]
    assert surv["source_file"] == "docs/ARCHITECTURE.md"
    assert surv["label"] == "Retrieval"
    assert surv["summary"] == "Architecture retrieval"
    # The loser's rationale must NOT be merged into the survivor from a different file!
    assert "rationale" not in surv

    err = capsys.readouterr().err
    assert "minted by two different files" in err
    assert "WARNING" in err


def test_definition_file_normalized_before_dedup(tmp_path):
    """definition_file should also be normalized to repo-relative against root."""
    root = tmp_path.resolve()
    abs_df = str((root / "src" / "impl.py").resolve())

    node = {
        "id": "src_impl_func",
        "label": "func",
        "file_type": "code",
        "source_file": "src/decl.py",
        "definition_file": abs_df,
    }

    G = build([{"nodes": [node], "edges": []}], root=root, dedup=True)

    assert G.nodes["src_impl_func"]["definition_file"] == "src/impl.py"
