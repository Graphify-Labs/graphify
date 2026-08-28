"""`graphify merge-graphs` tolerates inputs that disagree on graph type (#1606).

Per-repo graph.json files written by different extract paths at different times
don't always agree on the `directed` / `multigraph` flags. compose requires one
uniform type, so a mixed set used to crash with an unhandled NetworkXError. The
handler now normalizes every input to a plain undirected Graph before composing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _run(args, cwd):
    return subprocess.run([PYTHON, "-m", "graphify"] + args, cwd=cwd,
                          capture_output=True, text=True)


def _write(p: Path, directed: bool, multigraph: bool, node_id: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "directed": directed, "multigraph": multigraph, "graph": {},
        "nodes": [{"id": node_id}], "links": [],
    }))


def test_merge_graphs_mixed_directed_and_multigraph(tmp_path):
    a = tmp_path / "r1" / "graphify-out" / "graph.json"
    b = tmp_path / "r2" / "graphify-out" / "graph.json"
    c = tmp_path / "r3" / "graphify-out" / "graph.json"
    _write(a, directed=True, multigraph=False, node_id="x")    # DiGraph
    _write(b, directed=False, multigraph=False, node_id="y")   # Graph
    _write(c, directed=False, multigraph=True, node_id="z")    # MultiGraph
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), str(c), "--out", str(out)], tmp_path)
    assert r.returncode == 0, f"merge crashed: {r.stderr}"
    assert out.exists()
    data = json.loads(out.read_text())
    ids = {n["id"] for n in data["nodes"]}
    # every input's node survives, normalized into one undirected simple graph
    assert {"r1::x", "r2::y", "r3::z"} <= ids or len(ids) == 3
    assert data.get("directed") is False
    assert data.get("multigraph") is False


def test_merge_graphs_same_named_repo_dirs_do_not_collapse(tmp_path):
    # #1729: two graphs under a same-named repo dir (src/graphify-out and
    # frontend/src/graphify-out both → tag "src") share the `src::` prefix, so a
    # bare `app` node from each collapsed into one — silently merging unrelated
    # entities and inventing cross-runtime edges. Distinct tags must keep them apart.
    a = tmp_path / "src" / "graphify-out" / "graph.json"
    b = tmp_path / "frontend" / "src" / "graphify-out" / "graph.json"
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(json.dumps({"directed": False, "multigraph": False, "nodes": [
        {"id": "app", "label": "app.js", "source_file": "app.js"}], "links": []}))
    b.write_text(json.dumps({"directed": False, "multigraph": False, "nodes": [
        {"id": "app", "label": "App.jsx", "source_file": "App.jsx"}], "links": []}))
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    app_nodes = [n for n in data["nodes"] if n["id"].endswith("::app")]
    assert len(app_nodes) == 2, f"both app nodes must survive; got {[n['id'] for n in app_nodes]}"
    labels = {n.get("label") for n in app_nodes}
    assert labels == {"app.js", "App.jsx"}, f"both entities preserved; got {labels}"


def test_distinct_repo_tags_unit(tmp_path):
    from graphify.build import distinct_repo_tags
    # distinct repo dirs pass through unchanged
    assert distinct_repo_tags([
        Path("backend/graphify-out/graph.json"),
        Path("web/graphify-out/graph.json"),
    ]) == ["backend", "web"]
    # same-named repo dirs are widened to stay distinct
    tags = distinct_repo_tags([
        Path("proj/src/graphify-out/graph.json"),
        Path("proj/frontend/src/graphify-out/graph.json"),
    ])
    assert len(set(tags)) == 2, tags
    # a repeated dir name triple still yields all-distinct tags (index fallback)
    tags3 = distinct_repo_tags([
        Path("a/src/graphify-out/graph.json"),
        Path("b/src/graphify-out/graph.json"),
        Path("c/src/graphify-out/graph.json"),
    ])
    assert len(set(tags3)) == 3, tags3


def test_merge_graphs_preserves_import_edge_direction(tmp_path):
    # #2261: merge-graphs loaded graph.json into an undirected nx.Graph without
    # stashing _src/_tgt directional markers, causing node_link_data to re-serialize
    # edges based on arbitrary node ordering and reversing import edge direction whenever
    # target node index < source node index (turning imports into self-imports/reversed links).
    a = tmp_path / "repo1" / "graphify-out" / "graph.json"
    b = tmp_path / "repo2" / "graphify-out" / "graph.json"
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)

    # Note: collections comes BEFORE rota in nodes list, so collections has a smaller index
    a.write_text(json.dumps({
        "directed": False,
        "multigraph": False,
        "nodes": [
            {"id": "collections", "label": "collections.js"},
            {"id": "empresa", "label": "empresa.js"},
            {"id": "logger", "label": "logger.js"},
            {"id": "rota", "label": "rota.js"},
        ],
        "links": [
            {"source": "rota", "target": "collections", "relation": "imports_from", "context": "import"},
            {"source": "rota", "target": "empresa", "relation": "imports_from", "context": "import"},
            {"source": "rota", "target": "logger", "relation": "imports_from", "context": "import"},
        ],
    }))

    b.write_text(json.dumps({
        "directed": False,
        "multigraph": False,
        "nodes": [
            {"id": "main", "label": "main.js"},
            {"id": "utils", "label": "utils.js"},
        ],
        "links": [
            {"source": "main", "target": "utils", "relation": "imports_from", "context": "import"},
        ],
    }))

    out = tmp_path / "merged.json"
    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, f"merge failed: {r.stderr}"

    data = json.loads(out.read_text(encoding="utf-8"))

    # 1. Node count & edge count correct
    assert len(data["nodes"]) == 6
    assert len(data["links"]) == 4

    # 2. Repo prefixes applied
    node_ids = {n["id"] for n in data["nodes"]}
    expected_ids = {
        "repo1::collections", "repo1::empresa", "repo1::logger", "repo1::rota",
        "repo2::main", "repo2::utils"
    }
    assert node_ids == expected_ids

    # 3. Import relationships preserve original direction (source=rota, target=collections/empresa/logger)
    #    and no import edge becomes a self-import or reversed.
    repo1_links = [l for l in data["links"] if l["source"].startswith("repo1::") or l["target"].startswith("repo1::")]
    assert len(repo1_links) == 3

    for link in repo1_links:
        src = link["source"]
        tgt = link["target"]
        assert src != tgt, f"import edge became a self-import: {link}"
        assert src == "repo1::rota", f"expected source repo1::rota, got {src} in link {link}"
        assert tgt in {"repo1::collections", "repo1::empresa", "repo1::logger"}, f"unexpected target {tgt} in link {link}"

    repo2_link = [l for l in data["links"] if l["source"].startswith("repo2::")][0]
    assert repo2_link["source"] == "repo2::main"
    assert repo2_link["target"] == "repo2::utils"


def _write_with_hyperedges(p: Path, node_ids: list[str], hyperedges: list[dict],
                           *, top_level_only: bool = False):
    # Mirrors to_json's dual-slot shape: hyperedges live top-level AND under
    # the node_link graph attrs. top_level_only drops the nested slot to model
    # older writers (#2485).
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "directed": False, "multigraph": False,
        "graph": {} if top_level_only else {"hyperedges": hyperedges},
        "nodes": [{"id": n} for n in node_ids], "links": [],
        "hyperedges": hyperedges,
    }
    p.write_text(json.dumps(data))


def test_merge_graphs_carries_hyperedges_from_all_inputs(tmp_path):
    # #2484: prefix_graph_for_global never rewrote G.graph["hyperedges"], and
    # nx.compose's dict.update graph-attr merge clobbered each prior input's
    # list, so at best the LAST graph's hyperedges survived — with stale,
    # unprefixed member ids. Both inputs' hyperedges must reach the output,
    # relabeled to the prefixed node ids, in BOTH persistence slots.
    a = tmp_path / "alpha" / "graphify-out" / "graph.json"
    b = tmp_path / "beta" / "graphify-out" / "graph.json"
    _write_with_hyperedges(a, ["x", "y"], [{"id": "h_alpha", "nodes": ["x", "y"]}])
    _write_with_hyperedges(b, ["p", "q"], [{"id": "h_beta", "nodes": ["p", "q"]}])
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())

    hyperedges = data.get("hyperedges")
    assert isinstance(hyperedges, list), "top-level hyperedges slot must be written"
    assert {h["id"] for h in hyperedges} == {"alpha::h_alpha", "beta::h_beta"}
    assert len(hyperedges) == 2

    # every member id must resolve in the merged (prefixed) node set
    node_ids = {n["id"] for n in data["nodes"]}
    for h in hyperedges:
        assert set(h["nodes"]) <= node_ids, f"dangling members in {h}"

    # nested slot mirrors the top-level one (to_json's dual-slot shape)
    assert data["graph"]["hyperedges"] == hyperedges


def test_merge_graphs_hyperedges_dedup_on_shared_prefixed_id(tmp_path):
    # Idempotence: a duplicated hyperedge id within an input must not produce
    # duplicate entries in the merged output (attach_hyperedges dedups by id).
    a = tmp_path / "alpha" / "graphify-out" / "graph.json"
    b = tmp_path / "beta" / "graphify-out" / "graph.json"
    he = {"id": "h_alpha", "nodes": ["x"]}
    _write_with_hyperedges(a, ["x"], [he, dict(he)])
    _write_with_hyperedges(b, ["p"], [{"id": "h_beta", "nodes": ["p"]}])
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    ids = [h["id"] for h in data["hyperedges"]]
    assert sorted(ids) == ["alpha::h_alpha", "beta::h_beta"], f"dup survived: {ids}"


def test_merge_graphs_reads_top_level_only_hyperedges(tmp_path):
    # #2485 skew on the input side: node_link_graph restores only the nested
    # graph-attrs slot, so an input whose hyperedges live only at the top
    # level used to lose them entirely.
    a = tmp_path / "alpha" / "graphify-out" / "graph.json"
    b = tmp_path / "beta" / "graphify-out" / "graph.json"
    _write_with_hyperedges(a, ["x"], [{"id": "h_top", "nodes": ["x"]}],
                           top_level_only=True)
    _write_with_hyperedges(b, ["p"], [])
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    assert [h["id"] for h in data["hyperedges"]] == ["alpha::h_top"]
    assert data["hyperedges"][0]["nodes"] == ["alpha::x"]



def _write_with_communities(p: Path, nodes):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": nid, "community": cid} for nid, cid in nodes],
        "links": [],
    }))


def test_merge_graphs_offsets_communities_so_repos_do_not_fuse(tmp_path):
    # #3014: every input numbers its communities from 0, so merge-graphs
    # carrying ids across unchanged made community 0 of repo alpha and
    # community 0 of repo beta the SAME community — the aggregated community
    # view then fused unrelated communities into one meta-node. Each input's
    # ids must be offset into a shared id space, with the per-repo partition
    # kept in local_community.
    a = tmp_path / "alpha" / "graphify-out" / "graph.json"
    b = tmp_path / "beta" / "graphify-out" / "graph.json"
    _write_with_communities(a, [("a0", 0), ("a1", 0), ("a2", 1)])
    _write_with_communities(b, [("b0", 0), ("b1", 1), ("b2", 1), ("b3", 2)])
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    a_nodes = [n for n in data["nodes"] if n["id"].startswith("alpha::")]
    b_nodes = [n for n in data["nodes"] if n["id"].startswith("beta::")]
    # the first input keeps its original ids (offset 0)
    assert {n["community"] for n in a_nodes} == {0, 1}
    # the second input is shifted past the first: {2, 3, 4}, disjoint
    assert {n["community"] for n in b_nodes} == {2, 3, 4}
    assert not (
        {n["community"] for n in a_nodes} & {n["community"] for n in b_nodes}
    ), "community ids still collide across repos (#3014)"
    # all five distinct communities survive the merge
    assert len({n["community"] for n in data["nodes"]}) == 5
    # the per-repo partition is preserved
    assert {n["local_community"] for n in b_nodes} == {0, 1, 2}


def test_merge_graphs_community_offset_is_byte_reproducible(tmp_path):
    """For a FIXED input order, the offset assignment must be deterministic:
    merging the same inputs twice produces byte-identical output. (Offsets are
    position-dependent by design — reordering inputs may renumber — so this pins
    only same-order reproducibility, which is what consumers rely on. #3014.)"""
    a = tmp_path / "alpha" / "graphify-out" / "graph.json"
    b = tmp_path / "beta" / "graphify-out" / "graph.json"
    _write_with_communities(a, [("a0", 0), ("a1", 0), ("a2", 1)])
    _write_with_communities(b, [("b0", 0), ("b1", 1), ("b2", 2)])

    out1 = tmp_path / "m1.json"
    out2 = tmp_path / "m2.json"
    assert _run(["merge-graphs", str(a), str(b), "--out", str(out1)], tmp_path).returncode == 0
    assert _run(["merge-graphs", str(a), str(b), "--out", str(out2)], tmp_path).returncode == 0
    assert out1.read_bytes() == out2.read_bytes(), "same-order merge is not byte-reproducible"
