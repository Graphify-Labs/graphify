"""Native QML providers require explicit source/module/member provenance."""
from __future__ import annotations

import copy
import json

from graphify.build import build_from_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_qml_bridge import build_qt_qml_bridge
from graphify.export import to_json
from tests.qt_cpp_test_helpers import HEADER, collect, facts


def native_corpus(tmp_path, calls=None, header=HEADER):
    calls = calls or 'void install(){ qmlRegisterType<Backend>("Demo",1,0,"Backend"); }'
    return collect(tmp_path, {"backend.hpp": header, "register.cpp": calls})


def test_literal_provider_members_and_exact_endpoint_proof(tmp_path):
    result = native_corpus(tmp_path)
    before = copy.deepcopy(result)
    index = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    provider = index.module_type("Demo", 1, 0, "Backend", importer="Main.qml")
    assert provider.status == "resolved" and index.is_provider(provider.target_id)
    assert index.module_import("Demo", 1, 0).status == "resolved"
    assert index.metadata(provider.target_id)["kind"] == "component"
    for name, kind in (("next", "function"), ("valueChanged", "signal"), ("value", "property"), ("setValue", "function")):
        member = index.member(provider.target_id, name)
        assert member.status == "resolved"
        target = next(node for node in result["nodes"] if node["id"] == member.target_id)
        if kind != "property":
            assert target.get("_callable") is True
            assert not qt_metadata(target)
        assert index.metadata(member.target_id)["kind"] == kind
        proof = index.endpoint_proof(member.target_id, member.evidence)
        assert proof["canonical_target_id"] == member.target_id
        assert proof["class_id"] == qt_metadata(facts(result, "class", "Backend")[0])["class_id"]
        assert proof["member_fact_id"] in member.evidence
        assert index.endpoint_proof(member.target_id, ()) == {}
    assert index.metadata(index.member(provider.target_id, "valueChanged").target_id)["parameter_names"] == ["value"]
    assert index.member(provider.target_id, "ordinary").status == "unavailable"
    assert index.member(provider.target_id, "hidden").status == "unavailable"
    assert result == before


def test_module_namespace_multiple_types_not_ambiguous_duplicate_export_is(tmp_path):
    calls = '''void install(){
qmlRegisterType<Backend>("Demo",1,0,"Backend");
qmlRegisterType<Backend>("Demo",1,0,"Another");
qmlRegisterType<Backend>("Demo",1,0,"Duplicate");
qmlRegisterType<Backend>("Demo",1,0,"Duplicate");
}'''
    result = native_corpus(tmp_path, calls)
    index = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    imported = index.module_import("Demo", 1, 0)
    assert imported.status == "resolved" and len(imported.evidence) == 4
    duplicate = index.module_type("Demo", 1, 0, "Duplicate", importer="Main.qml")
    assert duplicate.status == "ambiguous" and len(duplicate.candidates) == 2
    for name in ("Backend", "Another"):
        assert index.module_type("Demo", 1, 0, name).status == "resolved"
    assert index.endpoint_proof(imported.target_id, imported.evidence, kind="module")["kind"] == "module"


def test_overloads_ambiguous_before_generic_method_ids_collapse(tmp_path):
    header = HEADER.replace("Q_INVOKABLE int next(int amount);", "Q_INVOKABLE int next(int amount);\n Q_INVOKABLE int next(QString value);")
    result = native_corpus(tmp_path, header=header)
    declarations = [qt_metadata(node) for node in facts(result, "member", "next")]
    assert {md["signature"] for md in declarations} == {"next(int)", "next(QString)"}
    assert len({md["generic_target_id"] for md in declarations}) == 1
    index = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    provider = index.module_type("Demo", 1, 0, "Backend")
    answer = index.member(provider.target_id, "next")
    assert answer.status == "ambiguous" and answer.target_id is None
    assert answer.reason == "native_member_or_overload_ambiguous"


def test_versions_namespaces_singleton_anonymous_and_no_label_fallback(tmp_path):
    calls = '''void install(){
qmlRegisterType<Backend>("First",1,0,"Backend");
qmlRegisterSingletonType<Backend>("Second",2,3,"State",factory);
qmlRegisterAnonymousType<Backend>("Second",2);
}'''
    result = native_corpus(tmp_path, calls)
    index = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    assert index.module_type("Second", 2, 3, "Backend").status == "unavailable"
    assert index.module_type("First", 2, 0, "Backend").status == "unavailable"
    assert index.module_type("First", 1, 1, "Backend").reason == "native_module_version_unavailable"
    state = index.module_type("Second", 2, 3, "State")
    assert index.metadata(state.target_id)["singleton"]
    assert index.module_type("Second", 2, 0, "").status == "unavailable"
    assert index.module_type("Missing", None, None, "Backend").status == "unavailable"


