"""REQ-QML-008-AC02/016/017 retain canonical implementation ownership."""
import json
import re
import copy

import pytest

from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_html, to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from tests.qt_analysis_helpers import analysis, sites


HEADER = '''namespace Shared {
class Backend : public QObject {
 Q_OBJECT
signals:
 void changed();
public:
 void run();
};
}
'''
CPP = '''#include "backend.hpp"
using namespace Shared;
void Backend::run() {
 emit changed();
}
'''
FORWARD = 'namespace Shared { class Backend; }\nQQmlApplicationEngine *admission_only;\n'


def canonical_run(result):
    """The generic facade already records the header/implementation identity."""
    selected = [node for node in result["nodes"] if node.get("_callable")
                and node.get("source_file") == "backend.hpp" and node.get("label") == ".run()"]
    assert len(selected) == 1
    return selected[0]


def payload(path, key):
    match = re.search(r"const " + key + r" = (\[.*?\]);", path.read_text(encoding="utf-8"), re.S)
    assert match
    return json.loads(match[1])


@pytest.mark.parametrize("forward", [False, True])
def test_req_qml008_ac02_definition_provenance_keeps_emission_owned_through_aggregate(tmp_path, forward):
    """Using-namespace syntax must reuse the facade's exact accepted definition owner."""
    sources = {"backend.hpp": HEADER, "backend.cpp": CPP}
    if forward:
        sources["forward.hpp"] = FORWARD
    result = analysis(tmp_path, sources)
    method = canonical_run(result)
    assert method["definition_file"] == "backend.cpp" and method["definition_location"] == "L3"
    member = next(node for node in sites(result, "member") if node["source_file"] == "backend.cpp")
    emission = sites(result, "emission")[0]
    signal = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "changed")
    assert qt_metadata(member)["generic_target_id"] == method["id"]
    assert qt_metadata(member)["class_name"] == "Shared::Backend"
    assert qt_metadata(member)["class_id"]
    assert qt_metadata(emission)["owner_id"] == method["id"]
    assert qt_metadata(emission)["status"] == "resolved"
    assert qt_metadata(emission)["target_id"] == signal["id"]
    source = CPP.encode()
    span = qt_metadata(emission)["span"]
    assert source[span["start_byte"]:span["end_byte"]] == b"changed()"
    graph = build_from_json(result, root=tmp_path)
    assert graph.has_edge(method["id"], emission["id"])
    assert graph.has_edge(emission["id"], signal["id"])
    assert not any(edge.get("relation") == "calls" for _, _, edge in graph.edges(emission["id"], data=True))
    groups = cluster(graph)
    path = tmp_path / "graph.json"
    assert to_json(graph, groups, str(path))
    reloaded = build_from_json(json.loads(path.read_text(encoding="utf-8")), root=tmp_path)
    assert reloaded.has_edge(method["id"], emission["id"]) and reloaded.has_edge(emission["id"], signal["id"])
    html = tmp_path / "graph.html"
    assert to_html(reloaded, groups, str(html), node_limit=2)
    nodes, edges = payload(html, "RAW_NODES"), payload(html, "RAW_EDGES")
    assert not [node for node in nodes if node["label"] in {"Qt member: run", "Qt emission: changed"}
                and not any(node["id"] in (edge["from"], edge["to"]) for edge in edges)]


def test_req_qml016_ac01_forward_declaration_does_not_compete_with_complete_definition(tmp_path):
    """A fully qualified control still rejects a forward declaration as a second body."""
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": CPP.replace("Backend::run", "Shared::Backend::run"),
                                 "forward.hpp": FORWARD})
    method = canonical_run(result)
    emission = sites(result, "emission")[0]
    assert qt_metadata(emission)["owner_id"] == method["id"]
    assert qt_metadata(emission)["status"] == "resolved"
    classes = sites(result, "class")
    assert len(classes) == 2
    assert {node["source_file"]: qt_metadata(node)["is_definition"] for node in classes} == {
        "backend.hpp": True, "forward.hpp": False}


