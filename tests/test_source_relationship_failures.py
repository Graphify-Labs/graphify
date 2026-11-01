"""INC-QML-89: rejected adoption and failed replacement retain accepted products."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import sys

import networkx as nx
import pytest

from graphify.cli import dispatch_command
from graphify.export import to_canvas
from graphify.paths import load_node_link_graph
from tests.source_relationship_helpers import logical_relations, source_graph, write_graph
from tests.test_source_relationship_merge import _isolated_global


@pytest.mark.parametrize("damage", ["contract", "direction", "storage_flag"])
def test_req_qml022_ac06_rejected_merge_retains_published_graph(tmp_path, monkeypatch, damage):
    """A typed promise cannot hide malformed metadata or a foreign endpoint marker."""
    graph, caller, local = source_graph(tmp_path / "source")
    if damage == "contract":
        graph.nodes[local]["metadata"]["csharp_local_function"]["contract_version"] = True
    elif damage == "direction":
        next(iter(graph[caller][local].values()))["_src"] = "foreign"
    source = write_graph(graph, tmp_path / "source" / "graphify-out" / "graph.json")
    if damage == "storage_flag":
        raw = json.loads(source.read_text())
        raw["multigraph"] = False
        source.write_text(json.dumps(raw))
    ordinary = write_graph(nx.Graph(), tmp_path / "keep" / "graphify-out" / "graph.json")
    output = write_graph(nx.Graph(), tmp_path / "merged.json")
    before = output.read_bytes()
    monkeypatch.setattr(sys, "argv", ["graphify", "merge-graphs", str(source), str(ordinary), "--out", str(output)])
    with pytest.raises(ValueError):
        dispatch_command("merge-graphs")
    assert output.read_bytes() == before


@pytest.mark.parametrize("damage", ["contract", "direction", "storage_flag"])
def test_req_qml022_ac06_rejected_global_adoption_retains_graph_and_manifest(tmp_path, monkeypatch, damage):
    """Rejection happens before either accepted global product is replaced."""
    service = _isolated_global(tmp_path, monkeypatch)
    service.global_add(write_graph(nx.Graph(), tmp_path / "ordinary.json"), "keep")
    before = (service.global_path().read_bytes(), service._GLOBAL_MANIFEST.read_bytes())
    graph, caller, local = source_graph(tmp_path / "source")
    if damage == "contract":
        graph.nodes[local]["metadata"]["csharp_local_function"]["contract_version"] = True
    elif damage == "direction":
        next(iter(graph[caller][local].values()))["_tgt"] = "foreign"
    source = write_graph(graph, tmp_path / "source.json")
    if damage == "storage_flag":
        raw = json.loads(source.read_text())
        raw["multigraph"] = False
        source.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        service.global_add(source, "source")
    assert (service.global_path().read_bytes(), service._GLOBAL_MANIFEST.read_bytes()) == before


def test_req_qml022_ac06_canvas_rejected_profile_retains_previous_file(tmp_path):
    """The typed metadata check precedes the actual canvas replacement boundary."""
    graph, _caller, local = source_graph(tmp_path / "source")
    output = tmp_path / "graph.canvas"
    to_canvas(graph, {}, str(output))
    before = output.read_bytes()
    graph.nodes[local]["metadata"]["csharp_local_function"]["span"] = []
    with pytest.raises(ValueError):
        to_canvas(graph, {}, str(output))
    assert output.read_bytes() == before


def test_req_qml022_ac06_global_real_replace_failure_retention_and_recovery(tmp_path, monkeypatch):
    """An actual graph replacement failure retains both products, then retries cleanly."""
    service = _isolated_global(tmp_path, monkeypatch)
    graph, _caller, old_local = source_graph(tmp_path / "source")
    source = write_graph(graph, tmp_path / "source.json")
    service.global_add(source, "source")
    before = (service.global_path().read_bytes(), service._GLOBAL_MANIFEST.read_bytes())
    changed, caller, local = source_graph(tmp_path / "source", local_name="Renamed")
    write_graph(changed, source)
    replace = os.replace

    def fail_graph(source_path, target_path):
        if Path(str(target_path).removeprefix("\\\\?\\")) == service.global_path():
            raise OSError(errno.EIO, "injected source graph replacement failure")
        return replace(source_path, target_path)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail_graph)
        with pytest.raises(OSError, match="injected"):
            service.global_add(source, "source")
    assert (service.global_path().read_bytes(), service._GLOBAL_MANIFEST.read_bytes()) == before
    service.global_add(source, "source")
    restored = load_node_link_graph(service.global_path())
    assert f"source::{old_local}" not in restored
    assert logical_relations(restored, f"source::{caller}", f"source::{local}") == {"contains", "calls"}
