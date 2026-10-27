"""MATLAB inheritance refresh across raw and clustered incremental merges."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from graphify.build import (
    _refresh_matlab_inheritance,
    build,
    build_merge,
    merge_raw_extraction,
)
from graphify.export import to_json
from graphify.extract import extract


MERGE_PATHS = ("raw", "clustered")


def _class_source(name: str, superclass: str | None = None, revision: int | None = None) -> str:
    parent = f" < {superclass}" if superclass else ""
    source = f"classdef {name}{parent}\n"
    if revision is not None:
        source += (
            "    methods\n"
            "        function value = version(obj)\n"
            f"            value = {revision};\n"
            "        end\n"
            "    end\n"
        )
    return source + "end\n"


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _extract(root: Path, paths: list[Path], **kwargs) -> dict:
    return extract(paths, root=root, cache_root=root.parent / "cache", parallel=False, **kwargs)


def _read_graph(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _edges(graph: dict) -> list[dict]:
    return graph.get("links", graph.get("edges", []))


def _write_raw(path: Path, graph: dict) -> None:
    path.write_text(
        json.dumps({key: graph[key] for key in ("nodes", "edges", "hyperedges") if key in graph}),
        encoding="utf-8",
    )


def _start_graph(mode: str, root: Path, path: Path, files: list[Path]) -> None:
    extracted = _extract(root, files)
    if mode == "raw":
        _write_raw(path, extracted)
    else:
        graph = build([extracted], dedup=False, root=root)
        assert to_json(graph, {}, str(path), force=True)


def _merge(
    mode: str,
    root: Path,
    path: Path,
    changed: list[Path] | None = None,
    deleted: list[Path] | None = None,
) -> dict:
    changed_paths = changed or []
    fresh = _extract(root, changed_paths) if changed_paths else {"nodes": [], "edges": []}
    prune = [str(item) for item in (deleted or [])]
    if mode == "raw":
        merged = merge_raw_extraction(
            fresh, path, prune_sources=prune, root=root, ast_sources=changed_paths,
        )
        _write_raw(path, merged)
    else:
        graph = build_merge(
            [fresh] if changed_paths else [], path, prune_sources=prune,
            dedup=False, root=root, ast_sources=changed_paths,
        )
        assert to_json(graph, {}, str(path), force=True)
    return _read_graph(path)


def _matlab_class(graph: dict, name: str, source_file: str) -> dict:
    matches = [
        node for node in graph.get("nodes", [])
        if node.get("label") == name
        and node.get("source_file") == source_file
        and node.get("metadata", {}).get("kind") == "matlab_class"
    ]
    assert len(matches) == 1, (name, source_file, matches)
    return matches[0]


def _targets(graph: dict, child: dict) -> list[dict]:
    by_id = {node["id"]: node for node in graph.get("nodes", [])}
    return [
        by_id[edge["target"]]
        for edge in _edges(graph)
        if edge.get("relation") == "inherits" and edge.get("source") == child["id"]
    ]


def _signature(graph: dict) -> tuple:
    nodes = tuple(sorted(json.dumps(node, sort_keys=True) for node in graph.get("nodes", [])))
    edges = tuple(sorted(json.dumps(edge, sort_keys=True) for edge in _edges(graph)))
    return nodes, edges


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_changed_child_replaces_only_itself_and_keeps_context_read_only(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base", revision=1))
    child_path = _write(root, "Child.m", _class_source("Child", "Base", revision=1))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    before = _read_graph(graph_path)
    base_before = _matlab_class(before, "Base", "Base.m")
    child_before = _matlab_class(before, "Child", "Child.m")
    assert [node["label"] for node in _targets(before, child_before)] == ["Base"]

    context_nodes = copy.deepcopy([
        node for node in before["nodes"] if node.get("source_file") == "Base.m"
    ])
    context_edges = copy.deepcopy([
        edge for edge in _edges(before) if edge.get("source_file") == "Base.m"
    ])
    nodes_snapshot, edges_snapshot = copy.deepcopy(context_nodes), copy.deepcopy(context_edges)
    child_path.write_text(_class_source("Child", "Base", revision=2), encoding="utf-8")
    fresh = _extract(
        root, [child_path], resolution_context_nodes=context_nodes,
        resolution_context_edges=context_edges,
    )
    assert context_nodes == nodes_snapshot
    assert context_edges == edges_snapshot
    assert {node.get("source_file") for node in fresh["nodes"]} == {"Child.m"}

    if mode == "raw":
        merged = merge_raw_extraction(
            fresh, graph_path, root=root, ast_sources=[child_path],
        )
        _write_raw(graph_path, merged)
    else:
        graph = build_merge(
            [fresh], graph_path, dedup=False, root=root, ast_sources=[child_path],
        )
        assert to_json(graph, {}, str(graph_path), force=True)
    after = _read_graph(graph_path)

    base_after = _matlab_class(after, "Base", "Base.m")
    child_after = _matlab_class(after, "Child", "Child.m")
    assert base_after["id"] == base_before["id"]
    assert child_after["id"] == child_before["id"]
    assert [node["label"] for node in _targets(after, child_after)] == ["Base"]
    assert sum(node.get("source_file") == "Base.m" for node in after["nodes"]) == sum(
        node.get("source_file") == "Base.m" for node in before["nodes"]
    )


def test_matlab_inheritance_refresh_normalizes_mixed_paths_without_mutating_inputs(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    child_source = str(root / "Child.m")
    nodes = [
        {
            "id": "child_file",
            "label": "Child.m",
            "source_file": child_source,
            "file_type": "code",
            "metadata": {
                "language": "matlab", "kind": "matlab_file", "namespace": "",
                "matlab_file_kind": "class", "matlab_primary_name": "Child",
            },
        },
        {
            "id": "child",
            "label": "Child",
            "source_file": child_source,
            "file_type": "code",
            "metadata": {
                "language": "matlab", "kind": "matlab_class", "namespace": "",
                "scope_chain": [],
                "matlab_superclasses": [{"name": "Base", "source_location": "L2"}],
            },
        },
        {
            "id": "base_file",
            "label": "Base.m",
            "source_file": "Base.m",
            "file_type": "code",
            "metadata": {
                "language": "matlab", "kind": "matlab_file", "namespace": "",
                "matlab_file_kind": "class", "matlab_primary_name": "Base",
            },
        },
        {
            "id": "base",
            "label": "Base",
            "source_file": "Base.m",
            "file_type": "code",
            "metadata": {
                "language": "matlab", "kind": "matlab_class", "namespace": "",
                "scope_chain": [],
            },
        },
    ]
    edges = [
        {"source": "base_file", "target": "base", "relation": "contains", "source_file": "Base.m"},
        {
            "source": "child", "target": "stale", "relation": "inherits",
            "source_file": child_source, "_origin": "ast",
        },
    ]
    before = copy.deepcopy((nodes, edges))

    refreshed = _refresh_matlab_inheritance(nodes, edges, root=root)

    assert (nodes, edges) == before
    assert [
        (edge["source"], edge["target"], edge["source_file"])
        for edge in refreshed if edge.get("relation") == "inherits"
    ] == [("child", "base", "Child.m")]


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_absolute_matlab_reextract_resolves_relative_unchanged_base(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    fresh = _extract(root, [child_path])
    for item in fresh["nodes"] + fresh["edges"]:
        if item.get("source_file"):
            item["source_file"] = str(root / item["source_file"])

    if mode == "raw":
        merged = merge_raw_extraction(
            fresh, graph_path, root=root, ast_sources=[child_path],
        )
        _write_raw(graph_path, merged)
    else:
        graph = build_merge(
            [fresh], graph_path, dedup=False, root=root, ast_sources=[child_path],
        )
        assert to_json(graph, {}, str(graph_path), force=True)

    after = _read_graph(graph_path)
    child = next(
        node for node in after["nodes"]
        if node.get("label") == "Child"
        and node.get("metadata", {}).get("kind") == "matlab_class"
    )
    assert [node["label"] for node in _targets(after, child)] == ["Base"]


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_unchanged_child_keeps_inheritance_after_base_content_change(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base", revision=1))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    before = _read_graph(graph_path)
    child_before = _matlab_class(before, "Child", "Child.m")

    base_path.write_text(_class_source("Base", revision=2), encoding="utf-8")
    after = _merge(mode, root, graph_path, [base_path])

    child_after = _matlab_class(after, "Child", "Child.m")
    assert child_after["id"] == child_before["id"]
    assert [node["label"] for node in _targets(after, child_after)] == ["Base"]


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_unchanged_child_drops_inheritance_when_base_is_renamed(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    child_before = _matlab_class(_read_graph(graph_path), "Child", "Child.m")

    renamed_path = root / "Renamed.m"
    renamed_path.write_text(_class_source("Renamed"), encoding="utf-8")
    base_path.unlink()
    after = _merge(mode, root, graph_path, [renamed_path], [base_path])

    child_after = _matlab_class(after, "Child", "Child.m")
    assert child_after["id"] == child_before["id"]
    assert _targets(after, child_after) == []
    assert not any(node.get("source_file") == "Base.m" for node in after["nodes"])


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_unchanged_child_resolves_when_base_is_added(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [child_path])
    child_before = _matlab_class(_read_graph(graph_path), "Child", "Child.m")
    assert _targets(_read_graph(graph_path), child_before) == []

    base_path = _write(root, "Base.m", _class_source("Base"))
    after = _merge(mode, root, graph_path, [base_path])

    child_after = _matlab_class(after, "Child", "Child.m")
    assert child_after["id"] == child_before["id"]
    assert [node["label"] for node in _targets(after, child_after)] == ["Base"]


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_unchanged_child_loses_inheritance_when_base_is_deleted(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    base_path.unlink()

    after = _merge(mode, root, graph_path, deleted=[base_path])

    child = _matlab_class(after, "Child", "Child.m")
    assert _targets(after, child) == []
    assert not any(node.get("source_file") == "Base.m" for node in after["nodes"])


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_newly_ambiguous_base_removes_inheritance(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "+pkg/Base.m", _class_source("Base"))
    child_path = _write(root, "+pkg/Child.m", _class_source("Child", "pkg.Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    child_before = _matlab_class(_read_graph(graph_path), "Child", "+pkg/Child.m")
    assert [node["label"] for node in _targets(_read_graph(graph_path), child_before)] == ["Base"]

    duplicate = _write(root, "other/+pkg/Base.m", _class_source("Base"))
    after = _merge(mode, root, graph_path, [duplicate])

    child_after = _matlab_class(after, "Child", "+pkg/Child.m")
    assert child_after["id"] == child_before["id"]
    assert _targets(after, child_after) == []


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_disambiguating_deleted_base_restores_inheritance(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    first = _write(root, "one/+pkg/Base.m", _class_source("Base"))
    second = _write(root, "two/+pkg/Base.m", _class_source("Base"))
    child_path = _write(root, "+pkg/Child.m", _class_source("Child", "pkg.Base"))
    _start_graph(mode, root, graph_path, [first, second, child_path])
    before = _read_graph(graph_path)
    child_before = _matlab_class(before, "Child", "+pkg/Child.m")
    assert _targets(before, child_before) == []

    first.unlink()
    after = _merge(mode, root, graph_path, deleted=[first])

    child_after = _matlab_class(after, "Child", "+pkg/Child.m")
    targets = _targets(after, child_after)
    assert len(targets) == 1
    assert targets[0].get("source_file") == "two/+pkg/Base.m"


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_deleted_child_removes_its_nodes_and_derived_inheritance(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    child_path.unlink()

    after = _merge(mode, root, graph_path, deleted=[child_path])

    assert not any(node.get("source_file") == "Child.m" for node in after["nodes"])
    assert not any(edge.get("source_file") == "Child.m" and edge.get("relation") == "inherits"
                   for edge in _edges(after))
    assert _matlab_class(after, "Base", "Base.m")


@pytest.mark.parametrize("mode", MERGE_PATHS)
def test_no_op_update_preserves_matlab_graph(tmp_path, mode):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph(mode, root, graph_path, [base_path, child_path])
    before = _read_graph(graph_path)

    after = _merge(mode, root, graph_path)

    assert _signature(after) == _signature(before)

def test_raw_graph_prune_refreshes_matlab_inheritance(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    graph_path = tmp_path / "graph.json"
    base_path = _write(root, "Base.m", _class_source("Base"))
    child_path = _write(root, "Child.m", _class_source("Child", "Base"))
    _start_graph("raw", root, graph_path, [base_path, child_path])
    before = _read_graph(graph_path)
    child = _matlab_class(before, "Child", "Child.m")
    assert [node["label"] for node in _targets(before, child)] == ["Base"]

    from graphify.cli import _prune_graph_json_sources

    assert _prune_graph_json_sources(graph_path, ["Base.m"]) > 0
    after = _read_graph(graph_path)
    child = _matlab_class(after, "Child", "Child.m")
    assert _targets(after, child) == []
    assert not any(node.get("source_file") == "Base.m" for node in after["nodes"])


@pytest.mark.parametrize("no_cluster", [True, False], ids=["raw-cli", "clustered-cli"])
def test_update_cli_refreshes_unchanged_matlab_child_after_base_change(tmp_path, no_cluster):
    import os
    import subprocess
    import sys

    root = tmp_path / "project"
    root.mkdir()
    base = _write(root, "Base.m", _class_source("Base", revision=1))
    _write(root, "Child.m", _class_source("Child", "Base"))
    options = ["--code-only"] + (["--no-cluster"] if no_cluster else [])
    first = subprocess.run(
        [sys.executable, "-m", "graphify", "extract", str(root), *options],
        cwd=tmp_path, capture_output=True, text=True, env=os.environ.copy(),
    )
    assert first.returncode == 0, first.stderr
    base.write_text(_class_source("Base", revision=2), encoding="utf-8")
    update_options = ["--no-cluster"] if no_cluster else []
    second = subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(root), *update_options],
        cwd=tmp_path, capture_output=True, text=True, env=os.environ.copy(),
    )
    assert second.returncode == 0, second.stderr

    graph = _read_graph(root / "graphify-out" / "graph.json")
    child_node = _matlab_class(graph, "Child", "Child.m")
    assert [node["label"] for node in _targets(graph, child_node)] == ["Base"]
