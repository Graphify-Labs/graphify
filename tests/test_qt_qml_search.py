"""Semantic metadata participates in production scoring without identity leakage."""
from __future__ import annotations

import copy

import networkx as nx
import pytest

from graphify.extractors.qml_facts import encode_metadata
from graphify.extractors.qt_cpp_facts import encode_qt
from graphify.qt_qml_search import SEARCH_NAMESPACE, search_attributes
from graphify.serve import _node_attributes_text, _pick_scored_endpoint, _query_graph_text, _score_nodes


def node():
    return {"id": "opaque_node", "label": "declaration", "attributes": {"user": {"note": "kept"}},
            "metadata": {"qt": encode_qt({"kind": "member", "raw_name": "fetch", "raw_type": "QList<Backend*>",
                                          "class_name": "Public::Backend", "signature": "fetch(int)",
                                          "roles": ["invokable"], "uri": "Public.Tools", "status": "resolved",
                                          "owner_id": "hidden_owner_93", "generic_target_id": "hidden_target_43"})}}


def test_decoded_names_types_roles_and_uris_are_indexed_without_mutating_facts():
    data = node()
    before = copy.deepcopy(data)
    attrs = search_attributes(data)
    assert attrs["user"] == before["attributes"]["user"]
    assert attrs[SEARCH_NAMESPACE]["qt"]["raw_type"] == "QList<Backend*>"
    norm, tokens = _node_attributes_text(data)
    assert all(value in norm for value in ("invokable", "public::backend", "fetch(int)", "public.tools", "qlist<backend*>"))
    assert "invokable" in tokens and "hidden_owner_93" not in norm and "hidden_target_43" not in norm
    assert "raw_values" not in norm
    assert data == before
    graph = nx.Graph()
    graph.add_node("native", **data)
    graph.add_node("unrelated", label="other")
    assert _score_nodes(graph, ["invokable"])[0][1] == "native"


def test_qml_import_value_is_semantic_but_arbitrary_literal_property_data_is_not():
    imported = {"metadata": {"qml": encode_metadata({"kind": "import", "value": "Public.Tools", "qualifier": "Tools"})}}
    assert search_attributes(imported)[SEARCH_NAMESPACE]["qml"]["import_value"] == "Public.Tools"
    prop = {"metadata": {"qml": encode_metadata({"kind": "property", "raw_name": "value", "literal_value": "private_text", "value": "private_text"})}}
    assert "private_text" not in str(search_attributes(prop))


@pytest.mark.parametrize("metadata", [None, "invalid", {"qt": []}, {"qt": {"contract_version": 2, "raw_name": "future"}},
                                    {"qt": {"contract_version": 1, "raw_values": {"raw_name": "!!!"}}}])
def test_missing_future_or_corrupted_metadata_preserves_existing_search(metadata):
    data = {"attributes": {"user": "existing"}, "metadata": metadata}
    assert search_attributes(data) == {"user": "existing"}
    assert "existing" in _node_attributes_text(data)[0]


def test_reserved_attribute_collision_wins_without_overwrite():
    data = node()
    data["attributes"][SEARCH_NAMESPACE] = {"custom": "kept"}
    before = copy.deepcopy(data)
    assert search_attributes(data) == data["attributes"]
    assert data == before


def test_metadata_text_and_list_work_are_bounded():
    data = {"metadata": {"qt": {"contract_version": 1, "kind": "member", "raw_name": "x" * 10_000,
                                "roles": ["x"] * 10_000, "uri": "Public.Tools"}}}
    view = search_attributes(data)[SEARCH_NAMESPACE]["qt"]
    assert "raw_name" not in view and "roles" not in view and view["uri"] == "Public.Tools"
    assert len(str(view)) < 100


@pytest.mark.parametrize("name", ["qt", "qml"])
def test_deep_malformed_literal_transport_cannot_crash_production_search(name):
    nested = "not encoded text"
    for _ in range(3000):
        nested = [nested]
    data = {"label": "safe", "attributes": {"user": "existing searchable text"},
            "metadata": {name: {"contract_version": 1, "kind": "member", "raw_name": "safe",
                                "raw_values": {"raw_name": nested}}}}
    assert search_attributes(data) == data["attributes"]
    assert "existing searchable text" in _node_attributes_text(data)[0]
    graph = nx.Graph()
    graph.add_node("safe", **data)
    assert "NODE safe" in _query_graph_text(graph, "existing", depth=1)
    assert data["metadata"][name]["raw_values"]["raw_name"] is nested


def test_public_event_semantics_are_searchable_without_indexing_supplied_data():
    data = {"metadata": {"qt": encode_qt({"kind": "connect", "declared_type": "QueuedConnection",
        "flags": ["UniqueConnection"], "callable_form": "member_pointer", "operation": "connect",
        "bridge_direction": "cpp_to_qml", "literal_value": "unrelated_private_literal"})}}
    text = _node_attributes_text(data)[0]
    assert all(value in text for value in ("queuedconnection", "uniqueconnection", "member_pointer", "cpp_to_qml"))
    assert "unrelated_private_literal" not in text


def test_exact_endpoint_identity_wins_over_fuzzy_token_collision():
    graph = nx.Graph()
    graph.add_node("qml:Main.qml:component:aaa", label="Main")
    graph.add_node("qml:Main.qml:property:bbb", label="input")
    scored = [(1000.0, "qml:Main.qml:component:aaa"), (1.0, "qml:Main.qml:property:bbb")]
    assert _pick_scored_endpoint(graph, scored, "qml:Main.qml:property:bbb") == "qml:Main.qml:property:bbb"


def test_fuzzy_endpoint_still_prefers_full_token_coverage():
    graph = nx.Graph()
    graph.add_node("summary", label="Rejection Summary")
    graph.add_node("judge", label="Degenerate Reject-Everything Judge")
    assert _pick_scored_endpoint(graph, [(1000, "summary"), (1, "judge")], "Reject-everything judge") == "judge"


def test_query_edge_rendering_is_identical_for_reversed_actual_graph_insertion(tmp_path):
    from graphify.build import build_from_json
    from tests.test_qt_qml_integration import corpus
    original = build_from_json(corpus(tmp_path), root=tmp_path)
    reversed_graph = nx.Graph()
    reversed_graph.add_nodes_from(reversed(list(original.nodes(data=True))))
    reversed_graph.add_edges_from(reversed(list(original.edges(data=True))))
    query = _query_graph_text(original, "next", depth=2)
    assert query == _query_graph_text(reversed_graph, "next", depth=2)
    assert "EDGE" in query and "qml_js_call" in query and "Main.qml:L" in query
