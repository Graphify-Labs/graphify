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
