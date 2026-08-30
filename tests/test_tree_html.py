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

from graphify.tree_html import build_tree, emit_html

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


# ── Expand All budget ─────────────────────────────────────────────────────────

UNBOUNDED = "window.expandAll = () => { expandBranch(rootNode); updateTree(rootNode); };"


def _wide_tree(n_files: int):
    return build_tree(_graph({f"pkg/mod{i}.py": f"sym{i}" for i in range(n_files)}))


def test_expand_all_does_not_mount_the_whole_tree_in_one_join():
    """Expand All used to be expandBranch(rootNode) with no ceiling. On a
    257k-node graph that is ~709k SVG elements in a single D3 join and the
    renderer never recovers, so the handler must go through a budget."""
    html = emit_html(_wide_tree(20), title="t", header="h")

    assert UNBOUNDED not in html
    assert "expandWithinBudget(rootNode, EXPAND_ALL_NODE_BUDGET)" in html


def test_expand_all_budget_is_emitted_and_overridable():
    from graphify.tree_html import DEFAULT_EXPAND_ALL_BUDGET

    default_html = emit_html(_wide_tree(5), title="t", header="h")
    assert f"const EXPAND_ALL_NODE_BUDGET = {DEFAULT_EXPAND_ALL_BUDGET};" in default_html

    custom_html = emit_html(_wide_tree(5), title="t", header="h", expand_all_budget=1234)
    assert "const EXPAND_ALL_NODE_BUDGET = 1234;" in custom_html


def test_expand_all_reports_what_it_left_collapsed():
    html = emit_html(_wide_tree(5), title="t", header="h")
    assert 'id="expand-status"' in html
    assert "setExpandStatus(" in html