def test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access(tmp_path):
    """Loader and property sites keep the same proven canonical implementation owner."""
    cpp = CPP.replace(" emit changed();", ''' QQmlApplicationEngine engine;
 engine.load("qrc:/App/Main.qml");
 QObject *root = engine.rootObjects().first();
 root->property("value");
 emit changed();''')
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": cpp,
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "app.qrc": '<RCC><qresource prefix="/App"><file>Main.qml</file></qresource></RCC>'})
    method = canonical_run(result)
    owned = sites(result, "qml_load") + sites(result, "qml_root") + sites(result, "qml_access")
    assert len(owned) == 3
    assert all(qt_metadata(node)["owner_id"] == method["id"] for node in owned)
    assert all(qt_metadata(node)["status"] == "resolved" for node in owned)
    graph = build_from_json(result, root=tmp_path)
    assert all(graph.has_edge(method["id"], node["id"]) for node in owned)
    # The owning method must survive the same publication/reload boundary as
    # native event ownership, including reverse QML property access sites.
    path = tmp_path / "graph.json"
    assert to_json(graph, cluster(graph), str(path))
    reloaded = build_from_json(json.loads(path.read_text(encoding="utf-8")), root=tmp_path)
    assert all(reloaded.has_edge(method["id"], node["id"]) for node in owned)
    assert all(qt_metadata(reloaded.nodes[node["id"]])["owner_id"] == method["id"] for node in owned)


def mapped_run(root, nodes, edges):
    """Reparse original source against the accepted boundary, including corrupt-proof controls."""
    mapping = map_cpp(read_cpp(root / "backend.cpp", root), nodes, edges, root=root)
    mapping.bind_classes([])
    return next(record for record in mapping.functions if record["name"] == "run")


@pytest.mark.parametrize("spelling", ["absolute", "dot", "windows_separator"])
def test_req_qml008_ac02_definition_paths_are_normalized_without_changing_source_spans(tmp_path, spelling):
    """Equivalent accepted path representations still select the exact definition."""
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": CPP})
    nodes = copy.deepcopy(result["nodes"])
    method = canonical_run({"nodes": nodes})
    method["definition_file"] = str(tmp_path / "backend.cpp") if spelling == "absolute" else (
        "./backend.cpp" if spelling == "dot" else ".\\backend.cpp")
    before = copy.deepcopy((nodes, result["edges"]))
    record = mapped_run(tmp_path, nodes, result["edges"])
    assert record["node_id"] == method["id"] and record["class_name"] == "Shared::Backend"
    assert CPP.encode()[record["span"]["start_byte"]:record["span"]["end_byte"]] == b"void Backend::run() {\n emit changed();\n}"
    assert (nodes, result["edges"]) == before


@pytest.mark.parametrize("corruption", ["wrong_file", "wrong_line", "not_callable", "inferred_owner"])
def test_req_qml008_ac02_definition_recovery_rejects_incomplete_or_foreign_proof(tmp_path, corruption):
    """No name-only replacement can compensate for rejected definition/ownership evidence."""
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": CPP})
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    method = canonical_run({"nodes": nodes})
    if corruption == "wrong_file":
        method["definition_file"] = "other.cpp"
    elif corruption == "wrong_line":
        method["definition_location"] = "L2"
    elif corruption == "not_callable":
        method["_callable"] = False
    else:
        for edge in edges:
            if edge["target"] == method["id"] and edge["relation"] == "method":
                edge["confidence"] = "INFERRED"
    before = copy.deepcopy((nodes, edges))
    record = mapped_run(tmp_path, nodes, edges)
    assert record["class_id"] == "" and record["class_name"] == "Backend"
    assert (nodes, edges) == before


def test_req_qml008_ac02_conflicting_callable_identity_is_not_arbitrarily_selected(tmp_path):
    """Two accepted callables claiming the same definition remain explicitly ambiguous."""
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": CPP})
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    method = canonical_run({"nodes": nodes})
    conflicting = {**method, "id": "conflicting_canonical_callable"}
    nodes.append(conflicting)
    edges.extend({**edge, "target": conflicting["id"]} for edge in list(edges)
                 if edge["target"] == method["id"] and edge["relation"] == "method")
    record = mapped_run(tmp_path, nodes, edges)
    assert record["node_id"] == "" and record["status"] == "ambiguous"
    assert set(record["candidates"]) == {method["id"], conflicting["id"]}


def test_req_qml008_ac02_multiple_real_class_bodies_are_not_forward_declarations(tmp_path):
    """Genuine competing complete definitions cannot acquire an arbitrary native target."""
    result = analysis(tmp_path, {"backend.hpp": HEADER, "duplicate.hpp": HEADER, "backend.cpp": CPP})
    classes = sites(result, "class")
    assert len(classes) == 2 and all(qt_metadata(node)["is_definition"] is True for node in classes)
    implementation = next(node for node in sites(result, "member") if node["source_file"] == "backend.cpp")
    assert qt_metadata(implementation)["class_id"] == ""
    emission = sites(result, "emission")[0]
    assert qt_metadata(emission)["status"] != "resolved" and qt_metadata(emission)["target_id"] == ""


