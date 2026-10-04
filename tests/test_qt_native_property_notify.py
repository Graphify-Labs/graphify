"""REQ-QML-007/008/017: native property handlers use the actual NOTIFY signal."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from tests.qt_analysis_helpers import analysis


def sources(*, notify="updated", parameters="", attribute="", handlers="normal", signal_role="signals", extra="", module=True):
    """Qmake owns registration; source declarations own property/accessor/signal proof."""
    clause = "NOTIFY " + notify if notify else ""
    header = f'''// Original bytes: café
class Backend : public QObject {{ Q_OBJECT QML_ELEMENT
 Q_PROPERTY(int count READ count {clause} {attribute})
 {extra}
 public: int count() const;
 {signal_role}: void {notify or 'updated'}({parameters});
}};
'''
    if handlers == "normal":
        body = 'Backend { id: backend; onCountChanged: { count; } }'
    elif handlers == "connections":
        body = ('Backend { id: backend; property Connections observer: Connections { '
                'target: backend; function onCountChanged() { count; } } }')
    else:
        body = ('Backend { id: backend; onCountChanged: {}; onTotalChanged: {} }')
    files = {"backend.h": "\ufeff" + header.replace("\n", "\r\n"),
             "Main.qml": 'import QtQml\nimport Public.Tools 1.0\n' + body + '\n'}
    if module:
        files["tools.pro"] = 'QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_VERSION = 1.0\nHEADERS += backend.h\nQML_FILES += Main.qml\n'
    return files


def persisted(root, files, *, directed=False):
    """Cross-language endpoint proof survives actual graph publication and reload."""
    result = analysis(root, files)
    graph = build_from_json(result, root=root, directed=directed)
    output = root / "notify.json"
    assert to_json(graph, {}, str(output), force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    restored = load_node_link_graph(payload)
    handlers = {node["id"]: node for node in result["nodes"] if qml_metadata(node).get("kind") == "handler"}
    links = [edge for edge in payload["links"] if edge["source"] in handlers and edge.get("context") == "qml_signal_subscription"]
    return result, restored, handlers, links, output


def assert_notify(result, graph, handlers, links, expected="updated"):
    """Each handler references the exact canonical signal with source-owned evidence."""
    assert handlers and len(links) == len(handlers)
    native_members = {node["id"]: node for node in result["nodes"] if qt_metadata(node).get("kind") == "member"}
    for edge in links:
        site, target = handlers[edge["source"]], graph.nodes[edge["target"]]
        md, proof = qml_metadata(site), qt_metadata(edge)["native_endpoint"]
        assert md["status"] == "resolved" and md["resolved_target_id"] == edge["target"]
        assert target["source_file"] == "backend.h" and target["label"].lstrip(".") == expected + "()"
        assert edge["relation"] == "references" and edge["confidence"] == "INFERRED"
        assert graph.has_edge(edge["source"], edge["target"])
        if graph.is_directed():
            assert not graph.has_edge(edge["target"], edge["source"])
        else:
            assert (graph.edges[edge["source"], edge["target"]]["_src"],
                    graph.edges[edge["source"], edge["target"]]["_tgt"]) == (edge["source"], edge["target"])
        assert proof["kind"] == "signal" and proof["canonical_target_id"] == edge["target"]
        member = native_members[proof["member_fact_id"]]
        assert qt_metadata(member)["raw_name"] == expected and "signal" in qt_metadata(member)["roles"]
        if md.get("reason") == "native_property_notify_signal":
            evidence = [qt_metadata(node) for node in result["nodes"] if node["id"] in proof["evidence"]]
            assert any(item.get("kind") == "property" for item in evidence)
            assert any(item.get("kind") == "property_accessor" and item.get("accessor_role") == "notify" for item in evidence)
        assert edge["source_file"] == "Main.qml" and edge["source_location"] == site["source_location"]
        span = md["span"]
        original = next(node for node in result["nodes"] if node["id"] == site["id"])
        assert original["source_location"].startswith("L") and qt_metadata(edge)["span"] == span


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("handlers", ["normal", "connections"])
@pytest.mark.parametrize("notify", ["updated", "countChanged"])
def test_req_qml007_ac03_native_property_handler_maps_custom_and_conventional_notify(tmp_path, directed, handlers, notify):
    """QML's handler spelling is property-based even when C++ signal differs."""
    result, graph, sites, edges, _ = persisted(tmp_path, sources(notify=notify, handlers=handlers), directed=directed)
    assert_notify(result, graph, sites, edges, notify)
    original = (tmp_path / "backend.h").read_bytes()
    prop = next(qt_metadata(node) for node in result["nodes"] if qt_metadata(node).get("kind") == "property")
    span = prop["span"]
    assert original[span["start_byte"]:span["end_byte"]] == f"Q_PROPERTY(int count READ count NOTIFY {notify} )".encode()
    signal = next(qt_metadata(node) for node in result["nodes"]
                  if qt_metadata(node).get("kind") == "member" and qt_metadata(node).get("raw_name") == notify)
    member_span = signal["span"]
    assert notify.encode() + b"(" in original[member_span["start_byte"]:member_span["end_byte"]]


