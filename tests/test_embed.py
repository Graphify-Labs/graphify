"""Tests for graphify.embed — optional semantic ranking backend.

A deterministic letter-count fake embedder stands in for a real model: texts
that share letters get similar vectors, so semantic scores are meaningful and
reproducible without Ollama or sentence-transformers.
"""
from __future__ import annotations

import numpy as np
import pytest

import networkx as nx

from graphify import embed
from graphify.embed import (
    _text_prefix,
    build_embeddings,
    get_embedder,
    load_embeddings,
    node_text,
    semantic_scores_for_query,
    sidecar_paths,
)


def test_text_prefix_nomic_is_asymmetric():
    assert _text_prefix("ollama:nomic-embed-text", "query") == "search_query: "
    assert _text_prefix("ollama:nomic-embed-text", "document") == "search_document: "


def test_text_prefix_non_nomic_is_empty():
    assert _text_prefix("st:all-MiniLM-L6-v2", "query") == ""
    assert _text_prefix("fake", "document") == ""
    assert _text_prefix("", "query") == ""


def fake_embedder(texts):
    """26-d letter-count vectors: shared letters -> higher cosine."""
    out = []
    for t in texts:
        v = np.zeros(26, dtype=np.float32)
        for ch in str(t).lower():
            if "a" <= ch <= "z":
                v[ord(ch) - 97] += 1.0
        out.append(v)
    return np.asarray(out, dtype=np.float32)


def _graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract()", source_file="graphify/extract.py", community_name="io")
    G.add_node("n2", label="cluster()", source_file="graphify/cluster.py", community_name="graph")
    G.add_node("n3", label="wxyz()", source_file="q/jkq.py", community_name="misc")
    return G


def test_node_text_combines_fields():
    text = node_text({"label": "foo()", "source_file": "a/b.py", "community_name": "core"})
    assert "foo()" in text and "a/b.py" in text and "core" in text


def test_node_text_falls_back_to_label():
    assert node_text({"label": "solo"}) == "solo"


def test_build_and_load_roundtrip(tmp_path):
    G = _graph()
    gp = str(tmp_path / "graph.json")
    summary = build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")
    assert summary["status"] == "built"
    assert summary["count"] == 3
    loaded = load_embeddings(gp)
    assert loaded is not None
    ids, matrix, meta = loaded
    assert set(ids) == {"n1", "n2", "n3"}
    assert matrix.shape == (3, 26)
    assert meta["model"] == "fake"
    # Vectors are L2-normalized on write.
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, 1.0)


def test_build_is_cached_then_forced(tmp_path):
    G = _graph()
    gp = str(tmp_path / "graph.json")
    assert build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")["status"] == "built"
    assert build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")["status"] == "cached"
    assert build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake", force=True)["status"] == "built"


def test_build_rebuilds_when_nodes_change(tmp_path):
    gp = str(tmp_path / "graph.json")
    G = _graph()
    build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")
    G.add_node("n4", label="new()", source_file="n.py")
    # Different node set -> different content hash -> not cached.
    assert build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")["status"] == "built"


def test_semantic_scores_rank_by_overlap(tmp_path):
    G = _graph()
    gp = str(tmp_path / "graph.json")
    build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")
    scores = semantic_scores_for_query(G, "extract", graph_path=gp, embedder=fake_embedder)
    assert set(scores) == {"n1", "n2", "n3"}
    # 'extract' shares more letters with extract() than with wxyz().
    assert scores["n1"] > scores["n3"]


def test_semantic_scores_only_for_present_nodes(tmp_path):
    G = _graph()
    gp = str(tmp_path / "graph.json")
    build_embeddings(G, gp, embedder=fake_embedder, model_tag="fake")
    G.remove_node("n3")  # sidecar still has n3, but it's no longer in the graph
    scores = semantic_scores_for_query(G, "cluster", graph_path=gp, embedder=fake_embedder)
    assert "n3" not in scores
    assert set(scores) == {"n1", "n2"}


def test_semantic_scores_without_sidecar_raises(tmp_path):
    G = _graph()
    gp = str(tmp_path / "nope.json")
    with pytest.raises(RuntimeError):
        semantic_scores_for_query(G, "extract", graph_path=gp, embedder=fake_embedder)


def test_sidecar_paths_beside_graph(tmp_path):
    gp = str(tmp_path / "sub" / "graph.json")
    vec, meta = sidecar_paths(gp)
    assert vec.parent == (tmp_path / "sub")
    assert vec.name.endswith(".npz")
    assert meta.name.endswith(".json")


def test_get_embedder_errors_when_backend_forced_and_absent(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_EMBED_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")  # nothing listening
    with pytest.raises(RuntimeError):
        get_embedder()
