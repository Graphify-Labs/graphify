"""INC-QML-31: JSON export rejects forged direction before durable publication."""
from __future__ import annotations

import copy
import json
import sys
from types import SimpleNamespace

import networkx as nx
import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_cypher, to_json
from graphify.exporters.graphdb import push_to_falkordb, push_to_neo4j
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_export import preflight_qt_payload, qt_cypher_lines
from tests.qt_analysis_helpers import analysis
from tests.test_qt_qml_integration import corpus


def actual_graph(root, directed=False):
    """Accepted original QML source supplies real typed reference and source-owner facts."""
    result = analysis(root, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }"})
    graph = build_from_json(result, root=root, directed=directed)
    source = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    target = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "property"
                  and qml_metadata(node).get("raw_name") == "input")
    return graph, source, target


def damage(data, corruption, source, target):
    """Mutate only marker transport, preserving the actual accepted graph endpoint pair."""
    data["_src"], data["_tgt"] = source, target
    if corruption == "partial_source":
        data.pop("_tgt")
    elif corruption == "partial_target":
        data.pop("_src")
    elif corruption == "foreign_source":
        data["_src"] = "private-needle\nforged diagnostic"
    elif corruption == "foreign_target":
        data["_tgt"] = "foreign"
    elif corruption == "null":
        data["_src"] = None
    elif corruption == "list":
        data["_src"] = [source]
    elif corruption == "mapping":
        data["_tgt"] = {"id": target}
    elif corruption == "collapsed":
        data["_tgt"] = source
    else:
        data["_src"], data["_tgt"] = target, source


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("corruption", ["partial_source", "partial_target", "foreign_source", "foreign_target",
                                      "null", "list", "mapping", "collapsed"])
def test_json_direction_rejection_preserves_previous_bytes_and_safe_diagnostic(tmp_path, capsys,
                                                                             directed, force, corruption):
    """Neither explicit force nor malformed marker types can replace the previous accepted graph."""
    graph, source, target = actual_graph(tmp_path, directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), built_at_commit="fixed")
    accepted = path.read_bytes()
    edge = graph.edges[source, target]
    damage(edge, corruption, source, target)
    before = copy.deepcopy(nx.node_link_data(graph, edges="links"))
    assert to_json(graph, {}, str(path), force=force, built_at_commit="fixed") is False
    assert path.read_bytes() == accepted
    assert nx.node_link_data(graph, edges="links") == before
    diagnostic = capsys.readouterr().err
    assert "QT_EXPORT_DIRECTION" in diagnostic
    assert "private-needle" not in diagnostic and "forged diagnostic" not in diagnostic
    assert str(path) not in diagnostic
    # Repair uses the same production writer; repeated success preserves bytes
    # and the actual read remains a dependency after the durable reload.
    edge["_src"], edge["_tgt"] = source, target
    assert to_json(graph, {}, str(path), built_at_commit="fixed")
    assert path.read_bytes() == accepted
    loaded = load_node_link_graph(path)
    assert source in {hit.node_id for hit in affected_nodes(loaded, target, depth=1)}


def test_json_directed_contradiction_rejects_before_first_file_exists(tmp_path, capsys):
    """A directed graph cannot reverse its real accepted pair; refusal creates no partial JSON."""
    graph, source, target = actual_graph(tmp_path, directed=True)
    damage(graph.edges[source, target], "reversed", source, target)
    path = tmp_path / "first.json"
    assert to_json(graph, {}, str(path), force=True) is False
    assert not path.exists() and "QT_EXPORT_DIRECTION" in capsys.readouterr().err


