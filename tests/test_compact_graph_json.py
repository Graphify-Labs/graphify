"""graph.json is one line of compact JSON (#3413).

A pretty-printed graph.json makes every PR that commits a rebuilt graph report
tens of thousands of changed lines, and GitHub's line counts ignore
``.gitattributes``. Only the file's content can fix that, so every writer of a
project graph.json emits a single line, and ``update`` rewrites an existing
indented graph instead of treating it as unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.watch import _rebuild_code

PYTHON = sys.executable


def _run(args, cwd):
    return subprocess.run([PYTHON, "-m", "graphify"] + args, cwd=cwd, capture_output=True, text=True)


def _assert_one_line(path: Path):
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 1, f"{path.name} spans {len(text.splitlines())} lines"
    # compact separators: no space after ',' or ':' outside string values
    assert '": ' not in text and '", ' not in text and "}, " not in text
    return json.loads(text)


def _node(nid: str, source_file: str = "a.py") -> dict:
    return {"id": nid, "label": nid, "file_type": "code", "source_file": source_file}


def _graph_file(path: Path, node_ids, edges=(), *, indent=None) -> dict:
    data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [_node(n) for n in node_ids],
        "links": [{"source": s, "target": t, "relation": "calls", "confidence": "EXTRACTED",
                   "source_file": "a.py"} for s, t in edges],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent), encoding="utf-8")
    return data


def _corpus(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(
        "def alpha():\n    return beta()\n\n\ndef beta():\n    return 1\n", encoding="utf-8"
    )
    return tmp_path


def test_to_json_writes_one_compact_line(tmp_path):
    from graphify.export import to_json

    G = nx.Graph()
    G.add_node("a", label="a", file_type="code", source_file="a.py", community=0)
    G.add_node("b", label="b", file_type="code", source_file="a.py", community=0)
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", source_file="a.py")
    out = tmp_path / "graph.json"

    assert to_json(G, {0: ["a", "b"]}, str(out), force=True)

    data = _assert_one_line(out)
    assert {n["id"] for n in data["nodes"]} == {"a", "b"}
    assert len(data["links"]) == 1


@pytest.mark.parametrize("no_cluster", [False, True], ids=["clustered", "no-cluster"])
def test_update_writes_one_compact_line(tmp_path, no_cluster):
    corpus = _corpus(tmp_path)
    assert _rebuild_code(corpus, no_cluster=no_cluster, acquire_lock=False) is True

    data = _assert_one_line(corpus / "graphify-out" / "graph.json")
    labels = {n["label"] for n in data["nodes"]}
    assert {"alpha()", "beta()"} <= labels


@pytest.mark.parametrize("no_cluster", [False, True], ids=["clustered", "no-cluster"])
def test_update_rewrites_existing_indented_graph_compact(tmp_path, no_cluster):
    """An unchanged graph still checked in with indent=2 must not stay that way
    forever: the topology/graph-equality skips compare parsed data, not bytes."""
    corpus = _corpus(tmp_path)
    graph = corpus / "graphify-out" / "graph.json"
    assert _rebuild_code(corpus, no_cluster=no_cluster, acquire_lock=False) is True
    before = _assert_one_line(graph)

    graph.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    assert len(graph.read_text(encoding="utf-8").splitlines()) > 1

    assert _rebuild_code(corpus, no_cluster=no_cluster, acquire_lock=False) is True

    after = _assert_one_line(graph)
    assert {n["id"] for n in after["nodes"]} == {n["id"] for n in before["nodes"]}
    assert len(after["links"]) == len(before["links"])


@pytest.mark.parametrize("no_cluster", [False, True], ids=["clustered", "no-cluster"])
def test_update_leaves_compact_graph_untouched(tmp_path, no_cluster):
    """The legacy rewrite must not make every update rewrite a compact graph."""
    corpus = _corpus(tmp_path)
    graph = corpus / "graphify-out" / "graph.json"
    assert _rebuild_code(corpus, no_cluster=no_cluster, acquire_lock=False) is True
    before = graph.stat()

    assert _rebuild_code(corpus, no_cluster=no_cluster, acquire_lock=False) is True

    after = graph.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns), (
        "an already-compact, unchanged graph was rewritten"
    )


def test_merge_driver_output_is_one_line_union(tmp_path):
    base, cur, oth = (tmp_path / n for n in ("base.json", "cur.json", "oth.json"))
    _graph_file(base, ["a"])
    _graph_file(cur, ["a", "b"], [("a", "b")])
    _graph_file(oth, ["a", "c"], [("a", "c")])
    for p in (base, cur, oth):
        p.write_text(json.dumps(json.loads(p.read_text(encoding="utf-8")), separators=(",", ":")))

    r = _run(["merge-driver", str(base), str(cur), str(oth)], tmp_path)

    assert r.returncode == 0, r.stderr
    merged = _assert_one_line(cur)
    assert {n["id"] for n in merged["nodes"]} == {"a", "b", "c"}
    assert {(l["source"], l["target"]) for l in merged["links"]} == {("a", "b"), ("a", "c")}


def test_merge_graphs_output_is_one_line(tmp_path):
    a = tmp_path / "r1" / "graphify-out" / "graph.json"
    b = tmp_path / "r2" / "graphify-out" / "graph.json"
    _graph_file(a, ["x"])
    _graph_file(b, ["y"])
    out = tmp_path / "merged.json"

    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)

    assert r.returncode == 0, r.stderr
    data = _assert_one_line(out)
    assert {n["id"] for n in data["nodes"]} == {"r1::x", "r2::y"}


def test_prune_output_is_one_line(tmp_path):
    from graphify.cli import _prune_graph_json_sources

    graph = tmp_path / "graph.json"
    data = _graph_file(graph, ["keep", "drop"], indent=2)
    data["nodes"][1]["source_file"] = "gone.py"
    graph.write_text(json.dumps(data, indent=2), encoding="utf-8")

    assert _prune_graph_json_sources(graph, ["gone.py"]) == 1

    pruned = _assert_one_line(graph)
    assert [n["id"] for n in pruned["nodes"]] == ["keep"]


def test_extract_no_cluster_output_is_one_line(tmp_path):
    (tmp_path / "corpus").mkdir()
    corpus = _corpus(tmp_path / "corpus")
    out = tmp_path / "scratch"

    r = _run(["extract", str(corpus), "--out", str(out), "--no-cluster", "--code-only"], tmp_path)

    assert r.returncode == 0, r.stderr
    data = _assert_one_line(out / "graphify-out" / "graph.json")
    assert {"alpha()", "beta()"} <= {n["label"] for n in data["nodes"]}


def test_global_graph_output_is_one_line(tmp_path, monkeypatch):
    import graphify.global_graph as gg

    monkeypatch.setattr(gg, "_GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(gg, "_GLOBAL_GRAPH", tmp_path / "global-graph.json")
    G = nx.Graph()
    G.add_edge("r::a", "r::b", relation="calls")

    gg._save_global_graph(G)

    data = _assert_one_line(tmp_path / "global-graph.json")
    assert {n["id"] for n in data["nodes"]} == {"r::a", "r::b"}
