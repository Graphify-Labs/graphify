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

import networkx as nx
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
    """Write a two-file graph.json with per-file and cross-file hyperedges."""
    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    nodes = [
        {"id": "a1", "label": "a1", "file_type": "document", "source_file": "a.md"},
        {"id": "a2", "label": "a2", "file_type": "document", "source_file": "a.md"},
        {"id": "a3", "label": "a3", "file_type": "document", "source_file": "a.md"},
        {"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"},
        {"id": "b2", "label": "b2", "file_type": "document", "source_file": "b.md"},
        {"id": "b3", "label": "b3", "file_type": "document", "source_file": "b.md"},
    ]
    hyperedges = [
        {"id": "he_a", "label": "flow A", "source_file": "a.md", "nodes": ["a1", "a2", "a3"]},
        {"id": "he_b", "label": "flow B", "source_file": "b.md", "nodes": ["b1", "b2", "b3"]},
        {"id": "he_global", "label": "cross-file flow", "nodes": ["a1", "b1", "b2"]},
    ]
    _write_graph(graph_path, nodes, [], hyperedges)
    return root, graph_path


def test_update_preserves_hyperedges_of_unchanged_files(tmp_path):
    """#1574: an unchanged file's hyperedges must survive an incremental update."""
    root, graph_path = _seed_two_file_graph(tmp_path)
    # Re-extract only b.md, with a fresh hyperedge for it.
    new_chunk = {
        "nodes": [
            {"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"},
            {"id": "b2", "label": "b2", "file_type": "document", "source_file": "b.md"},
            {"id": "b3", "label": "b3", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "label": "flow B v2", "source_file": "b.md", "nodes": ["b1", "b2", "b3"]}],
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
        "nodes": [
            {"id": "b1", "label": "b1", "file_type": "document", "source_file": "b.md"},
            {"id": "b2", "label": "b2", "file_type": "document", "source_file": "b.md"},
            {"id": "b3", "label": "b3", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [],
        "hyperedges": [{"id": "he_b_v2", "source_file": "b.md", "nodes": ["b1", "b2", "b3"]}],
    }
    G = build_merge([new_chunk], graph_path, dedup=False)  # no root
    ids = _he_ids(G)
    assert {"he_a", "he_global", "he_b_v2"} <= ids
    assert "he_b" not in ids


def test_deleted_file_hyperedges_are_pruned(tmp_path):
    """A deleted file's own hyperedges go, and a cross-file group left under the minimum goes with them."""
    root, graph_path = _seed_two_file_graph(tmp_path)
    deleted_abs = [str(root / "a.md")]
    G = build_merge([], graph_path, prune_sources=deleted_abs, dedup=False, root=root)
    ids = _he_ids(G)
    assert "he_a" not in ids        # deleted file's hyperedge pruned
    assert "he_b" in ids            # untouched file's hyperedge kept
    assert "he_global" not in ids   # deletion leaves fewer than 3 members
    # and its node is gone too
    assert "a1" not in set(G.nodes)


# ── minimum cardinality on a plain --update (no prune_sources) ───────────────

def _seed_single_node_graph(tmp_path, nodes):
    """Write a graph.json holding just *nodes* and no hyperedges."""
    root = tmp_path / "corpus"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path, nodes, [], [])
    return root, graph_path


def test_update_without_prune_drops_hyperedge_collapsed_by_doc_twin_fold(tmp_path):
    """A plain --update never reaches the prune branch, yet a new chunk can still
    carry a group whose members collapse to two distinct ids once build_from_json
    folds `<slug>` onto `<slug>_doc`. That pair must not be persisted."""
    root, graph_path = _seed_single_node_graph(
        tmp_path, [{"id": "z1", "label": "z1", "file_type": "document", "source_file": "z.md"}])
    chunk = {
        "nodes": [
            {"id": "docs_guide", "label": "Guide", "file_type": "document", "source_file": "docs/guide.md"},
            {"id": "docs_guide_doc", "label": "Guide (semantic)", "file_type": "document",
             "source_file": "docs/guide.md"},
            {"id": "docs_other_doc", "label": "Other", "file_type": "document", "source_file": "docs/other.md"},
        ],
        "edges": [],
        "hyperedges": [{"id": "he_twins", "source_file": "docs/other.md",
                        "nodes": ["docs_guide", "docs_guide_doc", "docs_other_doc"]}],
    }
    G = build_merge([chunk], graph_path, dedup=False, root=root)
    assert "he_twins" not in _he_ids(G)


_TWO_NODES = [
    {"id": "a1", "label": "a1", "file_type": "document", "source_file": "a.md"},
    {"id": "a2", "label": "a2", "file_type": "document", "source_file": "a.md"},
]


def _fake_build_returning(hyperedges):
    """Stand-in for build(): the seeded nodes (so the #479 shrink guard stays quiet)
    plus whatever hyperedge metadata the test wants to smuggle past build()."""
    def fake_build(*args, **kwargs):
        """Stand in for build(), returning the seeded nodes plus canned hyperedge metadata."""
        G = nx.Graph()
        for n in _TWO_NODES:
            G.add_node(n["id"], **n)
        if hyperedges is not None:
            G.graph["hyperedges"] = hyperedges
        return G
    return fake_build


def test_update_without_prune_still_revalidates_hyperedges_against_final_graph(tmp_path, monkeypatch):
    """The final revalidation gate must run whether or not a prune happened: a
    hyperedge that leaves build() with a dangling member and fewer than three
    survivors is dropped on a no-prune --update too."""
    root, graph_path = _seed_single_node_graph(tmp_path, _TWO_NODES)
    monkeypatch.setattr(
        "graphify.build.build",
        _fake_build_returning([{"id": "he_dangling", "nodes": ["a1", "a2", "ghost"]}]),
    )
    G = build_merge([], graph_path, dedup=False, root=root)
    assert "he_dangling" not in _he_ids(G)


def test_update_without_prune_keeps_absent_hyperedge_key_absent(tmp_path, monkeypatch):
    """#2485: a graph that never engaged hyperedge metadata has NO `hyperedges` key,
    and to_json warns on that absence when the file on disk already holds some.
    The unconditional revalidation must not manufacture an empty list and hide
    that diagnostic."""
    root, graph_path = _seed_single_node_graph(tmp_path, _TWO_NODES)
    monkeypatch.setattr("graphify.build.build", _fake_build_returning(None))
    G = build_merge([], graph_path, dedup=False, root=root)
    assert "hyperedges" not in G.graph


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


def test_reextracted_file_in_prune_sources_is_not_deleted(tmp_path):
    """#1796: a file present in BOTH new_chunks (re-extracted) and prune_sources
    must be REPLACED, not deleted. The old edit-workflow passed the changed file
    in prune_sources; combined with dedup keeping a same-label node, that used to
    silently delete the freshly re-extracted concept. Replace wins over delete."""
    graph_path = tmp_path / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    _write_graph(
        graph_path,
        nodes=[
            {"id": "foo_widget_cache", "label": "Widget Cache Design",
             "file_type": "concept", "source_file": "docs/foo.md", "source_location": "L1"},
            {"id": "bar_other", "label": "Other",
             "file_type": "concept", "source_file": "docs/bar.md", "source_location": "L1"},
        ],
        edges=[],
        hyperedges=[],
    )
    # foo.md edited: same-label node re-extracted (new content/line)
    new_chunk = {"nodes": [
        {"id": "foo_widget_cache", "label": "Widget Cache Design",
         "file_type": "concept", "source_file": "docs/foo.md", "source_location": "L2"}
    ], "edges": []}

    G = build_merge([new_chunk], graph_path=str(graph_path),
                    prune_sources=["docs/foo.md"], root=str(tmp_path))
    labels = {G.nodes[n].get("label") for n in G.nodes()}
    assert "Widget Cache Design" in labels, "re-extracted node was wrongly pruned"


def test_genuine_deletion_still_prunes(tmp_path):
    """#1796 guard must not break real deletions: a file in prune_sources but NOT
    in new_chunks is still removed."""
    graph_path = tmp_path / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    _write_graph(
        graph_path,
        nodes=[
            {"id": "foo_widget_cache", "label": "Widget Cache Design",
             "file_type": "concept", "source_file": "docs/foo.md", "source_location": "L1"},
            {"id": "bar_other", "label": "Other",
             "file_type": "concept", "source_file": "docs/bar.md", "source_location": "L1"},
        ],
        edges=[],
        hyperedges=[],
    )
    new_chunk = {"nodes": [
        {"id": "foo_widget_cache", "label": "Widget Cache Design",
         "file_type": "concept", "source_file": "docs/foo.md", "source_location": "L2"}
    ], "edges": []}
    # bar.md genuinely deleted (not re-extracted)
    G = build_merge([new_chunk], graph_path=str(graph_path),
                    prune_sources=["docs/bar.md"], root=str(tmp_path))
    labels = {G.nodes[n].get("label") for n in G.nodes()}
    assert "Other" not in labels, "genuinely deleted file's node should be pruned"
    assert "Widget Cache Design" in labels


# ── #2012: form-insensitive prune (absolute node vs relative prune, and back) ──

def test_prune_matches_node_stored_absolute_against_relative_delete(tmp_path):
    """#2012: a node whose source_file survived in ABSOLUTE form must still be
    pruned when the deletion is expressed relative to root. The runbook calls
    build_merge WITHOUT root, so build() does not re-normalize the node's stored
    absolute source_file; the old prune membership test then compared that raw
    absolute string against a prune_set that only held the relative forms, so the
    node slipped through and a deleted file's graph survived silently. build_merge
    now normalizes the node side too + an absolute-identity fallback."""
    root = tmp_path / "corpus"
    (root / "graphify-out").mkdir(parents=True)
    graph_path = root / "graphify-out" / "graph.json"
    nodes = [
        # gone.py's node kept an ABSOLUTE source_file (a semantic subagent wrote
        # it that way, #932); keep.py's is relative.
        {"id": "g1", "label": "gone", "file_type": "code",
         "source_file": str(root / "gone.py")},
        {"id": "k1", "label": "keep", "file_type": "code", "source_file": "keep.py"},
    ]
    edges = [
        {"source": "g1", "target": "k1", "type": "calls",
         "source_file": str(root / "gone.py")},
    ]
    _write_graph(graph_path, nodes, edges, [])
    # Runbook-style: NO root passed (eff_root inferred from the graphify-out
    # grandparent), so build() leaves the absolute node form intact. Deletion is
    # expressed RELATIVE — a third form vs the stored absolute node.
    G = build_merge([], graph_path, prune_sources=["gone.py"], dedup=False)
    labels = {d["label"] for _, d in G.nodes(data=True)}
    assert "gone" not in labels, "absolute-stored node not pruned by relative delete (#2012)"
    assert "keep" in labels
    assert G.number_of_edges() == 0, "edge from the deleted file must be pruned too (#2012)"


def test_prune_reextracted_absolute_node_not_deleted(tmp_path):
    """#1796 protection must hold in absolute-identity space too: a file present
    in BOTH new_chunks and prune_sources (in mismatched forms) is REPLACED, not
    deleted — the #2012 form-insensitive match must not resurrect the delete for
    a re-extracted file."""
    root = tmp_path / "corpus"
    (root / "graphify-out").mkdir(parents=True)
    graph_path = root / "graphify-out" / "graph.json"
    _write_graph(graph_path, [
        {"id": "g1", "label": "gone", "file_type": "code",
         "source_file": str(root / "mod.py")},
    ], [], [])
    # Re-extracted with a RELATIVE source_file; prune lists it RELATIVE too.
    # No root passed (runbook), so the stored absolute node is not re-normalized.
    new_chunk = {"nodes": [
        {"id": "g1", "label": "gone", "file_type": "code", "source_file": "mod.py"},
    ], "edges": []}
    G = build_merge([new_chunk], graph_path, prune_sources=["mod.py"], dedup=False)
    labels = {d["label"] for _, d in G.nodes(data=True)}
    assert "gone" in labels, "re-extracted file wrongly pruned across mismatched forms (#2012/#1796)"


def test_graphify_root_marker_with_a_utf8_bom_still_resolves(tmp_path):
    """A marker written by Windows PowerShell 5.1 carries a UTF-8 BOM (#3028).

    `Out-File -Encoding utf8` on 5.1 always prepends EF BB BF — there is no
    BOM-less utf8 there — and `str.strip()` does not remove U+FEFF, so the BOM
    survived into the recorded path. Worse than an error: `﻿C:\...` is no
    longer drive-qualified, so `Path.resolve()` treated it as relative and silently
    joined it onto the cwd. Reading with `utf-8-sig` drops an optional BOM and
    leaves a BOM-less file untouched, so existing broken checkouts heal in place.
    """
    out = tmp_path / "out"
    out.mkdir()
    graph_path = out / "graph.json"
    real_root = tmp_path / "elsewhere" / "repo"
    real_root.mkdir(parents=True)
    (out / ".graphify_root").write_bytes(
        b"\xef\xbb\xbf" + str(real_root).encode("utf-8")
    )

    resolved = _infer_merge_root(graph_path)
    assert resolved == str(real_root.resolve())
    assert "﻿" not in (resolved or "")
