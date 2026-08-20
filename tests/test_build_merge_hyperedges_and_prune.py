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


# ── #2908: skill --update prunes excluded_files alongside deleted_files ──────────

def test_skill_update_prunes_excluded_files_and_preserves_reinclusion(tmp_path):
    """#2908: when a file leaves scan scope (.graphifyignore), detect_incremental
    places it in excluded_files. The skill --update flow must include excluded_files
    in prune_sources so its graph contributions are removed when save_manifest
    drops the file from the manifest, leaving subsequent runs clean and allowing
    clean re-inclusion when unignored."""
    from graphify.detect import detect, detect_incremental, save_manifest
    from graphify.extract import extract
    from graphify.build import build
    from graphify.cluster import cluster
    from graphify.export import to_json
    from graphify.cli import _stamped_manifest_files

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    a_py = corpus / "A.py"
    a_py.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    out_dir = corpus / "graphify-out"
    out_dir.mkdir()
    graph_path = out_dir / "graph.json"
    manifest_path = out_dir / "manifest.json"

    # 1. Initial build & manifest
    det = detect(corpus)
    ast_res = extract([a_py], root=corpus)
    G0 = build([ast_res], root=corpus, directed=False)
    to_json(G0, cluster(G0), str(graph_path), force=True)

    _manifest_files = _stamped_manifest_files(det["files"], ast_res, corpus)
    _scan = {f for fl in det["files"].values() for f in fl}
    save_manifest(_manifest_files, str(manifest_path), root=corpus, scan_corpus=_scan)

    # Initial assertions
    g0_data = json.loads(graph_path.read_text(encoding="utf-8"))
    m0_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(n.get("source_file") == "A.py" for n in g0_data["nodes"])
    assert "A.py" in m0_data

    # 2. Scope change: A.py is added to .graphifyignore while remaining on disk
    (corpus / ".graphifyignore").write_text("A.py\n", encoding="utf-8")
    assert a_py.exists()

    inc1 = detect_incremental(corpus, str(manifest_path))
    assert inc1.get("deleted_files") == []
    assert len(inc1.get("excluded_files", [])) == 1
    assert Path(inc1["excluded_files"][0]).name == "A.py"

    # 3. Execute the skill --update merge sequence
    deleted = list(inc1.get("deleted_files", []))
    excluded = list(inc1.get("excluded_files", []))
    prune = deleted + excluded or None

    assert prune is not None
    assert any("A.py" in str(p) for p in prune)

    new_extraction = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    G1 = build_merge(
        [new_extraction],
        graph_path=str(graph_path),
        prune_sources=prune,
        root=str(corpus),
        directed=False,
    )
    to_json(G1, cluster(G1), str(graph_path), force=True)

    # Skill save_manifest step
    _manifest_files_1 = _stamped_manifest_files(inc1["files"], new_extraction, corpus)
    _scan_1 = {f for fl in inc1["files"].values() for f in fl}
    save_manifest(_manifest_files_1, str(manifest_path), root=corpus, scan_corpus=_scan_1)

    # Assert A.py is removed from graph.json and manifest.json
    g1_data = json.loads(graph_path.read_text(encoding="utf-8"))
    m1_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not any(n.get("source_file") == "A.py" for n in g1_data["nodes"])
    assert "A.py" not in m1_data

    # 4. Second incremental cycle (steady state)
    inc2 = detect_incremental(corpus, str(manifest_path))
    assert inc2.get("deleted_files") == []
    assert inc2.get("excluded_files") == []
    assert inc2.get("new_total") == 0

    g2_data = json.loads(graph_path.read_text(encoding="utf-8"))
    m2_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not any(n.get("source_file") == "A.py" for n in g2_data["nodes"])
    assert "A.py" not in m2_data

    # 5. Re-inclusion: remove .graphifyignore and modify A.py
    (corpus / ".graphifyignore").unlink()
    a_py.write_text("def hello():\n    return 'restored'\n", encoding="utf-8")

    inc3 = detect_incremental(corpus, str(manifest_path))
    assert inc3.get("deleted_files") == []
    assert inc3.get("excluded_files") == []
    assert any(Path(p).name == "A.py" for p in inc3.get("new_files", {}).get("code", []))

    ast_res3 = extract([a_py], root=corpus)
    G3 = build_merge(
        [ast_res3],
        graph_path=str(graph_path),
        prune_sources=inc3.get("deleted_files") or None,
        root=str(corpus),
        directed=False,
    )
    to_json(G3, cluster(G3), str(graph_path), force=True)

    _manifest_files_3 = _stamped_manifest_files(inc3["files"], ast_res3, corpus)
    _scan_3 = {f for fl in inc3["files"].values() for f in fl}
    save_manifest(_manifest_files_3, str(manifest_path), root=corpus, scan_corpus=_scan_3)

    g3_data = json.loads(graph_path.read_text(encoding="utf-8"))
    m3_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(n.get("source_file") == "A.py" for n in g3_data["nodes"])
    assert "A.py" in m3_data
