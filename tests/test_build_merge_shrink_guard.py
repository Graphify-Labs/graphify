"""build_merge safety rails: the #479 shrink guard rework (#2497) and
root-mismatch prune fallbacks (#2446).

- #2497: the original shrink guard compared the new node count against
  `existing_nodes` AFTER the replace-on-re-extract rebind had already removed
  the re-extracted sources' old nodes — so it could never fire when it
  mattered, and was skipped outright whenever prune_sources was passed. A
  broken partial re-extract silently destroyed the graph (12->3 observed).
  The guard now diffs the ON-DISK baseline by node identity (mirroring
  watch._check_shrink) and excuses only losses explained by this run's own
  re-extraction (same tier) or an explicit prune.
- #2446: with `root` omitted and a non-standard layout (graph.json not under
  <root>/graphify-out/), the inferred root was wrong, absolute prune_sources
  matched nothing, and build_merge reported "already clean" while counting
  EVERY prune entry as pruned-from. Now: a derived-root fallback
  (suffix-matching absolute prune paths against stored relative source_files),
  an accurate matched-entry count, and a WARNING instead of "already clean"
  on a true zero-match.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import graphify.build as buildmod
from graphify.build import build_merge, merge_raw_extraction


def _node(i: int, sf: str) -> dict:
    """Deterministic AST-tier node dict for source file *sf*."""
    stem = sf.replace("/", "_").replace(".", "_")
    return {
        "id": f"{stem}_n{i}",
        "label": f"{sf} node {i}",
        "file_type": "document",
        "source_file": sf,
        "source_location": f"L{i + 1}",
        "_origin": "ast",
    }


def _write_graph(graph_path: Path, nodes, edges=(), hyperedges=()) -> None:
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps({"nodes": list(nodes), "edges": list(edges),
                    "hyperedges": list(hyperedges)}),
        encoding="utf-8",
    )


def _seed_12(tmp_path: Path) -> Path:
    """Standard layout, 12 nodes: 10 from a.md + 2 from b.md."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        gp,
        [_node(i, "a.md") for i in range(10)] + [_node(i, "b.md") for i in range(2)],
    )
    return gp


# ── #2497: identity-based shrink guard ─────────────────────────────────────────

def test_legit_prune_driven_reduction_allowed(tmp_path):
    """The guard is now ACTIVE with prune_sources, but a prune-explained loss
    passes: 12 nodes, prune b.md -> 10, no raise."""
    gp = _seed_12(tmp_path)
    G = build_merge([], gp, prune_sources=["b.md"], dedup=False)
    assert G.number_of_nodes() == 10
    assert not any(d.get("source_file") == "b.md" for _, d in G.nodes(data=True))


def test_legit_replacement_reduction_allowed(tmp_path):
    """No #1116 false-refuse: a.md re-extracted with fewer symbols (10 -> 7)
    legitimately shrinks 12 -> 9."""
    gp = _seed_12(tmp_path)
    chunk = {"nodes": [_node(i, "a.md") for i in range(7)], "edges": []}
    G = build_merge([chunk], gp, prune_sources=None, dedup=False)
    assert G.number_of_nodes() == 9


