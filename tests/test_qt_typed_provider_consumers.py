"""REQ-QML-018-AC03/AC04/AC06: declared chains retain guarded consumer evidence."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import encode_qt, qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_analysis_helpers import analysis
from tests.qt_adoption_fixture import sources


def bridge_edges(result):
    return [edge for edge in result["edges"] if edge.get("context") in
            {"qt_context_member", "qt_context_subscription"}]


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml018_ac04_typed_subscriptions_survive_build_reload_and_query(tmp_path, directed):
    """Producer direction reaches the native signal and QML handler through distinct sites."""
    result = analysis(tmp_path, sources(tmp_path))
    expected = bridge_edges(result)
    assert len(expected) == 5
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path), force=True)
    restored = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    for edge in expected:
        assert restored.has_edge(edge["source"], edge["target"])
        metadata = restored.edges[edge["source"], edge["target"]]
        assert qt_metadata(metadata)["endpoint_proof"] == qt_metadata(edge)["endpoint_proof"]
        if not directed:
            assert (metadata["_src"], metadata["_tgt"]) == (edge["source"], edge["target"])
    from graphify.serve import _query_graph_text
    answer = _query_graph_text(restored, "native_service_ready", token_budget=8000)
    assert "qt_context_subscription" in answer and "Main.qml" in answer and "references" in answer


@pytest.mark.parametrize("corruption", ["hop", "accessor", "provider", "class", "handler", "role", "transport"])
def test_req_qml018_ac06_corrupted_endpoint_or_chain_is_rejected_at_consumer(tmp_path, corruption):
    """A copied serialized bridge cannot lend authority to altered declarations or roles."""
    result = analysis(tmp_path, sources(tmp_path))
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    by_id = {node["id"]: node for node in nodes}
    edge = next(edge for edge in edges if edge.get("context") == "qt_context_subscription")
    source, target = by_id[edge["source"]], by_id[edge["target"]]
    md = qt_metadata(source)
    proof = qt_metadata(edge)["endpoint_proof"]
    if corruption == "hop":
        proof["type_chain"][0]["target_class_id"] = md["binding_id"]
        fields = {key: value for key, value in qt_metadata(edge).items() if key != "raw_values"}
        fields["endpoint_proof"] = proof
        edge["metadata"]["qt"] = encode_qt(fields)
    else:
        chosen = (by_id[proof["type_chain"][0]["property_id"]] if corruption == "accessor" else
                  by_id[md["binding_id"]] if corruption == "provider" else
                  by_id[proof["class_id"]] if corruption == "class" else
                  by_id[proof["member_fact_id"]] if corruption in {"role", "transport"} else source)
        if corruption == "class":
            chosen["_callable_class"] = False
        elif corruption == "transport":
            chosen["metadata"]["qt"]["raw_values"]["raw_name"] = "invalid!"
        else:
            fields = {key: value for key, value in qt_metadata(chosen).items() if key != "raw_values"}
            fields[{"accessor": "api_type_target_id", "provider": "provider_type_evidence",
                    "handler": "handler_target_id", "role": "roles"}[corruption]] = [] if corruption in {"provider", "role"} else "missing"
            chosen["metadata"]["qt"] = encode_qt(fields)
    assert not allows_qt_qml_edge(source, target, edge, source_id=source["id"], target_id=target["id"], nodes=by_id)
