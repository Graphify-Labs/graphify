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


def _merged_graph(per_repo: dict[str, dict[str, str]]) -> dict:
    """Node-link graph shaped like a merge-graphs result: every node is
    repo-tagged and keeps its repo-relative source_file."""
    nodes = []
    for repo, files in sorted(per_repo.items()):
        for src, label in sorted(files.items()):
            nodes.append({
                "id": f"{repo}::{label}", "label": label,
                "source_file": src, "repo": repo,
            })
    return {"directed": False, "nodes": nodes, "links": []}


def _by_name(node: dict) -> dict:
    return {c["name"]: c for c in node["children"]}


def test_build_tree_merged_graph_gets_one_root_per_repo():
    graph = _merged_graph({
        "repo-a": {"src/engine.py": "EngineA"},
        "repo-b": {"lib/util.py": "UtilB"},
    })
    tree = build_tree(graph)
    assert set(_by_name(tree)) == {"repo-a", "repo-b"}
    assert tree["total_count"] == 2


def test_build_tree_merged_graph_keeps_shared_relative_paths_separate():
    """Same repo-relative path in two repos must not fuse into one file node."""
    graph = _merged_graph({
        "repo-a": {"src/engine.py": "EngineA"},
        "repo-b": {"src/engine.py": "EngineB"},
    })
    repos = _by_name(build_tree(graph))
    for tag, symbol in (("repo-a", "EngineA"), ("repo-b", "EngineB")):
        engine = _by_name(_by_name(repos[tag])["src"])["engine.py"]
        assert [c["name"] for c in engine["children"]] == [symbol]


def test_build_tree_single_repo_tag_is_unchanged():
    """One distinct repo tag keeps the pre-existing flat-root behaviour."""
    graph = _merged_graph({"repo-a": {"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"}})
    tree = build_tree(graph)
    assert tree["name"] == "pkg"
    assert {"a.py", "sub"} <= set(_by_name(tree))


def test_build_tree_merged_graph_untagged_nodes_are_kept():
    graph = _merged_graph({
        "repo-a": {"a.py": "A"},
        "repo-b": {"b.py": "B"},
    })
    graph["nodes"].append({"id": "x", "label": "X", "source_file": "x.py"})
    assert set(_by_name(build_tree(graph))) == {"repo-a", "repo-b", "(no repo)"}


def test_build_tree_partially_tagged_single_repo_is_not_a_merged_graph():
    """One real repo tag plus untagged nodes is not a merged graph: it must
    take the original single-root path, not grow a "(no repo)" sibling."""
    graph = {"nodes": [
        {"id": "a", "label": "A", "source_file": "pkg/a.py", "repo": "only-repo"},
        {"id": "b", "label": "B", "source_file": "pkg/b.py"},
    ]}
    tree = build_tree(graph)
    assert tree["name"] == "pkg"
    assert set(_by_name(tree)) == {"a.py", "b.py"}


def test_build_tree_untagged_graph_is_unchanged_by_repo_grouping():
    graph = _graph({"pkg/a.py": "func_a", "pkg/sub/b.py": "func_b"})
    assert "repo" not in graph["nodes"][0]
    tree = build_tree(graph)
    assert tree["name"] == "pkg"
    assert {"a.py", "sub"} <= set(_by_name(tree))


def test_build_tree_merged_graph_explicit_root_matching_nothing_raises():
    graph = _merged_graph({
        "repo-a": {"src/a.py": "A"},
        "repo-b": {"src/b.py": "B"},
    })
    with pytest.raises(ValueError, match=r"matched 0 of 2 source files"):
        build_tree(graph, root="/abs/checkout/elsewhere")


def test_build_tree_merged_graph_uses_project_label_for_top_root():
    graph = _merged_graph({"repo-a": {"a.py": "A"}, "repo-b": {"b.py": "B"}})
    assert build_tree(graph, project_label="world")["name"] == "world"


def test_tree_cli_merged_graph_renders_repo_roots(tmp_path):
    out = _write_graph(tmp_path, _merged_graph({
        "repo-a": {"src/engine.py": "EngineA"},
        "repo-b": {"src/engine.py": "EngineB"},
    }))
    r = _run(["tree", "--graph", str(out / "graph.json")], tmp_path)
    assert r.returncode == 0, r.stderr
    html = (out / "GRAPH_TREE.html").read_text(encoding="utf-8")
    assert "repo-a" in html and "repo-b" in html


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


# Directory breadth is independent of the existing symbol limit beneath files.
def test_build_tree_caps_directories_with_full_hidden_totals():
    graph = _graph({
        "pkg/Adir/a.py": "A", "pkg/Adir/b.py": "B", "pkg/Adir/c.py": "C",
        "pkg/b.py": "B0", "pkg/Zdir/a.py": "Z1", "pkg/Zdir/b.py": "Z2",
    })
    graph["nodes"].append({
        "id": "file", "label": "leaf.py", "source_file": "pkg/leaf.py",
        "file_type": "code",
    })
    tree = build_tree(graph, root="pkg", max_children=2)
    assert [c["name"] for c in tree["children"]] == ["Adir", "b.py", "(+2 more)"]
    assert tree["total_count"] == 7
    assert tree["children"][-1] == {"name": "(+2 more)", "total_count": 3, "children": []}
    nested = tree["children"][0]
    assert [c["name"] for c in nested["children"]] == ["a.py", "b.py", "(+1 more)"]
    assert nested["total_count"] == 3