@pytest.mark.parametrize("body", [False, None])
def test_req_qml008_ac02_missing_body_proof_cannot_become_a_native_provider(tmp_path, body):
    """Literal registration tolerates a forward declaration, but not absent definition proof."""
    from graphify.extractors.qt_cpp_facts import update_qt
    from graphify.qt_event_index import QtEventIndex
    from graphify.qt_qml_bridge import build_qt_qml_bridge

    registration = 'void install(){qmlRegisterType<Shared::Backend>("Demo",1,0,"Backend");}'
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": CPP,
        "forward.hpp": FORWARD, "register.cpp": registration})
    providers = sites(result, "registration")
    assert len(providers) == 1 and qt_metadata(providers[0])["status"] == "resolved"
    baseline = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    assert baseline.module_type("Demo", 1, 0, "Backend").status == "resolved"
    nodes = copy.deepcopy(result["nodes"])
    for node in nodes:
        if qt_metadata(node).get("kind") == "class" and node["source_file"] == "backend.hpp":
            update_qt(node, is_definition=body)
    assert QtEventIndex(nodes).class_name("Shared::Backend") == ""
    unsupported = build_qt_qml_bridge(nodes, result["edges"], root=tmp_path)
    assert unsupported.module_type("Demo", 1, 0, "Backend").status == "unavailable"
    assert unsupported.unresolved[providers[0]["id"]]["reason"] == "native_class_definition_unavailable"


def test_req_qml008_ac02_external_and_function_local_classes_keep_unknown_ownership(tmp_path):
    """Proven source containment does not invent an unavailable native class owner."""
    source = '#include "external.hpp"\nvoid External::run(){QObject *object;}\n' + (
        'void utility(){struct Local {void work(){}}; QObject *object;}')
    result = analysis(tmp_path, {"unresolved.cpp": source})
    external = next(node for node in sites(result, "member") if qt_metadata(node)["class_name"] == "External")
    local = next(node for node in sites(result, "class") if qt_metadata(node)["raw_name"] == "Local")
    assert qt_metadata(external)["class_id"] == "" and qt_metadata(external)["generic_target_id"]
    assert qt_metadata(local)["class_id"] == "" and qt_metadata(local)["is_definition"] is True
    function = next(node for node in result["nodes"] if node.get("label") == "utility()")
    for node, owner in ((external, qt_metadata(external)["generic_target_id"]), (local, function["id"])):
        assert qt_metadata(node)["owner_id"] == owner
        assert any(edge["source"] == owner and edge["target"] == node["id"]
                   and edge["relation"] == "contains" and edge["confidence"] == "EXTRACTED"
                   and edge["context"] == "qt_source_site" for edge in result["edges"])
    assert qt_metadata(local)["generic_target_id"] == "" and qt_metadata(local)["status"] == "unavailable"


def test_req_qml008_ac02_unrelated_plain_cpp_keeps_generic_identities(tmp_path):
    """The Qt overlay correction does not change admission or ordinary C++ calls."""
    source = "int helper(){return 1;}\nint use(){return helper();}"
    result = analysis(tmp_path, {"plain.cpp": source})
    assert not any(qt_metadata(node) for node in result["nodes"])
    functions = {node["label"]: node["id"] for node in result["nodes"] if node.get("_callable")}
    assert set(functions) == {"helper()", "use()"}
    assert any(edge["source"] == functions["use()"] and edge["target"] == functions["helper()"]
               and edge["relation"] == "calls" for edge in result["edges"])


def test_req_qml008_ac02_definition_and_emission_spans_use_original_bom_crlf_unicode_bytes(tmp_path):
    """Recovery changes ownership only; original encoded source still owns every span."""
    cpp = ("\ufeff// caf\u00e9 \u96ea\n" + CPP).replace("\n", "\r\n")
    result = analysis(tmp_path, {"backend.hpp": HEADER, "backend.cpp": cpp, "forward.hpp": FORWARD})
    method = canonical_run(result)
    assert method["definition_file"] == "backend.cpp" and method["definition_location"] == "L4"
    record = mapped_run(tmp_path, result["nodes"], result["edges"])
    assert record["node_id"] == method["id"] and record["class_name"] == "Shared::Backend"
    original = (tmp_path / "backend.cpp").read_bytes()
    assert original == cpp.encode("utf-8")
    definition = record["span"]
    assert original[definition["start_byte"]:definition["end_byte"]] == (
        b"void Backend::run() {\r\n emit changed();\r\n}")
    emission = sites(result, "emission")[0]
    span = qt_metadata(emission)["span"]
    assert original[span["start_byte"]:span["end_byte"]] == b"changed()"
    assert qt_metadata(emission)["owner_id"] == method["id"]
    assert qt_metadata(emission)["status"] == "resolved"