def test_req_qml008_ac02_shared_notify_preserves_two_independent_handler_sites(tmp_path):
    """Shared NOTIFY signals do not collapse the two source handler occurrences."""
    extra = 'Q_PROPERTY(int total READ total NOTIFY updated) public: int total() const;'
    result, graph, sites, edges, _ = persisted(tmp_path, sources(extra=extra, handlers="shared"))
    assert_notify(result, graph, sites, edges)
    assert len(edges) == 2 and len({edge["source"] for edge in edges}) == 2
    assert len({edge["target"] for edge in edges}) == 1


@pytest.mark.parametrize("options", [
    {"notify": ""}, {"notify": "", "attribute": "CONSTANT"},
    {"attribute": "CONSTANT"}, {"signal_role": "public"},
    {"parameters": "QString changed"}, {"attribute": "REVISION 1"},
    {"module": False},
])
def test_req_qml008_ac03_invalid_or_unexposed_notify_cannot_create_subscription(tmp_path, options):
    """Missing notification, ordinary methods, type/version/provider gaps stay explicit."""
    _, _, sites, edges, _ = persisted(tmp_path, sources(**options))
    assert sites and not edges
    assert all(qml_metadata(site)["status"] != "resolved" and not qml_metadata(site).get("resolved_target_id") for site in sites.values())


@pytest.mark.parametrize("parameters", ["", "int count"])
def test_req_qml007_ac03_notify_parameter_binding_uses_actual_signal_signature(tmp_path, parameters):
    """A signal parameter shadows a same-named native property in the handler body."""
    result, graph, handlers, links, _ = persisted(tmp_path, sources(parameters=parameters))
    assert_notify(result, graph, handlers, links)
    reads = [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == "read"
             and qml_metadata(node).get("reference") == "count"]
    assert len(reads) == 1
    assert reads[0]["status"] == ("dynamic" if parameters else "resolved")
    if parameters:
        assert reads[0]["reason"] == "javascript_lexical_binding" and not reads[0]["resolved_target_id"]


def test_req_qml017_ac04_native_notify_query_and_affected_use_canonical_signal(tmp_path, monkeypatch, capsys):
    """Consumers retain the canonical endpoint and QML occurrence direction."""
    from graphify.affected import affected_nodes, load_graph
    from tests.qt_consumer_helpers import cli
    result, graph, sites, links, output = persisted(tmp_path, sources(), directed=True)
    assert_notify(result, graph, sites, links)
    source, target = links[0]["source"], links[0]["target"]
    assert "Main.qml" in cli(monkeypatch, capsys, output, "explain", source)
    assert "updated" in cli(monkeypatch, capsys, output, "query", source)
    assert source in {hit.node_id for hit in affected_nodes(load_graph(output), target, relations=["references"], depth=1)}


@pytest.mark.parametrize("damage", ["overload", "duplicate_property", "private_signal", "conditional"])
def test_req_qml008_ac03_ambiguous_private_or_conditional_native_notify_is_not_guessed(tmp_path, damage):
    """A plausible spelling does not replace exact accessor/public-signal authority."""
    files = sources()
    if damage == "overload":
        files["backend.h"] = files["backend.h"].replace('void updated();', 'void updated(); void updated(int count);')
    elif damage == "duplicate_property":
        files["backend.h"] = files["backend.h"].replace('Q_PROPERTY(int count READ count NOTIFY updated )',
            'Q_PROPERTY(int count READ count NOTIFY updated ) Q_PROPERTY(int count READ count NOTIFY updated)')
    elif damage == "private_signal":
        files["backend.h"] = files["backend.h"].replace('signals: void updated();', 'private: Q_SIGNAL void updated();')
    else:
        files["backend.h"] = files["backend.h"].replace(' Q_PROPERTY', '\r\n#if FEATURE\r\n Q_PROPERTY').replace(
            'count READ count NOTIFY updated )', 'count READ count NOTIFY updated )\r\n#endif\r\n')
    _, _, handlers, edges, _ = persisted(tmp_path, files)
    assert handlers and not edges and all(qml_metadata(node)["status"] != "resolved" for node in handlers.values())