@pytest.mark.parametrize("graph_type", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph])
def test_legacy_unmarked_edges_and_valid_self_pairs_preserve_native_identity(tmp_path, graph_type):
    """Generic graphs retain native direction, loops, parallel facts and original values."""
    graph = graph_type()
    graph.add_edge("caller", "callee", relation="calls", context="ordinary", confidence="EXTRACTED")
    graph.add_edge("caller", "caller", relation="references", _src="caller", _tgt="caller")
    if graph.is_multigraph():
        graph.add_edge("caller", "callee", relation="references", context="second")
    before = copy.deepcopy(nx.node_link_data(graph, edges="links"))
    path = tmp_path / "legacy.json"
    assert to_json(graph, {}, str(path), built_at_commit="fixed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["directed"] == graph.is_directed() and payload["multigraph"] == graph.is_multigraph()
    assert len(payload["links"]) == graph.number_of_edges()
    assert all((edge["source"], edge["target"]) in {(u, v) for u, v in graph.edges()} for edge in payload["links"])
    assert nx.node_link_data(graph, edges="links") == before
    assert to_json(graph, {}, str(path), built_at_commit="fixed")


def test_undirected_reversed_storage_retains_real_qml_dependency_direction(tmp_path):
    """Reversing physical insertion order must not reverse an accepted QML read after reload."""
    graph, source, target = actual_graph(tmp_path)
    reversed_graph = nx.Graph()
    reversed_graph.add_node(target, **graph.nodes[target])
    reversed_graph.add_nodes_from((identity, data) for identity, data in graph.nodes(data=True) if identity != target)
    reversed_graph.add_edges_from((v, u, copy.deepcopy(data)) for u, v, data in graph.edges(data=True))
    assert next((u, v) for u, v in reversed_graph.edges() if {u, v} == {source, target}) == (target, source)
    path = tmp_path / "reversed.json"
    assert to_json(reversed_graph, {}, str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    edge = next(data for data in payload["links"] if data.get("context") == "qml_binding_read")
    assert (edge["source"], edge["target"]) == (source, target)
    assert source in {hit.node_id for hit in affected_nodes(load_node_link_graph(path), target, depth=1)}


@pytest.mark.parametrize("directed", [False, True])
def test_native_source_proof_export_reload_consumer_survives_rejection_and_repair(tmp_path, directed):
    """Actual C++ registration joins preserve exact native endpoint proof across the corrected boundary."""
    result = corpus(tmp_path)
    call = next(edge for edge in result["edges"] if edge.get("context") == "qml_js_call")
    source, target = call["source"], call["target"]
    assert qt_metadata(call)["native_endpoint"]["canonical_target_id"] == target
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "native.json"
    assert to_json(graph, {}, str(path), built_at_commit="fixed")
    accepted = path.read_bytes()
    edge = graph.edges[source, target]
    damage(edge, "foreign_source", source, target)
    assert to_json(graph, {}, str(path), force=True) is False and path.read_bytes() == accepted
    edge["_src"], edge["_tgt"] = source, target
    assert to_json(graph, {}, str(path), built_at_commit="fixed") and path.read_bytes() == accepted
    restored = load_node_link_graph(path)
    assert qt_metadata(restored.edges[source, target])["native_endpoint"] == qt_metadata(call)["native_endpoint"]
    assert restored.edges[source, target]["source_location"] == call["source_location"]
    assert source in {hit.node_id for hit in affected_nodes(restored, target, depth=1)}


@pytest.mark.parametrize("corruption", ["partial_source", "partial_target", "foreign_source", "foreign_target",
                                      "null", "list", "mapping", "collapsed"])
def test_external_direction_rejection_precedes_file_or_database_connection(tmp_path, monkeypatch, corruption):
    """External preflight shares strict malformed-pair rejection without printing untrusted values."""
    graph, source, target = actual_graph(tmp_path)
    damage(graph.edges[source, target], corruption, source, target)
    before = copy.deepcopy(nx.node_link_data(graph, edges="links"))
    path = tmp_path / "previous.cypher"
    path.write_bytes(b"previous valid export")

    def forbidden(*_, **__):
        pytest.fail("Direction rejection must precede database creation or connection")

    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(GraphDatabase=SimpleNamespace(driver=forbidden)))
    monkeypatch.setitem(sys.modules, "falkordb", SimpleNamespace(FalkorDB=forbidden))
    for action in (lambda: preflight_qt_payload(graph), lambda: qt_cypher_lines(graph),
                   lambda: to_cypher(graph, str(path)), lambda: push_to_neo4j(graph, "unused", "", ""),
                   lambda: push_to_falkordb(graph, "unused")):
        with pytest.raises(ValueError, match="QT_EXPORT_DIRECTION") as rejected:
            action()
        assert "private-needle" not in str(rejected.value) and "forged diagnostic" not in str(rejected.value)
    assert path.read_bytes() == b"previous valid export" and nx.node_link_data(graph, edges="links") == before


def test_external_bidirectional_wrapper_honors_logical_pair_but_json_requires_native_direction(tmp_path):
    """The external adapter retains its wrapper contract while JSON refuses contradictory native identity."""
    graph, source, target = actual_graph(tmp_path)
    wrapper = nx.MultiDiGraph(graph)
    preflight_qt_payload(wrapper)
    lines = qt_cypher_lines(wrapper)
    assert lines and any(f'id:{json.dumps(source)}' in line and f'id:{json.dumps(target)}' in line for line in lines)
    path = tmp_path / "wrapper.json"
    assert to_json(wrapper, {}, str(path), force=True) is False and not path.exists()