def test_build_tree_directory_cap_preserves_file_symbol_behavior():
    graph = {"nodes": [
        {"id": name, "label": name, "source_file": "pkg/a.py"}
        for name in ["gamma", "Beta", "_private", "Alpha"]
    ]}
    tree = build_tree(graph, root="pkg", max_children=2)
    file = tree["children"][0]
    # The existing finalizer sorts the file's omission sentinel before symbols.
    assert [c["name"] for c in file["children"]] == ["(+2 more)", "Alpha", "Beta"]
    assert file["children"][0]["total_count"] == 2
    assert file["total_count"] == tree["total_count"] == 4


def test_build_tree_caps_merged_repo_and_untagged_directories():
    graph = _merged_graph({
        "repo-a": {"src/engine.py": "EngineA", "z1.py": "A1", "z2.py": "A2", "z3.py": "A3"},
        "repo-b": {"src/engine.py": "EngineB", "y1.py": "B1", "y2.py": "B2"},
    })
    graph["nodes"].extend(_graph({f"u{i}.py": f"U{i}" for i in range(4)})["nodes"])
    tree = build_tree(graph, max_children=3)
    assert [c["name"] for c in tree["children"]] == ["(no repo)", "repo-a", "repo-b"]
    repos = _by_name(tree)
    for tag, symbol in [("repo-a", "EngineA"), ("repo-b", "EngineB")]:
        engine = _by_name(_by_name(repos[tag])["src"])["engine.py"]
        assert [c["name"] for c in engine["children"]] == [symbol]
    assert [c["name"] for c in repos["repo-a"]["children"]] == ["src", "z1.py", "z2.py", "(+1 more)"]
    assert [c["name"] for c in repos["repo-b"]["children"]] == ["src", "y1.py", "y2.py"]
    assert [c["name"] for c in repos["(no repo)"]["children"]] == ["u0.py", "u1.py", "u2.py", "(+1 more)"]
    assert [repos[tag]["total_count"] for tag in ["repo-a", "repo-b", "(no repo)"]] == [4, 3, 4]
    assert tree["total_count"] == 11


def test_build_tree_caps_synthetic_merged_root_with_hidden_subtree_total():
    tree = build_tree(_merged_graph({
        "Alpha": {"a.py": "A"}, "Beta": {"b.py": "B"},
        "Zulu": {"x.py": "X", "y.py": "Y", "z.py": "Z"},
    }), max_children=2)
    assert [c["name"] for c in tree["children"]] == ["Alpha", "Beta", "(+1 more)"]
    assert tree["children"][-1] == {"name": "(+1 more)", "total_count": 3, "children": []}
    assert tree["total_count"] == 5


@pytest.mark.parametrize("cap, names", [(0, ["(+2 more)"]), (2, ["a.py", "b.py"])])
def test_build_tree_directory_cap_zero_and_exact_boundary(cap, names):
    tree = build_tree(_graph({"pkg/a.py": "A", "pkg/b.py": "B"}), root="pkg", max_children=cap)
    assert [c["name"] for c in tree["children"]] == names
    assert tree["total_count"] == 2
    assert sum(c["total_count"] for c in tree["children"]) == 2
    assert build_tree({"nodes": []}, max_children=cap)["children"] == []


def test_build_tree_directory_cap_default_is_200():
    tree = build_tree(_graph({f"pkg/f{i:03}.py": str(i) for i in range(201)}), root="pkg")
    assert len(tree["children"]) == 201
    assert tree["children"][-2]["name"] == "f199.py"
    assert tree["children"][-1] == {"name": "(+1 more)", "total_count": 1, "children": []}
    assert tree["total_count"] == 201


@pytest.mark.parametrize("graph", [{"nodes": []}, _graph({"pkg/a.py": "A"})])
def test_build_tree_rejects_negative_cap_before_empty_return(graph):
    with pytest.raises(ValueError, match="--max-children must be nonnegative"):
        build_tree(graph, max_children=-1)


def test_tree_cli_directory_cap_serializes_existing_schema(tmp_path):
    import re

    out = _write_graph(tmp_path, _graph({"pkg/a.py": "A", "pkg/b.py": "B", "pkg/c.py": "C"}))
    result = _run(["tree", "--root", "pkg", "--max-children", "1"], tmp_path)
    assert result.returncode == 0, result.stderr
    page = (out / "GRAPH_TREE.html").read_text(encoding="utf-8")
    match = re.search(r"const initialJsonData = (.*);", page)
    assert match is not None
    tree = json.loads(match.group(1))
    assert [c["name"] for c in tree["children"]] == ["a.py", "(+2 more)"]
    assert tree["total_count"] == 3
    assert tree["children"][-1]["total_count"] == 2
    assert "b.py" not in match.group(1) and "c.py" not in match.group(1)

    def check_keys(node):
        assert set(node) == {"name", "total_count", "children"}
        for child in node["children"]:
            check_keys(child)

    check_keys(tree)


def test_tree_cli_negative_cap_does_not_write_html(tmp_path):
    out = _write_graph(tmp_path, _graph({"pkg/a.py": "A"}))
    result = _run(["tree", "--max-children", "-1"], tmp_path)
    assert result.returncode == 1
    assert "error:" in result.stderr
    assert "--max-children must be nonnegative" in result.stderr
    assert "Traceback" not in result.stderr and "wrote" not in result.stdout
    assert not (out / "GRAPH_TREE.html").exists()
