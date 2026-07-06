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


def _write_repository_graph(p: Path, label: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "entry",
                "label": f"{label} entry",
                "community": 0,
                "community_name": "Community 0",
            },
            {
                "id": "worker",
                "label": f"{label} worker",
                "community": 1,
                "community_name": f"{label} workers",
            },
        ],
        "links": [
            {"source": "entry", "target": "worker", "relation": "calls"},
        ],
        "hyperedges": [
            {"id": "request_flow", "nodes": ["entry", "worker"], "relation": "flow"},
        ],
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
    assert ids == {"r1::x", "r2::y", "r3::z"}
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


def test_merge_graphs_preserves_repository_local_identity(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)

    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    nodes = {node["id"]: node for node in data["nodes"]}
    assert set(nodes) == {"a::entry", "a::worker", "b::entry", "b::worker"}
    assert {nodes["a::entry"]["community"], nodes["a::worker"]["community"]}.isdisjoint(
        {nodes["b::entry"]["community"], nodes["b::worker"]["community"]}
    )
    assert nodes["b::entry"]["community_name"] == (
        f"Community {nodes['b::entry']['community']}"
    )
    assert nodes["b::worker"]["community_name"] == "B workers"
    assert {
        (edge["source"], edge["target"], edge["relation"])
        for edge in data["links"]
    } == {
        ("a::entry", "a::worker", "calls"),
        ("b::entry", "b::worker", "calls"),
    }
    assert {
        hyperedge["id"]: hyperedge["nodes"] for hyperedge in data["hyperedges"]
    } == {
        "a::request_flow": ["a::entry", "a::worker"],
        "b::request_flow": ["b::entry", "b::worker"],
    }
    assert "4 nodes, 2 edges, 2 hyperedges" in r.stdout


def test_merge_graphs_derives_tag_from_relative_canonical_path(tmp_path):
    a = tmp_path / "repo-a" / "graphify-out" / "graph.json"
    b = tmp_path / "repo-b" / "graphify-out" / "graph.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")

    r = _run([
        "merge-graphs", "graphify-out/graph.json",
        "../repo-b/graphify-out/graph.json", "--out", "merged.json",
    ], tmp_path / "repo-a")

    assert r.returncode == 0, r.stderr
    ids = {node["id"] for node in json.loads((tmp_path / "repo-a/merged.json").read_text())["nodes"]}
    assert {"repo-a::entry", "repo-b::entry"} <= ids


def test_merge_graphs_community_remap_is_input_order_independent(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")
    out_ab = tmp_path / "merged-ab.json"
    out_ba = tmp_path / "merged-ba.json"

    first = _run(["merge-graphs", str(a), str(b), "--out", str(out_ab)], tmp_path)
    second = _run(["merge-graphs", str(b), str(a), "--out", str(out_ba)], tmp_path)

    assert first.returncode == second.returncode == 0
    communities_ab = {
        node["id"]: node.get("community")
        for node in json.loads(out_ab.read_text())["nodes"]
    }
    communities_ba = {
        node["id"]: node.get("community")
        for node in json.loads(out_ba.read_text())["nodes"]
    }
    assert communities_ab == communities_ba


def test_merge_graphs_disambiguates_duplicate_derived_tags(tmp_path):
    a = tmp_path / "owner-a" / "service" / "graphify-out" / "graph.json"
    b = tmp_path / "owner-b" / "service" / "graphify-out" / "graph.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)

    assert r.returncode == 0, r.stderr
    ids = {node["id"] for node in json.loads(out.read_text())["nodes"]}
    assert "owner-a_service::entry" in ids
    assert "owner-b_service::entry" in ids


def test_merge_graphs_accepts_explicit_repository_tags(tmp_path):
    a = tmp_path / "owner-a" / "service" / "graphify-out" / "graph.json"
    b = tmp_path / "owner-b" / "service" / "graphify-out" / "graph.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")
    out = tmp_path / "merged.json"

    r = _run([
        "merge-graphs", str(a), str(b),
        "--repo-tag", "owner-a-service", "--repo-tag", "owner-b-service",
        "--out", str(out),
    ], tmp_path)

    assert r.returncode == 0, r.stderr
    ids = {node["id"] for node in json.loads(out.read_text())["nodes"]}
    assert "owner-a-service::entry" in ids
    assert "owner-b-service::entry" in ids


def test_merge_graphs_rejects_duplicate_explicit_tags(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")
    out = tmp_path / "merged.json"

    r = _run([
        "merge-graphs", str(a), str(b),
        "--repo-tag", "service", "--repo-tag", "service",
        "--out", str(out),
    ], tmp_path)

    assert r.returncode != 0
    assert "duplicate repository tag(s): 'service'" in r.stderr
    assert not out.exists()


def test_merge_graphs_requires_one_explicit_tag_per_input(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_repository_graph(a, "A")
    _write_repository_graph(b, "B")

    r = _run(["merge-graphs", str(a), str(b), "--repo-tag", "a"], tmp_path)

    assert r.returncode != 0
    assert "--repo-tag must be repeated once for every input graph" in r.stderr
