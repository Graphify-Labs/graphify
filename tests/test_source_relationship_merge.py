"""INC-QML-89: explicit merge/global adoption retain typed source relationships."""
from __future__ import annotations

import json
import sys

import networkx as nx
import pytest

from graphify.cli import dispatch_command
from graphify.paths import load_node_link_graph
from tests.source_relationship_helpers import logical_relations, source_graph, write_graph


def _isolated_global(tmp_path, monkeypatch):
    from graphify import global_graph
    directory = tmp_path / "global"
    monkeypatch.setattr(global_graph, "_GLOBAL_DIR", directory)
    monkeypatch.setattr(global_graph, "_GLOBAL_GRAPH", directory / "graph.json")
    monkeypatch.setattr(global_graph, "_GLOBAL_MANIFEST", directory / "manifest.json")
    return global_graph


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_merge_adopts_typed_local_relationships(tmp_path, monkeypatch, directed):
    """Mixed ordinary/typed inputs preserve real local ownership and calls after reload."""
    graph, caller, local = source_graph(tmp_path / "source", directed=directed)
    first = write_graph(graph, tmp_path / "qt" / "graphify-out" / "graph.json")
    ordinary = nx.Graph()
    ordinary.add_edge("left", "right", relation="imports", confidence="EXTRACTED")
    second = write_graph(ordinary, tmp_path / "other" / "graphify-out" / "graph.json")
    output = tmp_path / "merged.json"
    monkeypatch.setattr(sys, "argv", ["graphify", "merge-graphs", str(first), str(second), "--out", str(output)])
    dispatch_command("merge-graphs")
    merged = load_node_link_graph(output)
    assert merged.is_multigraph()
    assert logical_relations(merged, f"qt::{caller}", f"qt::{local}") == {"contains", "calls"}
    assert {"other::left", "other::right"} <= set(merged)


def test_req_qml022_ac06_global_promotes_legacy_store_and_retains_other_repo(tmp_path, monkeypatch):
    """Adding a typed repo preserves the preexisting global repo and both source facts."""
    service = _isolated_global(tmp_path, monkeypatch)
    ordinary = nx.Graph()
    ordinary.add_edge("left", "right", relation="imports", confidence="EXTRACTED")
    service.global_add(write_graph(ordinary, tmp_path / "ordinary.json"), "keep")
    graph, caller, local = source_graph(tmp_path / "source")
    path = write_graph(graph, tmp_path / "source.json")
    service.global_add(path, "source")
    merged = load_node_link_graph(service.global_path())
    assert merged.is_multigraph()
    assert logical_relations(merged, f"source::{caller}", f"source::{local}") == {"contains", "calls"}
    assert {"keep::left", "keep::right"} <= set(merged)
    before = service.global_path().read_bytes()
    assert service.global_add(path, "source")["skipped"] is True
    assert service.global_path().read_bytes() == before


def test_req_qml022_ac06_global_update_retires_old_local_and_keeps_relations(tmp_path, monkeypatch):
    """Refreshing one repo removes its old source identity without stale parallel facts."""
    service = _isolated_global(tmp_path, monkeypatch)
    graph, caller, old = source_graph(tmp_path / "source")
    path = write_graph(graph, tmp_path / "source.json")
    service.global_add(path, "source")
    changed, caller, local = source_graph(tmp_path / "source", local_name="Renamed")
    write_graph(changed, path)
    service.global_add(path, "source")
    merged = load_node_link_graph(service.global_path())
    assert f"source::{old}" not in merged
    assert logical_relations(merged, f"source::{caller}", f"source::{local}") == {"contains", "calls"}


def test_req_qml022_ac06_global_ordinary_input_remains_simple(tmp_path, monkeypatch):
    """A C# label alone cannot activate the typed source storage profile."""
    service = _isolated_global(tmp_path, monkeypatch)
    ordinary = nx.MultiGraph()
    ordinary.add_node("Local", label="Local", source_file="Data.cs", _callable=True)
    ordinary.add_edge("Use", "Local", relation="contains")
    ordinary.add_edge("Use", "Local", relation="calls")
    service.global_add(write_graph(ordinary, tmp_path / "ordinary.json"), "legacy")
    restored = load_node_link_graph(service.global_path())
    assert not restored.is_multigraph() and restored.number_of_edges() == 1