def test_macro_provider_requires_real_source_membership_build_context(tmp_path):
    from graphify.extractors.qml_cmake import extract_cmake
    from graphify.qt_project_index import QtProjectIndex
    result = collect(tmp_path, {"backend.hpp": HEADER})
    no_context = build_qt_qml_bridge(result["nodes"], result["edges"], root=tmp_path)
    assert not no_context.provider_records
    build_file = tmp_path / "CMakeLists.txt"
    build_file.write_text('qt_add_qml_module(app URI Demo VERSION 1.2 SOURCES backend.hpp)\n')
    metadata = extract_cmake(build_file, root=tmp_path)
    nodes, edges = result["nodes"] + metadata["nodes"], result["edges"] + metadata["edges"]
    project = QtProjectIndex(nodes, edges, root=tmp_path)
    index = build_qt_qml_bridge(nodes, edges, root=tmp_path, project_index=project)
    provider = index.module_type("Demo", 1, 2, "Backend")
    assert provider.status == "resolved" and project.module_context("backend.hpp").target_id in provider.evidence
    assert index.module_type("Demo", 1, 0, "Backend").status == "resolved"
    assert index.module_type("Demo", 1, 1, "Backend").status == "resolved"
    assert index.module_type("Demo", 1, 3, "Backend").status == "unavailable"
    assert index.module_type("Other", 1, 2, "Backend").status == "unavailable"


def test_qmake_major_only_macro_registration_uses_documented_base_minor_zero(tmp_path):
    from graphify.extractors.qml_qmake import extract_qmake
    from graphify.qt_project_index import QtProjectIndex
    result = collect(tmp_path, {"backend.hpp": HEADER})
    project_file = tmp_path / "app.pro"
    project_file.write_text('CONFIG += qmltypes\nQML_IMPORT_NAME = Demo\nQML_IMPORT_MAJOR_VERSION = 1\nHEADERS += backend.hpp\n')
    metadata = extract_qmake(project_file, root=tmp_path)
    nodes, edges = result["nodes"] + metadata["nodes"], result["edges"] + metadata["edges"]
    index = build_qt_qml_bridge(nodes, edges, root=tmp_path,
                              project_index=QtProjectIndex(nodes, edges, root=tmp_path))
    assert index.module_type("Demo", 1, 0, "Backend").status == "resolved"
    assert index.module_type("Demo", 1, 1, "Backend").status == "unavailable"


def test_macro_introduction_and_removal_do_not_equal_module_maximum(tmp_path):
    from graphify.extractors.qml_cmake import extract_cmake
    from graphify.qt_project_index import QtProjectIndex
    header = HEADER.replace("QML_NAMED_ELEMENT(Backend)", "QML_NAMED_ELEMENT(Backend) QML_ADDED_IN_VERSION(1,1) QML_REMOVED_IN_VERSION(1,2)")
    result = collect(tmp_path, {"backend.hpp": header})
    project_file = tmp_path / "CMakeLists.txt"
    project_file.write_text('qt_add_qml_module(app URI Demo VERSION 1.2 SOURCES backend.hpp)\n')
    metadata = extract_cmake(project_file, root=tmp_path)
    nodes, edges = result["nodes"] + metadata["nodes"], result["edges"] + metadata["edges"]
    index = build_qt_qml_bridge(nodes, edges, root=tmp_path,
                              project_index=QtProjectIndex(nodes, edges, root=tmp_path))
    assert index.module_type("Demo", 1, 0, "Backend").status == "unavailable"
    assert index.module_type("Demo", 1, 1, "Backend").status == "resolved"
    assert index.module_type("Demo", 1, 2, "Backend").status == "unavailable"


def test_source_facts_build_and_json_reload_keep_members_spans_and_direction(tmp_path):
    result = native_corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "roundtrip.json"
    assert to_json(graph, {}, str(output))
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    expected = {node["id"] for node in result["nodes"] if qt_metadata(node)}
    assert expected.issubset(restored.nodes)
    for nid in expected:
        assert qt_metadata(dict(restored.nodes[nid]))["span"] == qt_metadata(next(node for node in result["nodes"] if node["id"] == nid))["span"]
    for edge in result["edges"]:
        if edge.get("context") != "qt_property_accessor":
            continue
        assert restored.has_edge(edge["source"], edge["target"])
        data = restored.edges[edge["source"], edge["target"]]
        assert data["confidence"] == "EXTRACTED" and data["context"] == "qt_property_accessor"
        assert (data["_src"], data["_tgt"]) == (edge["source"], edge["target"])
