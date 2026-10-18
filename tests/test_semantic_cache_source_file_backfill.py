"""#3982 — save_semantic_cache must not silently drop work a local model returned.

A small local model fills ``source_file`` on nodes but routinely leaves it off
edges, and invents ``source_file`` paths that name no real file. Both kinds of
item had no usable cache key and vanished with no message, so a chunk logged as
a success persisted almost nothing and was re-extracted (and dropped) on every
incremental run.
"""
from __future__ import annotations

import warnings

import pytest

from graphify.cache import load_cached, save_semantic_cache


def _doc(tmp_path, rel="docs/a.md"):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# A\n", encoding="utf-8")
    return path


def test_edge_without_source_file_takes_its_endpoint_file(tmp_path):
    doc = _doc(tmp_path)
    nodes = [
        {"id": "a", "label": "A", "source_file": "docs/a.md"},
        {"id": "b", "label": "B", "source_file": "docs/a.md"},
    ]
    edges = [{"source": "a", "target": "b", "relation": "references"}]
    hyperedges = [{"id": "h", "label": "H", "nodes": ["a", "b"], "relation": "form"}]

    assert save_semantic_cache(nodes, edges, hyperedges, root=tmp_path) == 1

    cached = load_cached(doc, root=tmp_path, kind="semantic")
    assert cached is not None
    assert [(e["source"], e["target"]) for e in cached["edges"]] == [("a", "b")]
    assert [h["id"] for h in cached["hyperedges"]] == ["h"]
    # The caller's dicts are untouched.
    assert "source_file" not in edges[0]
    assert "source_file" not in hyperedges[0]


def test_edge_with_no_located_endpoint_is_reported_not_silently_dropped(tmp_path):
    _doc(tmp_path)
    nodes = [{"id": "a", "label": "A", "source_file": "docs/a.md"}]
    edges = [{"source": "x", "target": "y", "relation": "references"}]

    with pytest.warns(RuntimeWarning, match="1 node.*no source_file"):
        save_semantic_cache(nodes, edges, root=tmp_path)


def test_hyperedge_spanning_two_files_is_not_guessed(tmp_path):
    _doc(tmp_path, "docs/a.md")
    _doc(tmp_path, "docs/b.md")
    nodes = [
        {"id": "a", "label": "A", "source_file": "docs/a.md"},
        {"id": "b", "label": "B", "source_file": "docs/b.md"},
    ]
    hyperedges = [{"id": "h", "label": "H", "nodes": ["a", "b"], "relation": "form"}]

    with pytest.warns(RuntimeWarning, match="no source_file"):
        save_semantic_cache(nodes, [], hyperedges, root=tmp_path)


def test_invented_path_in_a_single_file_chunk_belongs_to_that_file(tmp_path):
    doc = _doc(tmp_path, "notes/SPEC-FINAL.md")
    nodes = [{"id": "a", "label": "A", "source_file": "diana-rag/insight_1.md"}]

    saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[doc])

    assert saved == 1
    cached = load_cached(doc, root=tmp_path, kind="semantic")
    assert cached is not None
    # Rewritten to the dispatched file (spelled the way #2973's recovery spells it).
    assert [n["id"] for n in cached["nodes"]] == ["a"]
    assert all(n["source_file"].replace("\\", "/").lower().endswith("notes/spec-final.md")
               for n in cached["nodes"])


def test_invented_path_in_a_multi_file_chunk_is_skipped_and_reported(tmp_path):
    a = _doc(tmp_path, "docs/a.md")
    b = _doc(tmp_path, "docs/b.md")
    nodes = [
        {"id": "a", "label": "A", "source_file": "docs/a.md"},
        {"id": "x", "label": "X", "source_file": "invented/insight_7.md"},
    ]

    with pytest.warns(RuntimeWarning, match="skipped 1 of 2"):
        saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[a, b])

    assert saved == 1
    assert load_cached(b, root=tmp_path, kind="semantic") is None


def test_real_undispatched_file_stays_out_of_scope_in_a_single_file_chunk(tmp_path):
    doc = _doc(tmp_path, "docs/a.md")
    other = _doc(tmp_path, "docs/other.md")
    nodes = [{"id": "o", "label": "O", "source_file": "docs/other.md"}]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[doc])

    assert saved == 0
    assert load_cached(doc, root=tmp_path, kind="semantic") is None
    assert load_cached(other, root=tmp_path, kind="semantic") is None


def test_basename_recovery_ignores_case(tmp_path):
    a = _doc(tmp_path, "g0/SPEC-CONGELATA.md")
    b = _doc(tmp_path, "g0/other.md")
    nodes = [{"id": "s", "label": "S", "source_file": "spec-congelata.md"}]

    saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[a, b])

    assert saved == 1
    assert load_cached(a, root=tmp_path, kind="semantic") is not None
