"""Tests for graphify tree / tree_html.build_tree.

#2534 case 3: `tree --root <path>` that matches NO source_file used to silently
flatten the whole hierarchy (every file attached flat to the root) while the CLI
still printed "wrote ..." and exited 0 — source_file paths are stored
repo-relative, so an absolute --root never matched. A zero-match explicit root
now raises/exits 1; the default computed root and partial matches stay exit 0.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.tree_html import build_tree

PYTHON = sys.executable


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _graph(files: dict[str, str]) -> dict:
    """Minimal node-link graph: one symbol node per {source_file: label}."""
    return {
        "directed": False,
        "nodes": [
            {"id": f"n{i}", "label": label, "source_file": src}
            for i, (src, label) in enumerate(sorted(files.items()))
        ],
        "links": [],
    }


def _write_graph(tmp_path: Path, graph: dict) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return out


# ── build_tree unit tests ─────────────────────────────────────────────────────


def test_build_tree_explicit_root_matching_nothing_raises():
    graph = _graph({"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"})
    with pytest.raises(ValueError, match=r"matched 0 of 2 source files"):
        build_tree(graph, root="/abs/checkout/elsewhere")


def test_build_tree_error_names_a_repo_relative_sample():
    graph = _graph({"pkg/a.py": "func_a"})
    with pytest.raises(ValueError, match=r"repo-relative.*'pkg/a\.py'"):
        build_tree(graph, root="/abs/nonmatch")


def test_build_tree_partial_match_does_not_raise():
    """Files outside an explicit root legitimately attach flat — only a
    ZERO-match explicit root is an error."""
    graph = _graph({"pkg/a.py": "func_a", "other/c.py": "func_c"})
    tree = build_tree(graph, root="pkg")
    assert tree["name"] == "pkg"
    assert tree["total_count"] > 0


def test_build_tree_default_root_keeps_hierarchy():
    graph = _graph({"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"})
    tree = build_tree(graph)  # computed common root — always matches
    assert tree["name"] == "pkg"
    names = {c["name"] for c in tree["children"]}
    assert "a.py" in names and "sub" in names


# ── CLI integration ───────────────────────────────────────────────────────────


def test_tree_cli_absolute_root_mismatch_exits_1(tmp_path):
    _write_graph(tmp_path, _graph({"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"}))
    r = _run(["tree", "--root", "/abs/nonmatch"], tmp_path)
    assert r.returncode == 1, r.stdout
    assert "matched 0 of" in r.stderr, r.stderr
    # the handler's error pattern, not an unhandled traceback
    assert "error:" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "wrote" not in r.stdout, r.stdout
    assert not (tmp_path / "graphify-out" / "GRAPH_TREE.html").exists()


def test_tree_cli_default_root_succeeds(tmp_path):
    _write_graph(tmp_path, _graph({"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"}))
    r = _run(["tree"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "wrote" in r.stdout, r.stdout
    html = (tmp_path / "graphify-out" / "GRAPH_TREE.html").read_text(encoding="utf-8")
    # the hierarchy survives: pkg is the root, sub is an interior node
    assert '"name":"pkg"' in html
    assert '"name":"sub"' in html


def test_tree_cli_partial_match_root_succeeds(tmp_path):
    _write_graph(tmp_path, _graph({"pkg/a.py": "func_a", "other/c.py": "func_c"}))
    r = _run(["tree", "--root", "pkg"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "graphify-out" / "GRAPH_TREE.html").exists()


# ── merged graphs (#4522, #4524) ──────────────────────────────────────────────


def _repo_graph(repo: str, files: dict[str, list[str]]) -> dict:
    """Per-repo graph shaped like merge-graphs output: prefixed id + repo tag."""
    nodes = [
        {"id": f"{repo}::{src}::{label}", "label": label, "source_file": src, "repo": repo}
        for src, labels in sorted(files.items())
        for label in labels
    ]
    return {"directed": False, "nodes": nodes, "links": []}


def _merged(*graphs: dict) -> dict:
    return {"directed": False, "nodes": [n for g in graphs for n in g["nodes"]], "links": []}


def _child(node: dict, name: str) -> dict:
    matches = [c for c in node["children"] if c["name"] == name]
    assert len(matches) == 1, [c["name"] for c in node["children"]]
    return matches[0]


def test_build_tree_merged_graph_has_one_root_per_repo():
    """Same relative path in two repos stays two files, each under its repo (#4524)."""
    graph = _merged(
        _repo_graph("repo-a", {"src/engine.py": ["ClsA", "fn_a"]}),
        _repo_graph("repo-b", {"src/engine.py": ["ClsB", "fn_b"]}),
    )
    tree = build_tree(graph)
    assert [c["name"] for c in tree["children"]] == ["repo-a", "repo-b"]
    assert tree["total_count"] == 4
    a = _child(_child(_child(tree, "repo-a"), "src"), "engine.py")
    b = _child(_child(_child(tree, "repo-b"), "src"), "engine.py")
    assert sorted(c["name"] for c in a["children"]) == ["ClsA", "fn_a"]
    assert sorted(c["name"] for c in b["children"]) == ["ClsB", "fn_b"]


def test_build_tree_merged_graph_root_label():
    graph = _merged(_repo_graph("a", {"x.py": ["f"]}), _repo_graph("b", {"y.py": ["g"]}))
    assert build_tree(graph)["name"] == "2 repos"
    assert build_tree(graph, project_label="world")["name"] == "world"


def test_build_tree_merged_graph_root_matching_nothing_raises():
    graph = _merged(_repo_graph("a", {"src/x.py": ["f"]}), _repo_graph("b", {"src/y.py": ["g"]}))
    with pytest.raises(ValueError, match=r"matched 0 of 2 source files"):
        build_tree(graph, root="/abs/nonmatch")
    # a repo-relative root applies inside every repo
    assert build_tree(graph, root="src")["total_count"] == 2


def test_build_tree_nodes_without_source_file_raise():
    """A non-empty graph with no source_file used to render a blank viewer (#4522)."""
    graph = {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "links": []}
    with pytest.raises(ValueError, match=r"none of the graph's 2 nodes has a source_file"):
        build_tree(graph)
    assert build_tree({"nodes": [], "links": []})["name"] == "(empty graph)"


def test_tree_cli_on_merge_graphs_output_keeps_repo_hierarchy(tmp_path):
    """End to end: merge-graphs keeps source_file and tree draws per-repo roots (#4522, #4524)."""
    paths = []
    for repo, label in (("repo-a", "ClsA"), ("repo-b", "ClsB")):
        out = tmp_path / repo / "graphify-out"
        out.mkdir(parents=True)
        g = {
            "directed": False,
            "nodes": [{"id": "src_engine_cls", "label": label, "file_type": "code",
                       "source_file": "src/engine.py"}],
            "links": [],
        }
        (out / "graph.json").write_text(json.dumps(g), encoding="utf-8")
        paths.append(str(out / "graph.json"))
    merged = tmp_path / "world" / "graphify-out" / "graph.json"
    r = _run(["merge-graphs", *paths, "--out", str(merged)], tmp_path)
    assert r.returncode == 0, r.stderr
    nodes = json.loads(merged.read_text(encoding="utf-8"))["nodes"]
    assert all(n.get("source_file") == "src/engine.py" for n in nodes), nodes

    html_out = tmp_path / "TREE.html"
    r = _run(["tree", "--graph", str(merged), "--output", str(html_out)], tmp_path)
    assert r.returncode == 0, r.stderr
    html = html_out.read_text(encoding="utf-8")
    assert '"name":"repo-a"' in html and '"name":"repo-b"' in html
    assert "(empty graph)" not in html


def test_tree_cli_nodes_without_source_file_exits_1(tmp_path):
    _write_graph(tmp_path, {"directed": False, "nodes": [{"id": "a", "label": "A"}], "links": []})
    r = _run(["tree"], tmp_path)
    assert r.returncode == 1, r.stdout
    assert "error:" in r.stderr and "source_file" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
