"""Tests for the local embedding pass (graphify/embed.py, issue #7).

All tests use the `_embedder` seam to inject deterministic fake vectors, so CI
needs neither a model download nor onnxruntime. The one real-model smoke test is
gated behind an importorskip + opt-in env marker.
"""
from __future__ import annotations

import json
import math
import os

import networkx as nx
import numpy as np
import pytest

from graphify import embed as embed_mod
from graphify.embed import _content_hash, _node_text, embed_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit(vec):
    arr = np.asarray(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def _vec_embedder(mapping):
    """Return an embedder callable that maps node text -> a fixed vector.

    Unknown text maps to a far-away orthogonal-ish vector so it never crosses a
    sane threshold with the named ones.
    """
    def _embed(texts):
        rows = []
        for t in texts:
            rows.append(mapping.get(t, [0.0, 0.0, 1.0, 0.0]))
        return np.asarray(rows, dtype=np.float32)

    return _embed


def _graph(nodes):
    """nodes: list of (id, label). All code, distinct files."""
    G = nx.Graph()
    for nid, label in nodes:
        G.add_node(nid, label=label, file_type="code", source_file=f"{nid}.py")
    return G


# ---------------------------------------------------------------------------
# Threshold behavior
# ---------------------------------------------------------------------------

def test_edges_created_only_above_threshold():
    # a,b nearly identical (cos ~1.0); c orthogonal.
    mapping = {
        "alpha": [1.0, 0.0, 0.0],
        "beta": [0.98, 0.2, 0.0],
        "gamma": [0.0, 1.0, 0.0],
    }
    G = _graph([("a", "alpha"), ("b", "beta"), ("c", "gamma")])
    added = embed_graph(G, threshold=0.9, _embedder=_vec_embedder(mapping))
    assert added == 1
    assert G.has_edge("a", "b")
    assert not G.has_edge("a", "c")
    assert not G.has_edge("b", "c")


def test_edge_attributes_match_spec():
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [1.0, 0.0, 0.0]}
    G = _graph([("a", "alpha"), ("b", "beta")])
    embed_graph(G, threshold=0.5, _embedder=_vec_embedder(mapping))
    data = G.get_edge_data("a", "b")
    assert data["relation"] == "semantically_similar_to"
    assert data["confidence"] == "INFERRED"
    # identical unit vectors -> cosine 1.0
    assert data["confidence_score"] == pytest.approx(1.0, abs=1e-4)
    assert data["weight"] == data["confidence_score"]
    # confidence_score is the real cosine, never the INFERRED 0.5 default.
    assert data["confidence_score"] != 0.5
    assert data["_src"] == "a" and data["_tgt"] == "b"


def test_confidence_score_is_rounded_to_4dp():
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [0.9, 0.3, 0.0]}
    G = _graph([("a", "alpha"), ("b", "beta")])
    embed_graph(G, threshold=0.5, _embedder=_vec_embedder(mapping))
    score = G.get_edge_data("a", "b")["confidence_score"]
    assert round(score, 4) == score


# ---------------------------------------------------------------------------
# has_edge guard
# ---------------------------------------------------------------------------

def test_existing_edge_not_clobbered():
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [1.0, 0.0, 0.0]}
    G = _graph([("a", "alpha"), ("b", "beta")])
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, _src="a", _tgt="b")
    added = embed_graph(G, threshold=0.5, _embedder=_vec_embedder(mapping))
    assert added == 0
    # The real calls edge survives untouched.
    assert G.get_edge_data("a", "b")["relation"] == "calls"


def test_existing_similarity_edge_not_duplicated():
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [1.0, 0.0, 0.0]}
    G = _graph([("a", "alpha"), ("b", "beta")])
    G.add_edge("a", "b", relation="semantically_similar_to", confidence="INFERRED",
               confidence_score=0.7, weight=0.7, _src="a", _tgt="b")
    added = embed_graph(G, threshold=0.5, _embedder=_vec_embedder(mapping))
    assert added == 0
    assert G.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------

def test_self_pairs_excluded_and_single_node_noop():
    G = _graph([("a", "alpha")])
    assert embed_graph(G, _embedder=_vec_embedder({"alpha": [1.0, 0.0]})) == 0
    assert G.number_of_edges() == 0


