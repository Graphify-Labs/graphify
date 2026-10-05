"""REQ-QML-018-AC04/AC06: subscriptions retain their exact source callback."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.paths import load_node_link_graph
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_adoption_fixture import QML, sources
from tests.qt_analysis_helpers import analysis


def callback_view(tmp_path, result, stage, form):
    """Exercise raw facts and both graph orientations after real serialization."""
    if stage == "raw":
        nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
        by_id = {node["id"]: node for node in nodes}
    else:
        graph = build_from_json(result, root=tmp_path, directed=stage == "directed")
        path = tmp_path / "callbacks.json"
        assert to_json(graph, {}, str(path), force=True)
        restored = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
        by_id = restored.nodes
        edges = [{**attrs, "source": attrs.get("_src", source), "target": attrs.get("_tgt", target)}
                 for source, target, attrs in restored.edges(data=True)]
    edge = next(item for item in edges if item.get("context") == "qt_context_subscription"
                and qt_metadata(by_id[item["source"]]).get("subscription_form") == form)
    source_id, target_id = edge["source"], edge["target"]
    def accepted():
        return allows_qt_qml_edge(by_id[source_id], by_id[target_id], edge,
                                  source_id=source_id, target_id=target_id, nodes=by_id)
    assert accepted()
    return by_id, by_id[source_id], accepted


@pytest.mark.parametrize("stage", ["raw", "undirected", "directed"])
@pytest.mark.parametrize("form", ["signal.connect", "Connections"])
def test_req_qml018_ac04_ac06_callback_target_cannot_be_substituted(tmp_path, stage, form):
    """Changing only the derived target to a real sibling function must invalidate the bridge."""
    nodes, subscription, accepted = callback_view(tmp_path, analysis(tmp_path, sources(tmp_path)), stage, form)
    replacement = next(nid for nid, node in nodes.items() if qml_metadata(node).get("kind") == "function"
                       and qml_metadata(node).get("raw_name") == "run")
    update_qt(subscription, handler_target_id=replacement)
    assert not accepted()


@pytest.mark.parametrize("stage", ["raw", "undirected", "directed"])
def test_req_qml018_ac04_ac06_local_callback_precedes_same_named_qml_function(tmp_path, stage):
    """The captured local binder remains accepted; a same-name QML function cannot replace it."""
    qml = QML.replace("function run() {", "function run() { function handleReady() {}")
    nodes, subscription, accepted = callback_view(tmp_path, analysis(tmp_path, sources(tmp_path, qml=qml)), stage, "signal.connect")
    assert qml_metadata(nodes[qt_metadata(subscription)["handler_target_id"]])["kind"] == "js_function"
    replacement = next(nid for nid, node in nodes.items() if qml_metadata(node).get("kind") == "function"
                       and qml_metadata(node).get("raw_name") == "handleReady")
    update_qt(subscription, handler_target_id=replacement)
    assert not accepted()


@pytest.mark.parametrize("corruption", ["reference", "arity", "lexical", "name", "scope", "span", "handler_span", "form", "owner"])
def test_req_qml018_ac06_callback_borrowed_provenance_is_revalidated(tmp_path, corruption):
    """Accepted callback IDs do not repair changed call, declaration, scope or site ownership."""
    nodes, subscription, accepted = callback_view(tmp_path, analysis(tmp_path, sources(tmp_path)), "raw", "signal.connect")
    md = qt_metadata(subscription)
    call, handler = nodes[md["owner_id"]], nodes[md["handler_target_id"]]
    if corruption in {"form", "owner"}:
        update_qt(subscription, **({"subscription_form": "Connections"} if corruption == "form" else {"owner_id": md["handler_target_id"]}))
    elif corruption in {"span", "handler_span"}:
        span = md["span"] if corruption == "span" else qml_metadata(handler)["span"]
        span["start_byte"] += 1 if corruption == "span" else 1_000_000
        if corruption == "handler_span":
            span["end_byte"] += 1_000_000
            fields = {key: value for key, value in qml_metadata(handler).items() if key != "raw_values"}
            fields["span"] = span
            handler["metadata"]["qml"] = encode_metadata(fields)
        else:
            update_qt(subscription, span=span)
    else:
        chosen = handler if corruption in {"name", "scope"} else call
        fields = {key: value for key, value in qml_metadata(chosen).items() if key != "raw_values"}
        fields.update({"reference": {"callback_reference": "run"}, "arity": {"callback_argument_count": 2},
                       "lexical": {"callback_lexical_shadowed": True, "callback_lexical_target_id": ""},
                       "name": {"raw_name": "unrelated"}, "scope": {"object_scope_key": "unrelated"}}[corruption])
        chosen["metadata"]["qml"] = encode_metadata(fields)
    assert not accepted()


@pytest.mark.parametrize("stage", ["raw", "undirected", "directed"])
@pytest.mark.parametrize("callback", ["qualified", "own_scope"])
def test_req_qml018_ac04_callback_lookup_retains_object_scope(tmp_path, stage, callback):
    """A same-name root function cannot displace an own member or qualified ID member."""
    use = "backend.service.ready.connect(" + ("receiver.handleReady" if callback == "qualified" else "handleReady") + ")"
    child = " property QtObject nested: QtObject { id: receiver; function handleReady() {}\n"
    qml = "import QtQml\nQtObject {\n function handleReady() {}\n" + child
    qml += (" }\n function run() { " + use + " }\n" if callback == "qualified" else " function run() { " + use + " }\n }\n") + "}\n"
    nodes, subscription, _ = callback_view(tmp_path, analysis(tmp_path, sources(tmp_path, qml=qml)), stage, "signal.connect")
    selected = qml_metadata(nodes[qt_metadata(subscription)["handler_target_id"]])
    receiver = next(qml_metadata(node) for node in nodes.values() if qml_metadata(node).get("object_id") == "receiver")
    assert selected["object_scope_key"] == receiver["object_scope_key"]
