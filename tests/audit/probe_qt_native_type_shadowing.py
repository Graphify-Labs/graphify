"""Opt-in audit of native type authority through completed graph publication.

Invoke this ``probe_`` file explicitly with pytest; normal ``test_*.py`` discovery
excludes it. Unsafe alias assertions intentionally fail until lexical authority is
implemented or the unsupported use is rejected. No C++/QML code executes. Unknown
targets are acceptable; an unrelated same-spelling global class is never proof.
"""
from __future__ import annotations

import json

import pytest

from graphify.affected import load_graph
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_qml_bridge import build_qt_qml_bridge

DECLARATIONS = """class Sender : public QObject { Q_OBJECT
signals: void changed(int value);
};
class Receiver : public QObject { Q_OBJECT
public: void accept(int value) {}
};
class Other : public QObject { Q_OBJECT
signals: void changed(int value);
};
"""
ALIASES = ["using Sender = Other;", "typedef Other Sender;"]
QML = "import Demo 1.0\nThing { onChanged: (value) => {} }\n"


def persisted(root, source, *, qml=False):
    """Synthetic bytes enter the real facade, assembly, JSON writer and loader."""
    path = root / "events.cpp"
    path.write_bytes(source.encode("utf-8"))
    paths = [path]
    if qml:
        qml_path = root / "Main.qml"
        qml_path.write_bytes(QML.encode("utf-8"))
        paths.append(qml_path)
    result = extract(paths, root=root, cache_root=root / "cache", parallel=False,
                     qml_import_roots=(".",))
    assert not result.get("qml_failures") and not result.get("qt_failures")
    output = root / "proof.json"
    graph = build_from_json(result, root=root)
    assert to_json(graph, {}, str(output), force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    reloaded = load_graph(output)
    assert reloaded.is_directed()
    # Evidence belongs to original file bytes, not normalized source/graph labels.
    for node in payload["nodes"]:
        metadata = qt_metadata(node) or qml_metadata(node)
        if not metadata or not metadata.get("span"):
            continue
        data = (root / node["source_file"]).read_bytes()
        span = metadata["span"]
        start, end = span["start_byte"], span["end_byte"]
        assert 0 <= start <= end <= len(data)
        for prefix, offset in (("start", start), ("end", end)):
            preceding = data[:offset]
            assert span[prefix + "_row"] == preceding.count(b"\n")
            assert span[prefix + "_column"] == len(preceding.rsplit(b"\n", 1)[-1])
    return result, payload, reloaded


def native_facts(result, kind):
    return [node for node in result["nodes"] if qt_metadata(node).get("kind") == kind]


def native_signal(result, class_name):
    return next(node for node in native_facts(result, "member")
                if qt_metadata(node).get("class_name") == class_name
                and qt_metadata(node).get("raw_name") == "changed")


def endpoint_links(payload, site):
    """Role nodes retain logical direction after default undirected assembly."""
    role_ids = {node["id"] for node in payload["nodes"]
                if qt_metadata(node).get("kind") == "event_endpoint"
                and qt_metadata(node).get("owner_id") == site["id"]}
    return [edge for edge in payload["links"]
            if edge["source"] in role_ids | {site["id"]}
            and edge.get("context") in {"qt_connect_signal", "qt_signal_emit"}]


def assert_no_wrong_signal(result, payload, graph, site):
    """Unsupported aliases may remain unresolved; wrong persisted edges may not."""
    wrong = native_signal(result, "Sender")
    forbidden = {wrong["id"], qt_metadata(wrong)["generic_target_id"]}
    links = endpoint_links(payload, site)
    assert not [edge for edge in links if edge["target"] in forbidden], links
    for edge in links:
        assert graph.has_edge(edge["source"], edge["target"])
    metadata = qt_metadata(site)
    assert metadata.get("signal_target_id") not in forbidden, metadata
    assert metadata.get("target_id") not in forbidden, metadata


@pytest.mark.parametrize("alias", ALIASES, ids=["using", "typedef"])
def test_req_qml016_connect_alias_cannot_select_unrelated_global_signal(tmp_path, alias):
    """A local alias shadows Sender; connect must not persist global Sender's signal."""
    source = DECLARATIONS + f"""void wire(Other *original, Receiver *receiver) {{
 {alias}
 Sender *sender = original;
 QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept);
}}
"""
    result, payload, graph = persisted(tmp_path, source)
    site = native_facts(result, "connect")[0]
    assert_no_wrong_signal(result, payload, graph, site)


@pytest.mark.parametrize("alias", ALIASES, ids=["using", "typedef"])
def test_req_qml016_emission_alias_cannot_select_unrelated_global_signal(tmp_path, alias):
    """An explicit alias-typed receiver supplies no authority for the global class."""
    source = DECLARATIONS + f"""void send(Other *original) {{
 {alias}
 Sender *sender = original;
 emit sender->changed(1);
}}
"""
    result, payload, graph = persisted(tmp_path, source)
    assert_no_wrong_signal(result, payload, graph, native_facts(result, "emission")[0])


def registration_proof(root, alias, raw_type="Sender"):
    source = DECLARATIONS + f"""void install() {{
 {alias}
 qmlRegisterType<{raw_type}>("Demo", 1, 0, "Thing");
}}
"""
    result, payload, graph = persisted(root, source, qml=True)
    bridge = build_qt_qml_bridge(result["nodes"], result["edges"], root=root)
    provider = bridge.module_type("Demo", 1, 0, "Thing")
    handlers = [node for node in payload["nodes"] if qml_metadata(node).get("kind") == "handler"]
    assert len(handlers) == 1
    return result, payload, graph, bridge, provider, handlers[0]


@pytest.mark.parametrize("alias", ALIASES, ids=["using", "typedef"])
def test_req_qml008_alias_registration_cannot_export_global_class_to_qml(tmp_path, alias):
    """Completed native registration→QML handler edges must honor type authority."""
    result, payload, graph, bridge, provider, handler = registration_proof(tmp_path, alias)
    wrong = native_signal(result, "Sender")
    forbidden = {wrong["id"], qt_metadata(wrong)["generic_target_id"]}
    links = [edge for edge in payload["links"] if edge["source"] == handler["id"]
             and edge.get("context") == "qml_signal_subscription"]
    assert not [edge for edge in links if edge["target"] in forbidden], links
    assert qml_metadata(handler).get("resolved_target_id") not in forbidden
    wrong_class = qt_metadata(wrong)["class_id"]
    assert qt_metadata(native_facts(result, "registration")[0]).get("class_id") != wrong_class
    if provider.target_id:
        assert bridge.provider_records[provider.target_id]["class_id"] != wrong_class
    for edge in links:
        assert graph.has_edge(edge["source"], edge["target"])


def test_req_qml016_block_alias_does_not_change_before_and_after_native_scope(tmp_path):
    """The alias applies inside its block; globally suppressing Sender is insufficient."""
    source = DECLARATIONS + """void wire(Sender *outer, Other *other, Receiver *receiver) {
 QObject::connect(outer, &Sender::changed, receiver, &Receiver::accept);
 { using Sender = Other; Sender *inner = other;
   QObject::connect(inner, &Sender::changed, receiver, &Receiver::accept); }
 QObject::connect(outer, &Sender::changed, receiver, &Receiver::accept);
}
"""
    result, payload, graph = persisted(tmp_path, source)
    before, inside, after = native_facts(result, "connect")
    target = native_signal(result, "Sender")["id"]
    assert qt_metadata(before)["signal_target_id"] == target
    assert qt_metadata(after)["signal_target_id"] == target
    assert {edge["target"] for edge in endpoint_links(payload, before)} == {target}
    assert {edge["target"] for edge in endpoint_links(payload, after)} == {target}
    assert_no_wrong_signal(result, payload, graph, inside)


@pytest.mark.parametrize("class_name", ["Sender", "Other"])
def test_direct_native_type_control_preserves_roles_and_direction(tmp_path, class_name):
    """Unshadowed connections/emissions retain distinct roles and logical direction."""
    source = DECLARATIONS + f"""void wire({class_name} *sender, Receiver *receiver) {{
 QObject::connect(sender, &{class_name}::changed, receiver, &Receiver::accept);
 emit sender->changed(1);
}}
"""
    result, payload, graph = persisted(tmp_path, source)
    connection = native_facts(result, "connect")[0]
    emission = native_facts(result, "emission")[0]
    signal = native_signal(result, class_name)["id"]
    assert qt_metadata(connection)["status"] == qt_metadata(emission)["status"] == "resolved"
    for site in (connection, emission):
        links = endpoint_links(payload, site)
        assert len(links) == 1 and links[0]["target"] == signal
        assert graph.has_edge(links[0]["source"], signal)
        assert not graph.has_edge(signal, links[0]["source"])
    roles = [node for node in payload["nodes"]
             if qt_metadata(node).get("kind") == "event_endpoint"
             and qt_metadata(node).get("owner_id") == connection["id"]]
    assert {qt_metadata(node)["role"] for node in roles} == {"signal", "receiver"}
    assert len({node["id"] for node in roles}) == 2
    assert not any(edge["source"] == connection["id"] and edge.get("relation") == "calls"
                   for edge in payload["links"])


@pytest.mark.parametrize("class_name", ["Sender", "Other"])
def test_direct_registration_control_preserves_native_qml_endpoint(tmp_path, class_name):
    """A literal unshadowed registration exports only its actual native signal."""
    result, payload, graph, bridge, provider, handler = registration_proof(tmp_path, "", class_name)
    signal = native_signal(result, class_name)
    assert provider.status == "resolved"
    assert bridge.provider_records[provider.target_id]["class_id"] == qt_metadata(signal)["class_id"]
    target = qt_metadata(signal)["generic_target_id"]
    assert qml_metadata(handler)["status"] == "resolved"
    assert qml_metadata(handler)["resolved_target_id"] == target
    links = [edge for edge in payload["links"] if edge["source"] == handler["id"]
             and edge.get("context") == "qml_signal_subscription"]
    assert len(links) == 1 and links[0]["target"] == target
    assert graph.has_edge(handler["id"], target) and not graph.has_edge(target, handler["id"])
