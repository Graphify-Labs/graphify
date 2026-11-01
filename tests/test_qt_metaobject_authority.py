"""REQ-QML-022-AC03/06: own meta members require an actual source-owned Q_OBJECT."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.paths import load_node_link_graph
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_analysis_helpers import analysis
from tests.qt_metaobject_helpers import analyzed, bridge, facts, member_edges, member_sites, sources
from tests.test_qt_final_incremental_parity import normalized


@pytest.mark.parametrize("marker,expected", [
    ("", "unavailable"), ("#if ENABLED\nQ_OBJECT\n#endif", "dynamic"),
    ("Q_OBJECT Q_OBJECT", "ambiguous"), ("class Inner { Q_OBJECT };", "unavailable"),
    ('Q_CLASSINFO("marker", "Q_OBJECT")', "unavailable"), ("Q_OBJECT()", "unsupported"),
    ("int ÅQ_OBJECT;", "unavailable"), ("int Q_OBJECTÅ;", "unavailable"),
])
def test_req_qml022_ac03_ancestry_cannot_supply_own_metaobject_members(tmp_path, marker, expected):
    """Missing/conditional/duplicate/nested markers retain providers and C++ source facts only."""
    result = analyzed(tmp_path, marker)
    selected = member_sites(result)
    assert len(selected) == 3
    assert {qml_metadata(node)["status"] for node in selected} == {expected}
    assert not member_edges(result)
    index = bridge(tmp_path, result)
    assert index.module_type("Public.Probe", 1, 0, "Service").status == "resolved"
    owner = next(qt_metadata(node) for node in facts(result, "class") if qt_metadata(node)["raw_name"] == "Backend")
    assert owner["is_qobject"] is True and owner["status"] == "resolved"
    assert {qt_metadata(node)["raw_name"] for node in facts(result, "member")} >= {"ownMethod", "ordinary", "changed"}
    assert all(qt_metadata(node)["status"] == "resolved" for node in facts(result, "member"))


def test_req_qml022_ac03_stringified_payload_cannot_supply_metaobject(tmp_path):
    """QML_NAMED_ELEMENT stringifies Q_OBJECT as the type name, without enabling moc features."""
    result = analyzed(tmp_path, "", name="Q_OBJECT")
    assert len(member_sites(result)) == 3 and not member_edges(result)
    assert {qml_metadata(node)["status"] for node in member_sites(result)} == {"unavailable"}
    assert bridge(tmp_path, result).module_type("Public.Probe", 1, 0, "Q_OBJECT").status == "resolved"


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_own_marker_bytes_and_proof_survive_cold_warm_export(tmp_path, directed):
    """The exact BOM/CRLF token, class fact and accepted endpoint evidence survive real reload."""
    files = sources(crlf=True)
    graphs = []
    for phase in ("cold", "warm"):
        result = analyzed(tmp_path, crlf=True)
        assert len(member_sites(result)) == 3 and len(member_edges(result)) == 3
        marker, = facts(result, "metaobject")
        owner, = facts(result, "class")
        md = qt_metadata(marker)
        assert files["backend.hpp"].encode()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"Q_OBJECT"
        assert md["owner_id"] == md["class_id"] == qt_metadata(owner)["class_id"]
        assert md["conditional"] is False and md["status"] == "resolved"
        owned = [e for e in result["edges"] if e["target"] == marker["id"]]
        assert len(owned) == 1 and owned[0]["source"] == md["class_id"]
        for edge in member_edges(result):
            proof = qt_metadata(edge)["native_endpoint"]
            assert proof["metaobject_fact_id"] == marker["id"]
            assert {marker["id"], owner["id"]} <= set(proof["evidence"])
        graph = build_from_json(result, root=tmp_path, directed=directed)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        nodes = loaded.nodes
        owned = [{**data, "source": data.get("_src", src), "target": data.get("_tgt", dst)}
                 for src, dst, data in loaded.edges(data=True)]
        for edge in member_edges(result):
            src, dst = edge["source"], edge["target"]
            assert loaded.has_edge(src, dst)
            assert allows_qt_qml_edge(nodes[src], nodes[dst], loaded.edges[src, dst], source_id=src,
                                      target_id=dst, nodes=nodes, edges=owned)
        graphs.append(normalized(loaded))
    assert graphs[0] == graphs[1]
    direct = extract([tmp_path / name for name in files], root=tmp_path, cache_root=tmp_path / "fresh", parallel=False)
    assert {qt_metadata(n)["span"]["start_byte"] for n in facts(direct, "metaobject")} == {md["span"]["start_byte"]}


@pytest.mark.parametrize("corruption", ["missing", "count", "count_bool", "class_status", "class_id", "class_none",
    "owner", "owner_list", "marker_id", "kind_list", "source_flag", "file", "span", "span_bool", "edge_missing", "edge_owner",
    "edge_direction", "edge_file", "edge_span", "conditional"])
def test_req_qml022_ac06_corrupt_positive_marker_contract_rejects_before_lookup(tmp_path, corruption):
    """Missing or malformed promised marker/ownership data is integrity failure, unlike absent source syntax."""
    result = analyzed(tmp_path)
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    marker = next(n for n in nodes if qt_metadata(n).get("kind") == "metaobject")
    owner = next(n for n in nodes if qt_metadata(n).get("kind") == "class")
    edge = next(e for e in edges if e["target"] == marker["id"])
    if corruption == "missing":
        nodes.remove(marker)
    elif corruption == "count":
        update_qt(owner, metaobject_count=[])
    elif corruption == "count_bool":
        update_qt(owner, metaobject_count=True)
    elif corruption == "class_status":
        update_qt(owner, metaobject_status=[])
    elif corruption == "class_id":
        update_qt(marker, class_id=[])
    elif corruption == "class_none":
        update_qt(owner, class_id=None)
    elif corruption == "owner":
        update_qt(marker, owner_id="other")
    elif corruption == "owner_list":
        update_qt(marker, owner_id=[])
    elif corruption == "marker_id":
        marker["id"] = []
    elif corruption == "kind_list":
        update_qt(marker, kind=[])
    elif corruption == "source_flag":
        update_qt(owner, source_q_object=False)
    elif corruption == "file":
        marker["source_file"] = "other.hpp"
    elif corruption == "span":
        span = qt_metadata(marker)["span"]
        update_qt(marker, span={**span, "start_byte": span["start_byte"] + 1})
    elif corruption == "span_bool":
        update_qt(marker, span={**qt_metadata(marker)["span"], "start_byte": True})
    elif corruption == "conditional":
        update_qt(marker, conditional=True)
    elif corruption == "edge_missing":
        edges.remove(edge)
    elif corruption == "edge_owner":
        edge["source"] = edge["_src"] = "other"
    elif corruption == "edge_direction":
        edge["_src"] = "other"
    elif corruption == "edge_file":
        edge["source_file"] = "other.hpp"
    else:
        update_qt(edge, span={**qt_metadata(edge)["span"], "start_byte": 999_999})
    with pytest.raises(ValueError, match="QT_METADATA"):
        bridge(tmp_path, {"nodes": nodes, "edges": edges})


def test_req_qml022_ac06_serialized_member_proof_rejects_removed_marker(tmp_path):
    """An accepted edge cannot retain authority after its declaring metaobject fact disappears."""
    result = analyzed(tmp_path)
    nodes = {node["id"]: copy.deepcopy(node) for node in result["nodes"]}
    edge = member_edges(result)[0]
    marker, = facts(result, "metaobject")
    del nodes[marker["id"]]
    assert not allows_qt_qml_edge(nodes[edge["source"]], nodes[edge["target"]], edge,
        source_id=edge["source"], target_id=edge["target"], nodes=nodes, edges=result["edges"])


def test_req_qml022_ac06_nodes_only_consumer_cannot_borrow_marker_ownership(tmp_path):
    """Legacy optional signatures remain callable but a positive own-meta proof requires actual edges."""
    result = analyzed(tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    edge = member_edges(result)[0]
    args = {"source_id": edge["source"], "target_id": edge["target"], "nodes": nodes}
    assert not allows_qt_qml_edge(nodes[edge["source"]], nodes[edge["target"]], edge, **args)
    assert allows_qt_qml_edge(nodes[edge["source"]], nodes[edge["target"]], edge, **args, edges=result["edges"])


def test_req_qml022_ac03_context_type_hop_requires_actual_declaring_metaobject(tmp_path):
    """A valid typed provider/hop retains scope without lending its marker to the final child API."""
    from tests.qt_adoption_fixture import NATIVE, sources as context_sources
    native = NATIVE.replace("class Service : public QObject { Q_OBJECT", "class Service : public QObject {         ")
    result = analysis(tmp_path, context_sources(tmp_path, native=native))
    bindings = facts(result, "context_binding")
    assert len(bindings) == 1 and qt_metadata(bindings[0])["status"] == "resolved"
    service = next(qt_metadata(n)["class_id"] for n in facts(result, "class") if qt_metadata(n)["raw_name"] == "Service")
    for edge in result["edges"]:
        if edge.get("context") in {"qt_context_member", "qt_context_subscription"}:
            assert qt_metadata(edge)["endpoint_proof"]["class_id"] != service
    assert {qt_metadata(n)["raw_name"] for n in facts(result, "member")} >= {"makeBackend", "refresh", "ready"}


def test_req_qml022_ac06_corrupted_borrowed_marker_is_controlled_facade_failure(tmp_path):
    """Real incremental extraction rejects a broken promised marker and never mutates borrowed facts."""
    result = analyzed(tmp_path)
    nodes = copy.deepcopy([n for n in result["nodes"] if n.get("source_file") != "Main.qml"])
    edges = copy.deepcopy([e for e in result["edges"] if e.get("source_file") != "Main.qml"])
    marker = next(n for n in nodes if qt_metadata(n).get("kind") == "metaobject")
    update_qt(marker, owner_id="wrong-source-owner")
    before = copy.deepcopy((nodes, edges))
    rejected = extract([tmp_path / "Main.qml"], root=tmp_path, cache_root=tmp_path,
        resolution_context_nodes=nodes, resolution_context_edges=edges, parallel=False)
    assert rejected.get("qml_failures")
    assert {item["code"] for item in rejected["qml_failures"]} == {"QML_RESOLUTION_FAILED"}
    assert not member_edges(rejected) and (nodes, edges) == before


@pytest.mark.parametrize("corruption", ["identity", "span", "status", "relocated", "orphan", "missing_contract"])
def test_req_qml022_ac06_positive_marker_promise_cannot_lose_canonical_class(tmp_path, corruption):
    """A resolved own-metaobject promise must retain its unique accepted canonical class source."""
    result = analyzed(tmp_path)
    owner, = facts(result, "class")
    marker, = facts(result, "metaobject")
    if corruption == "identity":
        update_qt(owner, class_id="missing")
    elif corruption == "span":
        update_qt(owner, span={**qt_metadata(owner)["span"], "start_byte": qt_metadata(owner)["span"]["start_byte"] + 1})
    elif corruption == "status":
        update_qt(owner, status="unsupported")
    elif corruption == "relocated":
        update_qt(owner, class_id="missing", owner_id="missing")
        update_qt(marker, class_id="missing", owner_id="missing")
    elif corruption == "missing_contract":
        update_qt(owner, metaobject_contract=None)
    else:
        result["nodes"].remove(owner)
        update_qt(marker, class_id="missing", owner_id="missing")
    with pytest.raises(ValueError, match="QT_METADATA"):
        bridge(tmp_path, result)


@pytest.mark.parametrize("count", [50, 51])
def test_req_qml022_ac06_actual_source_marker_count_has_bounded_failure(tmp_path, count):
    """The exact source boundary retains50 ambiguous declarations and rejects51 without bindings."""
    files = sources(" ".join(["Q_OBJECT"] * count))
    for name, source in files.items():
        (tmp_path / name).write_bytes(source.encode())
    result = extract([tmp_path / name for name in files], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not member_edges(result)
    if count == 50:
        assert not result.get("qml_failures") and len(facts(result, "metaobject")) == 50
        assert {qml_metadata(n)["status"] for n in member_sites(result)} == {"ambiguous"}
    else:
        assert {item["code"] for item in result["qml_failures"]} == {"QT_CPP_LIMIT"}
        assert not facts(result, "metaobject")