def test_unexplained_loss_blocked(tmp_path, monkeypatch):
    """A build that drops a node from an UNTOUCHED file (neither re-extracted
    nor pruned this run) must raise instead of silently destroying it — the
    exact failure the dead #479 guard waved through (#2497)."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        gp,
        [_node(i, "a.md") for i in range(10)]
        + [_node(0, "c.md"), _node(1, "c.md")],
    )
    chunk_for_a = {"nodes": [_node(i, "a.md") for i in range(10)], "edges": []}

    real_build = buildmod.build

    def _broken_build(chunks, **kwargs):
        G = real_build(chunks, **kwargs)
        G.remove_node("c_md_n0")  # untouched c.md node silently lost
        return G

    monkeypatch.setattr(buildmod, "build", _broken_build)
    with pytest.raises(ValueError, match="neither re-extracted nor pruned"):
        build_merge([chunk_for_a], gp, dedup=False)


def test_grow_and_equal_unaffected(tmp_path):
    gp = _seed_12(tmp_path)
    # equal: a.md re-emits its 10 identical nodes -> still 12
    chunk = {"nodes": [_node(i, "a.md") for i in range(10)], "edges": []}
    assert build_merge([chunk], gp, dedup=False).number_of_nodes() == 12
    # grow: a.md re-emits 11 nodes -> 13
    chunk2 = {"nodes": [_node(i, "a.md") for i in range(11)], "edges": []}
    assert build_merge([chunk2], gp, dedup=False).number_of_nodes() == 13


def test_replacement_is_reported_and_own_file_loss_excused(tmp_path, capsys):
    """Visibility (#2497): the replace-on-re-extract rebind is announced on
    stderr, and a re-extract that under-produces for its OWN file is excused
    (owned by the extraction layer's incomplete-build guard, #1951)."""
    gp = _seed_12(tmp_path)
    chunk = {"nodes": [_node(0, "a.md")], "edges": []}
    G = build_merge([chunk], gp, dedup=False)  # must not raise
    assert G.number_of_nodes() == 3  # 2 b.md + 1 fresh a.md
    assert "Replaced 10 node(s)" in capsys.readouterr().err


def test_dedup_skip_preserved(tmp_path, monkeypatch):
    """dedup=True legitimately merges ids, so the guard stays off there — even
    for a loss the dedup=False path would refuse."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        gp,
        [_node(i, "a.md") for i in range(10)]
        + [_node(0, "c.md"), _node(1, "c.md")],
    )
    chunk_for_a = {"nodes": [_node(i, "a.md") for i in range(10)], "edges": []}

    real_build = buildmod.build

    def _broken_build(chunks, **kwargs):
        G = real_build(chunks, **kwargs)
        if "c_md_n0" in G:
            G.remove_node("c_md_n0")
        return G

    monkeypatch.setattr(buildmod, "build", _broken_build)
    G = build_merge([chunk_for_a], gp, dedup=True)  # no raise
    assert "c_md_n0" not in G


def test_no_existing_graph_path_unchanged(tmp_path):
    """Fresh/no-graph merges never trip the guard."""
    gp = tmp_path / "graphify-out" / "graph.json"  # does not exist
    G = build_merge([{"nodes": [_node(0, "a.md")], "edges": []}], gp, dedup=False)
    assert G.number_of_nodes() == 1
    G2 = build_merge([], tmp_path / "elsewhere" / "graph.json", dedup=False)
    assert G2.number_of_nodes() == 0


# ── #2446: absolute prune_sources with a wrong/missing inferred root ──────────

def test_absolute_prune_custom_layout_derives_root(tmp_path):
    """graph.json directly in <root> (no graphify-out dir, no marker): the
    grandparent heuristic guesses wrong, so absolute prune entries used to
    match nothing and silently no-op. The derived-root fallback must recover
    the scan root by suffix-matching and prune correctly."""
    root = tmp_path / "proj"
    root.mkdir()
    gp = root / "graph.json"
    _write_graph(gp, [_node(i, "a.md") for i in range(2)] + [_node(0, "b.md")])
    G = build_merge([], gp, prune_sources=[str(root / "b.md")], dedup=False)
    sfs = {d.get("source_file") for _, d in G.nodes(data=True)}
    assert "b.md" not in sfs, "absolute prune must remove the file's nodes (#2446)"
    assert G.number_of_nodes() == 2


def test_absolute_prune_standard_layout_marker_still_prunes(tmp_path):
    """Regression guard for #1571/#2012: the standard layout with a
    .graphify_root marker keeps working without root=."""
    root = tmp_path / "repo"
    out = root / "graphify-out"
    out.mkdir(parents=True)
    (out / ".graphify_root").write_text(str(root), encoding="utf-8")
    gp = out / "graph.json"
    _write_graph(gp, [_node(0, "keep.md"), _node(0, "gone.md")])
    G = build_merge([], gp, prune_sources=[str(root / "gone.md")], dedup=False)
    assert {d["source_file"] for _, d in G.nodes(data=True)} == {"keep.md"}


def test_zero_match_prune_warns_instead_of_already_clean(tmp_path, capsys):
    """A prune set that matches nothing must WARN with samples (prune entry +
    stored source_file) and suggest root=, not claim the graph is clean."""
    root = tmp_path / "repo"
    (root / "graphify-out").mkdir(parents=True)
    gp = root / "graphify-out" / "graph.json"
    _write_graph(gp, [_node(0, "a.md")])
    G = build_merge(
        [], gp, prune_sources=["/nowhere/else/x.md"], dedup=False
    )
    assert G.number_of_nodes() == 1
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "x.md" in err, "must name a sample prune entry"
    assert "a.md" in err, "must name a sample stored source_file"
    assert "root" in err
    assert "already clean" not in err


def test_partial_match_reports_only_matched_entry_count(tmp_path, capsys):
    """With [abs(b.md), abs(nonexistent.md)], the pruned-from file count must
    be 1 (the entry that matched), not len(prune_sources) == 2."""
    root = tmp_path / "repo"
    (root / "graphify-out").mkdir(parents=True)
    gp = root / "graphify-out" / "graph.json"
    _write_graph(gp, [_node(0, "a.md"), _node(0, "b.md"), _node(1, "b.md")])
    G = build_merge(
        [], gp,
        prune_sources=[str(root / "b.md"), str(root / "nonexistent.md")],
        dedup=False,
    )
    assert G.number_of_nodes() == 1
    err = capsys.readouterr().err
    assert "Pruned 2 node(s) from 1 deleted or excluded source file(s)" in err


def test_merge_raw_extraction_absolute_prune_custom_layout(tmp_path):
    """merge_raw_extraction (the raw --no-cluster incremental path) shares the
    derived-root fallback (#2446 parity)."""
    root = tmp_path / "proj"
    root.mkdir()
    gp = root / "graph.json"
    _write_graph(gp, [_node(0, "a.md"), _node(0, "b.md")])
    new = {"nodes": [], "edges": [], "hyperedges": []}
    merged = merge_raw_extraction(new, gp, prune_sources=[str(root / "b.md")])
    sfs = {n.get("source_file") for n in merged["nodes"]}
    assert sfs == {"a.md"}, "raw path must prune the absolute entry too (#2446)"
