"""MATLAB inheritance refresh through the actual incremental watch rebuild."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code


def _class_source(name: str, superclass: str | None = None, revision: int | None = None) -> str:
    parent = f" < {superclass}" if superclass else ""
    lines = [f"classdef {name}{parent}"]
    if revision is not None:
        lines.extend([
            "    methods",
            "        function value = version(obj)",
            f"            value = {revision};",
            "        end",
            "    end",
        ])
    return "\n".join([*lines, "end", ""])


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _graph(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _class(graph: dict, name: str, source_file: str) -> dict:
    matches = [
        node for node in graph.get("nodes", [])
        if node.get("label") == name
        and node.get("source_file") == source_file
        and node.get("metadata", {}).get("kind") == "matlab_class"
    ]
    assert len(matches) == 1, (name, source_file, matches)
    return matches[0]


def _inheritance_targets(graph: dict, child: dict) -> list[dict]:
    by_id = {node["id"]: node for node in graph.get("nodes", [])}
    return [
        by_id[edge["target"]]
        for edge in graph.get("links", graph.get("edges", []))
        if edge.get("relation") == "inherits" and edge.get("source") == child["id"]
    ]


@pytest.mark.parametrize("no_cluster", [True, False], ids=["raw", "clustered"])
def test_incremental_watch_refreshes_unchanged_child_for_base_lifecycle(tmp_path, no_cluster):
    root = tmp_path / "project"
    root.mkdir()
    graph_path = root / "graphify-out" / "graph.json"
    _write(root, "+pkg/Child.m", _class_source("Child", "pkg.Base"))

    assert _rebuild_code(root, no_cluster=no_cluster, acquire_lock=False) is True
    initial = _graph(graph_path)
    child = _class(initial, "Child", "+pkg/Child.m")
    child_id = child["id"]
    assert _inheritance_targets(initial, child) == []

    base_path = _write(root, "+pkg/Base.m", _class_source("Base"))
    assert _rebuild_code(
        root, changed_paths=[base_path], no_cluster=no_cluster, acquire_lock=False
    ) is True
    added = _graph(graph_path)
    child = _class(added, "Child", "+pkg/Child.m")
    targets = _inheritance_targets(added, child)
    assert child["id"] == child_id
    assert [(node["label"], node.get("source_file")) for node in targets] == [
        ("Base", "+pkg/Base.m")
    ]

    before_noop = graph_path.read_bytes()
    assert _rebuild_code(
        root, changed_paths=[], no_cluster=no_cluster, acquire_lock=False
    ) is True
    assert graph_path.read_bytes() == before_noop

    base_path.write_text(_class_source("Base", revision=1), encoding="utf-8")
    assert _rebuild_code(
        root, changed_paths=[base_path], no_cluster=no_cluster, acquire_lock=False
    ) is True
    changed = _graph(graph_path)
    child = _class(changed, "Child", "+pkg/Child.m")
    assert child["id"] == child_id
    assert [node["label"] for node in _inheritance_targets(changed, child)] == ["Base"]

    duplicate_path = _write(
        root, "other/+pkg/Base.m", _class_source("Base")
    )
    assert _rebuild_code(
        root, changed_paths=[duplicate_path], no_cluster=no_cluster, acquire_lock=False
    ) is True
    ambiguous = _graph(graph_path)
    child = _class(ambiguous, "Child", "+pkg/Child.m")
    assert child["id"] == child_id
    assert _inheritance_targets(ambiguous, child) == []

    duplicate_path.unlink()
    assert _rebuild_code(
        root, changed_paths=[duplicate_path], no_cluster=no_cluster, acquire_lock=False
    ) is True
    disambiguated = _graph(graph_path)
    child = _class(disambiguated, "Child", "+pkg/Child.m")
    targets = _inheritance_targets(disambiguated, child)
    assert child["id"] == child_id
    assert [(node["label"], node.get("source_file")) for node in targets] == [
        ("Base", "+pkg/Base.m")
    ]

    base_path.unlink()
    assert _rebuild_code(
        root, changed_paths=[base_path], no_cluster=no_cluster, acquire_lock=False
    ) is True
    removed = _graph(graph_path)
    child = _class(removed, "Child", "+pkg/Child.m")
    assert child["id"] == child_id
    assert _inheritance_targets(removed, child) == []
    assert not any(node.get("source_file") == "+pkg/Base.m" for node in removed["nodes"])
