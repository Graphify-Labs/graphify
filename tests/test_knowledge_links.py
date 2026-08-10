from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify.knowledge_links import KnowledgeLinkError, apply_knowledge_links


def _write_manifest(root, links):
    path = root / "docs" / "contracts" / "knowledge_graph_links.v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": "tetra.knowledge-graph-links.v1", "links": links}))


def test_apply_knowledge_links_adds_validated_edge(tmp_path):
    (tmp_path / "docs" / "spec").mkdir(parents=True)
    (tmp_path / "compiler").mkdir()
    (tmp_path / "docs" / "spec" / "language.md").write_text("spec")
    (tmp_path / "compiler" / "frontend.go").write_text("package compiler")
    _write_manifest(tmp_path, [{
        "source": {"path": "docs/spec/language.md"},
        "target": {"path": "compiler/frontend.go", "symbol": "ParseFile()"},
        "relation": "implemented_by",
        "rationale": "The canonical parser implements the language grammar.",
    }])
    graph = nx.Graph()
    graph.add_node("spec", label="language.md", source_file="docs/spec/language.md")
    graph.add_node("parse", label="ParseFile()", source_file="compiler/frontend.go")

    stats = apply_knowledge_links(graph, tmp_path)

    assert stats == {"loaded": 1, "applied": 1}
    assert graph.edges["spec", "parse"]["relation"] == "implemented_by"
    assert graph.edges["spec", "parse"]["confidence"] == "EXTRACTED"


def test_apply_knowledge_links_rejects_absolute_endpoint(tmp_path):
    _write_manifest(tmp_path, [{
        "source": {"path": str(tmp_path / "secret.md")},
        "target": {"path": "compiler/frontend.go"},
        "relation": "references",
        "rationale": "invalid",
    }])
    with pytest.raises(KnowledgeLinkError, match="repo-relative"):
        apply_knowledge_links(nx.Graph(), tmp_path)


def test_apply_knowledge_links_rejects_ambiguous_symbol(tmp_path):
    (tmp_path / "a.go").write_text("package a")
    (tmp_path / "b.go").write_text("package b")
    _write_manifest(tmp_path, [{
        "source": {"path": "a.go"},
        "target": {"path": "b.go", "symbol": "run()"},
        "relation": "tests",
        "rationale": "ambiguous on purpose",
    }])
    graph = nx.Graph()
    graph.add_node("a", label="a.go", source_file="a.go")
    graph.add_node("b1", label="run()", source_file="b.go")
    graph.add_node("b2", label="run()", source_file="b.go")
    with pytest.raises(KnowledgeLinkError, match="ambiguous"):
        apply_knowledge_links(graph, tmp_path)
