"""Incremental --update: hyperedge preservation (#1574) and root-less prune (#1571).

build_merge backs `graphify --update`. Two regressions covered here:

- #1574: it read only nodes+edges from the existing graph.json, never hyperedges,
  so every incremental update collapsed the graph's hyperedge set down to just the
  re-extracted files'. Now existing hyperedges are carried forward, with
  re-extracted files' replaced (by source_file) and deleted files' pruned.
- #1571: when a caller omits `root` (the skill's --update runbook does), absolute
  prune_sources never relativized to match the stored relative source_file keys, so
  deleted files' nodes survived as ghosts. build_merge now infers a fallback root.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from graphify.build import build_merge, _infer_merge_root


def _write_graph(graph_path: Path, nodes, edges, hyperedges) -> None:
    """Write a graph.json in the shape to_json emits (top-level hyperedges)."""
    graph_path.write_text(
        json.dumps({"nodes": nodes, "edges": edges, "hyperedges": hyperedges}),
        encoding="utf-8",
    )


def _he_ids(G) -> set[str]:
    return {h["id"] for h in G.graph.get("hyperedges", [])}


# ── #1574: hyperedge preservation ─────────────────────────────────────────────

def _seed_two_file_graph(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    nodes = [
        {"id": "a1", "label": "a1", "file_type": "document", "source_file": "a.md"},
        {"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"},
    ]
    hyperedges = [
        {"id": "he_a", "label": "flow A", "source_file": "a.md", "nodes": ["a1"]},
        {"id": "he_b", "label": "flow B", "source_file": "b.md", "nodes": ["b1"]},
        {"id": "he_global", "label": "cross-file flow", "nodes": ["a1", "b1"]},  # no source_file
    ]
    _write_graph(graph_path, nodes, [], hyperedges)
    return root, graph_path


def test_update_preserves_hyperedges_of_unchanged_files(tmp_path):
    root, graph_path = _seed_two_file_graph(tmp_path)
    # Re-extract only b.md, with a fresh hyperedge for it.
    new_chunk = {
        "nodes": [{"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"}],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "label": "flow B v2", "source_file": "b.md", "nodes": ["b1"]}],
    }
    G = build_merge([new_chunk], graph_path, dedup=False, root=root)
    ids = _he_ids(G)
    assert "he_a" in ids           # unchanged file's hyperedge preserved (the bug)
    assert "he_global" in ids      # source_file-less hyperedge preserved
    assert "he_b_v2" in ids        # re-extracted file's new hyperedge present
    assert "he_b" not in ids       # re-extracted file's OLD hyperedge replaced


def test_update_without_root_still_preserves_hyperedges(tmp_path):
    """The runbook omits root; the fallback root must not break preservation."""
    root, graph_path = _seed_two_file_graph(tmp_path)
    new_chunk = {
        "nodes": [{"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"}],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "source_file": "b.md", "nodes": ["b1"]}],
    }
    G = build_merge([new_chunk], graph_path, dedup=False)  # no root
    ids = _he_ids(G)
    assert {"he_a", "he_global", "he_b_v2"} <= ids
    assert "he_b" not in ids


def test_deleted_file_hyperedges_are_pruned(tmp_path):
    root, graph_path = _seed_two_file_graph(tmp_path)
    deleted_abs = [str(root / "a.md")]
    G = build_merge([], graph_path, prune_sources=deleted_abs, dedup=False, root=root)
    ids = _he_ids(G)
    assert "he_a" not in ids        # deleted file's hyperedge pruned
    assert "he_b" in ids            # untouched file's hyperedge kept
    assert "he_global" in ids       # global hyperedge kept
    # and its node is gone too
    assert "a1" not in set(G.nodes)


# ── #1571: root-less prune (absolute deleted paths vs relative node keys) ──────

def test_prune_without_root_removes_ghost_nodes_via_grandparent_fallback(tmp_path):
    root = tmp_path / "corpus"
    (root / "graphify-out").mkdir(parents=True)
    graph_path = root / "graphify-out" / "graph.json"
    nodes = [
        {"id": "h1", "label": "handoff", "file_type": "document", "source_file": "HANDOFF.md"},
        {"id": "k1", "label": "keep", "file_type": "document", "source_file": "KEEP.md"},
    ]
    _write_graph(graph_path, nodes, [], [])
    # Runbook-style call: absolute prune path, NO root passed.
    deleted_abs = [str(root / "HANDOFF.md")]
    G = build_merge([], graph_path, prune_sources=deleted_abs, dedup=False)
    labels = {d["label"] for _, d in G.nodes(data=True)}
    assert "handoff" not in labels, "deleted file's ghost node must be pruned without root"
    assert "keep" in labels


def test_prune_without_root_uses_graphify_root_marker(tmp_path):
    # graph.json not under a <root>/graphify-out layout, so grandparent wouldn't
    # help — the committed .graphify_root marker must be honored instead.
    out = tmp_path / "out"
    out.mkdir()
    graph_path = out / "graph.json"
    real_root = tmp_path / "elsewhere" / "repo"
    real_root.mkdir(parents=True)
    (out / ".graphify_root").write_text(str(real_root), encoding="utf-8")
    nodes = [{"id": "h1", "label": "handoff", "file_type": "document", "source_file": "HANDOFF.md"}]
    _write_graph(graph_path, nodes, [], [])
    assert _infer_merge_root(graph_path) == str(real_root.resolve())
    G = build_merge([], graph_path, prune_sources=[str(real_root / "HANDOFF.md")], dedup=False)
    assert "handoff" not in {d["label"] for _, d in G.nodes(data=True)}


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_prune_matches_across_symlinked_root(tmp_path):
    """A symlinked scan root (macOS /var -> /private/var, symlinked home/worktree)
    makes the absolute prune path and the resolved root differ by prefix. The prune
    must still match — lexical relative_to fails, so normalization resolves both
    sides. Regression for the edge case a canonical-tmp unit test can't reach."""
    real = tmp_path / "real"
    (real / "graphify-out").mkdir(parents=True)
    link = tmp_path / "link"
    os.symlink(real, link)
    graph_path = real / "graphify-out" / "graph.json"
    _write_graph(graph_path, [
        {"id": "h1", "label": "handoff", "file_type": "document", "source_file": "HANDOFF.md"},
        {"id": "k1", "label": "keep", "file_type": "document", "source_file": "KEEP.md"},
    ], [], [])
    # prune path addressed via the SYMLINK, root resolved to the real dir
    G = build_merge([], graph_path=graph_path,
                    prune_sources=[str(link / "HANDOFF.md")], root=str(real), dedup=False)
    labels = {d["label"] for _, d in G.nodes(data=True)}
    assert "handoff" not in labels and "keep" in labels