def test_empty_graph_noop():
    assert embed_graph(nx.Graph(), _embedder=_vec_embedder({})) == 0


def test_empty_text_nodes_skipped():
    # node "b" has no label -> empty text -> excluded from embedding entirely.
    G = nx.Graph()
    G.add_node("a", label="alpha", file_type="code", source_file="a.py")
    G.add_node("b", label="", file_type="code", source_file="b.py")
    added = embed_graph(G, threshold=0.1, _embedder=_vec_embedder({"alpha": [1.0, 0.0]}))
    assert added == 0


def test_zero_vector_does_not_crash():
    mapping = {"alpha": [0.0, 0.0, 0.0], "beta": [1.0, 0.0, 0.0]}
    G = _graph([("a", "alpha"), ("b", "beta")])
    # a embeds to the zero vector -> skipped, no divide-by-zero / NaN.
    added = embed_graph(G, threshold=0.1, _embedder=_vec_embedder(mapping))
    assert added == 0


# ---------------------------------------------------------------------------
# top_k
# ---------------------------------------------------------------------------

def test_top_k_caps_fanout():
    # a is similar to b, c, d (all above threshold); top_k=1 keeps only the best.
    mapping = {
        "alpha": [1.0, 0.0, 0.0],
        "b1": [0.99, 0.10, 0.0],
        "c1": [0.97, 0.20, 0.0],
        "d1": [0.95, 0.30, 0.0],
    }
    G = _graph([("a", "alpha"), ("b", "b1"), ("c", "c1"), ("d", "d1")])
    added = embed_graph(G, threshold=0.9, top_k=1, _embedder=_vec_embedder(mapping))
    # a keeps its single best neighbor; b/c/d may still pair among themselves.
    assert G.degree("a") == 1
    assert added >= 1


# ---------------------------------------------------------------------------
# Directed graphs
# ---------------------------------------------------------------------------

def test_directed_adds_single_edge_no_reverse():
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [1.0, 0.0, 0.0]}
    G = nx.DiGraph()
    for nid, label in [("a", "alpha"), ("b", "beta")]:
        G.add_node(nid, label=label, file_type="code", source_file=f"{nid}.py")
    added = embed_graph(G, threshold=0.5, _embedder=_vec_embedder(mapping))
    assert added == 1
    assert G.has_edge("a", "b") ^ G.has_edge("b", "a")


# ---------------------------------------------------------------------------
# Cache idempotency
# ---------------------------------------------------------------------------

def test_cache_idempotent(tmp_path):
    mapping = {"alpha": [1.0, 0.0, 0.0], "beta": [0.99, 0.1, 0.0]}
    cache = tmp_path / "embeddings.json"

    calls = {"n": 0}
    def counting_embedder(texts):
        calls["n"] += len(list(texts))
        return _vec_embedder(mapping)(texts)

    G1 = _graph([("a", "alpha"), ("b", "beta")])
    added1 = embed_graph(G1, threshold=0.9, cache_path=cache, _embedder=counting_embedder)
    assert added1 == 1
    first_call_count = calls["n"]
    assert first_call_count == 2  # both embedded
    node_count_1 = len(json.loads(cache.read_text())["nodes"])

    # Second run on a fresh equivalent graph: cache hit -> 0 new vectors, 0 edges.
    G2 = _graph([("a", "alpha"), ("b", "beta")])
    added2 = embed_graph(G2, threshold=0.9, cache_path=cache, _embedder=counting_embedder)
    assert added2 == 1  # edges still computed from cached vectors
    assert calls["n"] == first_call_count  # no new embedding calls
    node_count_2 = len(json.loads(cache.read_text())["nodes"])
    assert node_count_1 == node_count_2


def test_cache_schema_mismatch_forces_reembed(tmp_path):
    mapping = {"alpha": [1.0, 0.0, 0.0, 0.0], "beta": [0.99, 0.1, 0.0, 0.0]}
    cache = tmp_path / "embeddings.json"

    calls = {"n": 0}
    def counting_embedder(texts):
        calls["n"] += len(list(texts))
        return _vec_embedder(mapping)(texts)

    G1 = _graph([("a", "alpha"), ("b", "beta")])
    embed_graph(G1, threshold=0.9, dim=None, cache_path=cache, _embedder=counting_embedder)
    after_first = calls["n"]

    # Same nodes but different dim -> different vector space -> full re-embed.
    G2 = _graph([("a", "alpha"), ("b", "beta")])
    embed_graph(G2, threshold=0.9, dim=2, cache_path=cache, _embedder=counting_embedder)
    assert calls["n"] == after_first + 2


