"""Incremental merge retention and path-normalization regressions on build DTOs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.build import _infer_merge_root, build_from_extraction, build_merge


def _seed():
    return build_from_extraction({
        "nodes": [
            {"id": "a1", "label": "a1", "source_file": "a.md", "_origin": "ast"},
            {"id": "b1", "label": "b1", "source_file": "b.md", "_origin": "ast"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "he_a", "source_file": "a.md", "nodes": ["a1"], "_origin": "ast"},
            {"id": "he_b", "source_file": "b.md", "nodes": ["b1"], "_origin": "ast"},
            {"id": "he_global", "nodes": ["a1", "b1"]},
        ],
    })


def _he_ids(data):
    return {item["id"] for item in data.attributes.get("hyperedges", [])}


def _labels(data):
    return {node.attributes.get("label") for node in data.nodes}


def test_update_preserves_hyperedges_of_unchanged_files(tmp_path):
    fresh = {
        "nodes": [{"id": "b1", "label": "b1", "source_file": "b.md", "_origin": "ast"}],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "source_file": "b.md", "nodes": ["b1"], "_origin": "ast"}],
    }
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=_seed(), dedup=False, root=tmp_path)
    assert _he_ids(data) == {"he_a", "he_global", "he_b_v2"}


def test_update_without_root_still_preserves_hyperedges(tmp_path):
    fresh = {
        "nodes": [{"id": "b1", "label": "b1", "source_file": "b.md", "_origin": "ast"}],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "source_file": "b.md", "nodes": ["b1"], "_origin": "ast"}],
    }
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=_seed(), dedup=False)
    assert _he_ids(data) == {"he_a", "he_global", "he_b_v2"}


def test_deleted_file_hyperedges_are_pruned(tmp_path):
    data = build_merge(
        [],
        tmp_path / "graph.helix",
        base_graph=_seed(),
        prune_sources=[str(tmp_path / "a.md")],
        dedup=False,
        root=tmp_path,
    )
    assert "he_a" not in _he_ids(data)
    assert "he_b" in _he_ids(data)
    assert "a1" not in {node.id for node in data.nodes}


def test_prune_without_root_removes_ghost_nodes_via_grandparent_fallback(tmp_path):
    root = tmp_path / "corpus"
    path = root / "graphify-out" / "graph.helix"
    path.parent.mkdir(parents=True)
    data = build_merge(
        [],
        path,
        base_graph=build_from_extraction({
            "nodes": [{"id": "h1", "label": "handoff", "source_file": "HANDOFF.md", "_origin": "ast"}, {"id": "k1", "label": "keep", "source_file": "KEEP.md", "_origin": "ast"}],
            "edges": [],
        }),
        prune_sources=[str(root / "HANDOFF.md")],
        dedup=False,
    )
    assert _labels(data) == {"keep"}


def test_prune_without_root_uses_graphify_root_marker(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    path = out / "graph.helix"
    real_root = tmp_path / "elsewhere" / "repo"
    real_root.mkdir(parents=True)
    (out / ".graphify_root").write_text(str(real_root))
    assert _infer_merge_root(path) == str(real_root.resolve())
    data = build_merge(
        [],
        path,
        base_graph=build_from_extraction({"nodes": [{"id": "h1", "label": "handoff", "source_file": "HANDOFF.md", "_origin": "ast"}], "edges": []}),
        prune_sources=[str(real_root / "HANDOFF.md")],
        dedup=False,
    )
    assert data.node_count == 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_prune_matches_across_symlinked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    data = build_merge(
        [],
        real / "graph.helix",
        base_graph=build_from_extraction({"nodes": [{"id": "h1", "label": "handoff", "source_file": "HANDOFF.md", "_origin": "ast"}, {"id": "k1", "label": "keep", "source_file": "KEEP.md", "_origin": "ast"}], "edges": []}),
        prune_sources=[str(link / "HANDOFF.md")],
        root=real,
        dedup=False,
    )
    assert _labels(data) == {"keep"}


def test_reextracted_file_in_prune_sources_is_not_deleted(tmp_path):
    base = build_from_extraction({"nodes": [{"id": "foo", "label": "Widget Cache Design", "source_file": "docs/foo.md", "_origin": "ast"}, {"id": "bar", "label": "Other", "source_file": "docs/bar.md", "_origin": "ast"}], "edges": []})
    fresh = {"nodes": [{"id": "foo", "label": "Widget Cache Design", "source_file": "docs/foo.md", "_origin": "ast"}], "edges": []}
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=base, prune_sources=["docs/foo.md"], root=tmp_path)
    assert "Widget Cache Design" in _labels(data)


def test_genuine_deletion_still_prunes(tmp_path):
    base = build_from_extraction({"nodes": [{"id": "foo", "label": "Widget Cache Design", "source_file": "docs/foo.md", "_origin": "ast"}, {"id": "bar", "label": "Other", "source_file": "docs/bar.md", "_origin": "ast"}], "edges": []})
    fresh = {"nodes": [{"id": "foo", "label": "Widget Cache Design", "source_file": "docs/foo.md", "_origin": "ast"}], "edges": []}
    data = build_merge([fresh], tmp_path / "graph.helix", base_graph=base, prune_sources=["docs/bar.md"], root=tmp_path)
    assert _labels(data) == {"Widget Cache Design"}
