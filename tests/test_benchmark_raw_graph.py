"""#2212: run_benchmark must accept a raw --no-cluster graph.json.

The clustered writer stores edges under "links" (networkx node-link default);
the raw --no-cluster writer stores them under "edges". Consumers calling
node_link_graph(data, edges="links") raised KeyError: 'links' on the raw
shape — the `except TypeError` fallback only covered old networkx versions,
not the missing key.
"""
from __future__ import annotations
import json

from graphify.benchmark import run_benchmark


def _graph_payload(edges_key: str) -> dict:
    # Raw extract shape: top-level nodes/edges/hyperedges + token counters.
    nodes = [
        {
            "id": "auth_flow",
            "label": "authentication flow",
            "source_file": "auth.py",
            "source_location": "L1",
        },
        {
            "id": "login_handler",
            "label": "user login authentication handler",
            "source_file": "auth.py",
            "source_location": "L10",
        },
        {
            "id": "main_entry",
            "label": "main entry point",
            "source_file": "main.py",
            "source_location": "L1",
        },
    ]
    edges = [
        {
            "id": "edge_1",
            "source": "auth_flow",
            "target": "login_handler",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
        },
        {
            "id": "edge_2",
            "source": "login_handler",
            "target": "main_entry",
            "relation": "used_by",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
        },
    ]
    return {
        "nodes": nodes,
        edges_key: edges,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_run_benchmark_raw_edges_keyed_graph(tmp_path):
    """A --no-cluster graph.json ("edges" key) must not raise KeyError."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(_graph_payload("edges")), encoding="utf-8")

    result = run_benchmark(graph_path=str(graph_file), corpus_words=5_000)

    assert "error" not in result
    assert result["nodes"] == 3
    assert result["edges"] == 2
    assert result["reduction_ratio"] > 0
    assert any(
        "authentication" in p["question"] for p in result["per_question"]
    )


def test_run_benchmark_links_keyed_graph(tmp_path):
    """The clustered writer's "links" key keeps working identically."""
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(_graph_payload("links")), encoding="utf-8")

    result = run_benchmark(graph_path=str(graph_file), corpus_words=5_000)

    assert "error" not in result
    assert result["nodes"] == 3
    assert result["edges"] == 2
    assert result["reduction_ratio"] > 0


def test_raw_and_links_graphs_benchmark_identically(tmp_path):
    """Both spellings of the same graph must produce the same stats."""
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(json.dumps(_graph_payload("edges")), encoding="utf-8")
    links_file = tmp_path / "links.json"
    links_file.write_text(json.dumps(_graph_payload("links")), encoding="utf-8")

    raw = run_benchmark(graph_path=str(raw_file), corpus_words=5_000)
    links = run_benchmark(graph_path=str(links_file), corpus_words=5_000)

    assert raw == links
