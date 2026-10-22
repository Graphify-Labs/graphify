"""QML-009-AC02: generated tooling origins, members/flags and conflict retention."""
import copy
import json

import pytest

from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_cmake import parse_cmake
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_types import extract_qmltypes, parse_qmltypes
from graphify.qt_project_index import QtProjectIndex
from graphify.security import sanitize_metadata

SOURCE = '''import QtQuick.tooling 1.2
Module {
    dependencies: ["Public.Core 1.0"]
    Component {
        name: "NativeMain"; prototype: "QObject"; exports: ["Public.Tools/Main 1.0"]
        isSingleton: true; isCreatable: false; exportMetaObjectRevisions: [256]
        Property { name: "status"; type: "int"; isReadonly: true; notify: "statusChanged" }
        Signal { name: "statusChanged"; Parameter { name: "value"; type: "int" } }
        Method { name: "run"; type: "bool"; Parameter { name: "text"; type: "QString" } }
        Enum { name: "Mode"; isFlag: true; values: ["Idle", "Active"] }
    }
}'''


def records(result, kind):
    return [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("bom", ["", "\ufeff"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_qmltypes_members_flags_exports_original_byte_provenance(tmp_path, bom, newline):
    source = bom + SOURCE.replace("NativeMain", "NativeÉcran").replace("\n", newline)
    path = tmp_path / "plugins.qmltypes"
    path.write_bytes(source.encode())
    result = extract_qmltypes(path, root=tmp_path)
    assert not result.get("error")
    component = records(result, "qmltypes_component")[0]
    assert (component["raw_name"], component["singleton"], component["creatable"]) == (
        "NativeÉcran", True, False)
    assert records(result, "qmltypes_export")[0]["uri"] == "Public.Tools"
    assert [(md["member_kind"], md["raw_name"]) for md in records(result, "qmltypes_member")] == [
        ("property", "status"), ("signal", "statusChanged"), ("method", "run"), ("enum", "Mode")]
    assert [(md["raw_name"], md["raw_type"]) for md in records(result, "qmltypes_parameter")] == [
        ("value", "int"), ("text", "QString")]
    fields = records(result, "qmltypes_field")
    assert any(md["field_name"] == "isFlag" and md["value"] is True for md in fields)
    assert any(md["field_name"] == "values" and md["value"] == "Active" for md in fields)
    raw = source.encode()
    for node in result["nodes"]:
        md = qml_metadata(node)
        span = md["span"]
        for end in ("start", "end"):
            prefix = raw[:span[f"{end}_byte"]]
            assert span[f"{end}_row"] == prefix.count(b"\n")
            assert span[f"{end}_column"] == len(prefix) - prefix.rfind(b"\n") - 1
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"])
    payload = json.loads(json.dumps(result))
    for item in payload["nodes"] + payload["edges"]:
        item["metadata"] = sanitize_metadata(item["metadata"])
    assert records(payload, "qmltypes_field") == fields


def test_generated_and_source_declarations_keep_both_origins_and_conflict(tmp_path):
    path = tmp_path / "Main.qml"
    path.write_bytes(b"Item { property string status: 'live' }")
    qml, generated = extract_qml(path, root=tmp_path), parse_qmltypes(SOURCE)
    cmake = parse_cmake("qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml)")
    nodes = qml["nodes"] + generated["nodes"] + cmake["nodes"]
    before = copy.deepcopy(nodes)
    index = QtProjectIndex(nodes, [], root=tmp_path)
    assert nodes == before
    assert index.diagnostics[0]["code"] == "QML_TYPES_CONFLICT"
    resolved = index.resolve_component("Public.Tools", "Main")
    assert qml_metadata(index.nodes[resolved.target_id])["kind"] == "component"
    assert len(records(generated, "qmltypes_component")) == 1
    assert all(qml_metadata(n).get("generated") is True for n in generated["nodes"]
               if qml_metadata(n)["kind"] != "file")


def test_generated_tooling_description_does_not_prove_runtime_type_availability(tmp_path):
    result = parse_qmltypes(SOURCE)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.resolve_component("Public.Tools", "Main").target_id is None


@pytest.mark.parametrize("source", [
    "Module { Component { name: dynamicName } }",
    "Module { Component { name: 'SingleQuoteOutsideJsonSubset' } }",
    'Module { Component { name: "Thing"; unknownField: true } }',
    'Module { Component { name: "Thing"; exports: ["Invalid"] } }',
    'Module { Component { name: "Thing"; Property { name: "p"; type: factory() } } }',
    'Module { Component { name: "Thing"; isSingleton: "true" } }',
    'Module { Component { name: 12 } }',
    "Module { Component {", "Item {}", "Module {}\nModule {}",
])
def test_unsupported_or_computed_type_description_never_succeeds(source):
    result = parse_qmltypes(source)
    assert result["qml_failures"]
    assert result["nodes"] == []


def test_qmltypes_parser_absence_is_an_explicit_failure(monkeypatch):
    from graphify.extractors.qml_ast import QmlInputError
    def unavailable():
        raise QmlInputError("QML_PARSER_MISSING", "parser absent")
    monkeypatch.setattr("graphify.extractors.qml_types.load_parser", unavailable)
    result = parse_qmltypes(SOURCE)
    assert result["qml_failures"][0]["code"] == "QML_PARSER_MISSING"


def test_qmltypes_cpp_member_conflict_preserves_authoritative_source(tmp_path):
    from graphify.extractors.qt_cpp_facts import encode_qt
    generated = parse_qmltypes(SOURCE)
    source = {"id": "native-property", "source_file": "backend.h", "type": "property",
              "metadata": {"qt": encode_qt({"kind": "property", "class_name": "NativeMain",
                                            "raw_name": "status", "raw_type": "QString",
                                            "notify": "otherSignal"})}}
    nodes = generated["nodes"] + [source]
    before = copy.deepcopy(nodes)
    index = QtProjectIndex(nodes, generated["edges"], root=tmp_path)
    assert any(d["reason"] == "generated_member_disagrees_with_source" and
               d["source_id"] == source["id"] for d in index.diagnostics)
    assert index.nodes[source["id"]] == before[-1]
    assert nodes == before


def test_more_than_fifty_generated_enum_values_survive_transport():
    values = ", ".join(json.dumps(f"Value{i}") for i in range(60))
    result = parse_qmltypes('Module { Component { name: "Thing"; Enum { name: "Flags"; '
                            'values: [' + values + '] } } }')
    assert not result.get("error")
    payload = json.loads(json.dumps(result))
    for node in payload["nodes"]:
        node["metadata"] = sanitize_metadata(node["metadata"])
    assert len([md for md in records(payload, "qmltypes_field") if md["field_name"] == "values"]) == 60


def test_qt6_enum_literal_object_keeps_signed_values_without_evaluation():
    source = 'Module { Component { name: "Thing"; Enum { name: "Mode"; '
    source += 'values: { "Ready": 1, "Missing": -1 } } } }'
    result = parse_qmltypes(source)
    assert not result.get("error")
    assert [(md["enum_key"], md["value"]) for md in records(result, "qmltypes_field")
            if md["field_name"] == "values"] == [("Ready", 1), ("Missing", -1)]
    assert parse_qmltypes(source.replace('"Missing": -1', '"Ready": 2'))["qml_failures"]