def test_req_qml008_ac02_qml_inheritance_uses_native_notify_without_cpp_ancestry_guess(tmp_path):
    """The supported source QML base chain retains its exact native provider."""
    files = sources()
    files["Base.qml"] = 'import Public.Tools 1.0\nBackend {}\n'
    files["Main.qml"] = 'import QtQml\nBase { onCountChanged: count }\n'
    files["tools.pro"] += 'QML_FILES += Base.qml\n'
    result, graph, handlers, edges, _ = persisted(tmp_path, files)
    assert_notify(result, graph, handlers, edges)


def test_req_qml008_ac03_unproved_native_inherited_property_cannot_invent_notify(tmp_path):
    """C++ ancestor lookup stays outside the current native-member bounded profile."""
    files = sources()
    files["backend.h"] = files["backend.h"].replace('class Backend', 'class Base').replace('QML_ELEMENT', '')
    files["backend.h"] += 'class Backend : public Base { Q_OBJECT QML_ELEMENT };\r\n'
    _, _, handlers, edges, _ = persisted(tmp_path, files)
    assert handlers and not edges


@pytest.mark.parametrize("damage", ["drop_accessor", "wrong_owner", "wrong_span", "wrong_target"])
def test_req_qml008_ac03_notify_join_requires_accepted_accessor_identity(tmp_path, damage):
    """A direct index join must reject corrupted/missing provenance, without reads."""
    import copy
    from graphify.extractors.qt_cpp_facts import update_qt
    from graphify.qt_project_index import QtProjectIndex
    from graphify.qt_qml_bridge import build_qt_qml_bridge
    result = analysis(tmp_path, sources())
    borrowed = copy.deepcopy(result)
    nodes = copy.deepcopy(result["nodes"])
    accessor = next(node for node in nodes if qt_metadata(node).get("kind") == "property_accessor"
                    and qt_metadata(node).get("accessor_role") == "notify")
    if damage == "drop_accessor":
        nodes.remove(accessor)
    elif damage == "wrong_owner":
        update_qt(accessor, owner_id="unrelated")
    elif damage == "wrong_span":
        update_qt(accessor, span={**qt_metadata(accessor)["span"], "start_byte": 0})
    else:
        update_qt(accessor, generic_target_id="unrelated")
    bridge = build_qt_qml_bridge(nodes, result["edges"], root=tmp_path,
                                project_index=QtProjectIndex(nodes, result["edges"], root=tmp_path))
    provider = next(iter(bridge.provider_records))
    property_id = next(node["id"] for node in nodes if qt_metadata(node).get("kind") == "property")
    assert bridge.property_notify(property_id, provider).status != "resolved"
    assert result == borrowed


@pytest.mark.parametrize("style", ["legacy", "arrow", "anonymous", "connections"])
def test_req_qml007_ac03_notify_binds_only_block_injection_or_explicit_formals(tmp_path, style):
    """Signal parameter names do not shadow a function's outer property dependency."""
    files = sources(parameters="int count")
    if style == "legacy":
        handler = 'onCountChanged: { count; }'
    elif style == "arrow":
        handler = 'onCountChanged: (renamed) => { count; renamed; }'
    elif style == "anonymous":
        handler = 'onCountChanged: function(renamed) { count; renamed; }'
    else:
        handler = ('property Connections observer: Connections { target: backend; '
                   'function onCountChanged(renamed) { count; renamed; } }')
    files["Main.qml"] = 'import QtQml\nimport Public.Tools 1.0\nBackend { id: backend; ' + handler + ' }\n'
    result, graph, handlers, edges, _ = persisted(tmp_path, files)
    assert_notify(result, graph, handlers, edges)
    reads = {qml_metadata(node)["reference"]: qml_metadata(node) for node in result["nodes"]
             if qml_metadata(node).get("kind") == "read"}
    assert reads["count"]["status"] == ("dynamic" if style == "legacy" else "resolved")
    if style != "legacy":
        assert reads["renamed"]["status"] == "dynamic" and reads["renamed"]["reason"] == "javascript_lexical_binding"
    assert qml_metadata(next(iter(handlers.values())))["implicit_parameters"] is (style == "legacy")