# ---------------------------------------------------------------------------
# Dim truncation
# ---------------------------------------------------------------------------

def test_dim_truncation_renormalizes(tmp_path):
    mapping = {"alpha": [3.0, 4.0, 12.0], "beta": [3.0, 4.0, 0.0]}
    cache = tmp_path / "embeddings.json"
    G = _graph([("a", "alpha"), ("b", "beta")])
    # dim=2 truncates both to their first 2 components -> [3,4] each -> cos 1.0.
    embed_graph(G, threshold=0.5, dim=2, cache_path=cache, _embedder=_vec_embedder(mapping))
    assert G.get_edge_data("a", "b")["confidence_score"] == pytest.approx(1.0, abs=1e-4)
    # cached vectors are 2-dimensional and unit-norm.
    vec = json.loads(cache.read_text())["nodes"]["a"]["vec"]
    assert len(vec) == 2
    assert math.isclose(np.linalg.norm(vec), 1.0, abs_tol=1e-4)


# ---------------------------------------------------------------------------
# Chunked vs naive equivalence
# ---------------------------------------------------------------------------

def test_chunked_similarity_equals_naive(monkeypatch):
    rng = np.random.default_rng(0)
    n = 40
    vecs = {f"t{i}": rng.normal(size=8).tolist() for i in range(n)}
    nodes = [(f"n{i}", f"t{i}") for i in range(n)]

    def run(block):
        monkeypatch.setattr(embed_mod, "_SIM_BLOCK", block)
        G = _graph(nodes)
        embed_graph(G, threshold=0.3, _embedder=_vec_embedder(vecs))
        return {tuple(sorted((u, v))) for u, v in G.edges()}

    assert run(4) == run(1000)


# ---------------------------------------------------------------------------
# Missing-deps error
# ---------------------------------------------------------------------------

def test_missing_deps_raises_clean_error(monkeypatch):
    # Force the real embedder path (no seam) and make its import fail.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "onnxruntime":
            raise ImportError("no onnxruntime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    G = _graph([("a", "alpha"), ("b", "beta")])
    with pytest.raises(RuntimeError, match=r"\[embeddings\] extra"):
        embed_graph(G, threshold=0.5)


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def test_node_text_combines_fields():
    node = {"label": "validate", "signature": "def validate(x)", "summary": "checks x"}
    text = _node_text(node)
    assert "validate" in text and "def validate(x)" in text and "checks x" in text


def test_content_hash_changes_with_config():
    h1 = _content_hash("foo", "repo", "q4", None)
    h2 = _content_hash("foo", "repo", "q8", None)
    h3 = _content_hash("foo", "repo", "q4", 256)
    assert h1 != h2 and h1 != h3


def test_pyproject_declares_embeddings_extra():
    """Acceptance #5: `pip install graphifyy[embeddings]` resolves the right deps,
    and the extra is rolled into [all]."""
    import pathlib

    try:
        import tomllib  # py311+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore

    root = pathlib.Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert "embeddings" in extras
    deps = extras["embeddings"]
    for pkg in ("onnxruntime", "huggingface-hub", "tokenizers", "numpy"):
        assert any(pkg in dep for dep in deps), f"[embeddings] missing {pkg}"
        assert any(pkg in dep for dep in extras["all"]), f"[all] missing {pkg}"


# ---------------------------------------------------------------------------
# Real-model smoke test (opt-in, offline-by-default)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("GRAPHIFY_EMBED_REAL_MODEL") != "1",
    reason="set GRAPHIFY_EMBED_REAL_MODEL=1 to run the real EmbeddingGemma download",
)
def test_real_model_smoke():
    pytest.importorskip("onnxruntime")
    G = _graph([("a", "user authentication handler"), ("b", "login auth check")])
    added = embed_graph(G, threshold=0.5)
    assert added >= 0
