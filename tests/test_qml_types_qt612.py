"""REQ-QML-022-AC04/06: tagged generator fields, typing and authority boundaries."""
import copy
import json

import pytest

from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_types import extract_qmltypes, parse_qmltypes
from graphify.qt_project_index import QtProjectIndex
from graphify.security import sanitize_metadata
from tests.qml_types_qt612_helpers import fields, module, records


@pytest.mark.parametrize("bom,newline", [("", "\n"), ("\ufeff", "\r\n")])
def test_req_qml022_ac04_generated_fields_preserve_original_owner_and_bytes(tmp_path, bom, newline):
    """Every added field survives direct/facade/JSON transport without trusting line hints."""
    raw = (bom + module().replace("Backend", "Backénd")).replace("\n", newline).encode()
    path = tmp_path / "plugins.qmltypes"
    path.write_bytes(raw)
    direct = extract_qmltypes(path, root=tmp_path)
    assert not direct.get("error")
    assert len(records(direct, "qmltypes_member")) == 5
    assert len(records(direct, "qmltypes_parameter")) == 1
    expected = {"lineNumber", "lineNumberInResolvedFile", "resolvedFile", "parentProperty",
                "isSelfExtension", "isTypeConstant", "isPropertyConstant", "isVirtual", "isOverride"}
    assert expected <= {f["field_name"] for f in records(direct, "qmltypes_field")}
    component = records(direct, "qmltypes_component")[0]
    assert component["declared_file"] == "backend.hpp"
    assert component["span"]["start_row"] != 11
    for node in direct["nodes"]:
        span = qml_metadata(node)["span"]
        for end in ("start", "end"):
            prefix = raw[:span[f"{end}_byte"]]
            assert span[f"{end}_row"] == prefix.count(b"\n")
            assert span[f"{end}_column"] == len(prefix) - prefix.rfind(b"\n") - 1
    cold = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not cold.get("qml_failures") and not warm.get("qml_failures")
    assert fields(cold) == fields(warm) == fields(direct)
    payload = json.loads(json.dumps(cold))
    for item in payload["nodes"] + payload["edges"]:
        item["metadata"] = sanitize_metadata(item.get("metadata", {}))
    assert fields(payload) == fields(direct)


def test_req_qml022_ac04_opaque_types_have_no_creation_or_native_authority(tmp_path, monkeypatch):
    """An opaque generator description retains members but never reads its source hints."""
    source = module('name: "Foreign"; isTypeOpaque: true; file: "../outside.hpp"; '
                    'lineNumber: 0; accessSemantics: "reference"; '
                    'Property { name: "count"; type: "int"; lineNumber: 8 }')
    path = tmp_path / "plugins.qmltypes"
    path.write_text(source, encoding="utf-8")
    original_open = type(path).open

    def admitted_only(open_path, *args, **kwargs):
        assert open_path == path, "tooling source hints must not authorize a read"
        return original_open(open_path, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", admitted_only)
    result = extract_qmltypes(path, root=tmp_path)
    assert not result.get("error")
    component = records(result, "qmltypes_component")[0]
    assert component["opaque"] is True and component["creatable"] is False
    assert component["evidence_role"] == "tooling_description"
    assert not records(result, "qmltypes_export")
    assert all(n["source_file"] == "plugins.qmltypes" for n in result["nodes"])
    before = copy.deepcopy(result)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.resolve_component("Example", "Foreign").target_id is None
    assert result == before


@pytest.mark.parametrize("extra", [
    'exports: ["Example/Foreign 1.0"]', 'isCreatable: true', 'isSingleton: true',
    'isComposite: true', 'extension: "Other"', 'isSelfExtension: true',
    'isJavaScriptBuiltin: true',
])
def test_req_qml022_ac04_opaque_contradictions_reject_the_whole_description(extra):
    """Forged creatability/registration/extension claims do not override opaque evidence."""
    result = parse_qmltypes(module('name: "Foreign"; isTypeOpaque: true; ' + extra))
    assert result["nodes"] == []
    assert result["qml_failures"][0]["reason"] == "opaque_type_authority_conflict"


@pytest.mark.parametrize("component", [
    'name: "B"; lineNumber: true', 'name: "B"; lineNumber: -1',
    'name: "B"; lineNumber: 2147483648', 'name: "B"; lineNumberInResolvedFile: 1.5',
    'name: "B"; resolvedFile: ["outside.hpp"]', 'name: "B"; parentProperty: false',
    'name: "B"; isTypeOpaque: 1', 'name: "B"; isSelfExtension: "true"',
    'name: "B"; interfaces: "Interface"', 'name: "B"; exportMetaObjectRevisions: [true]',
    'name: "B"; Property { name: "p"; isPropertyConstant: "yes" }',
    'name: "B"; Method { name: "f"; lineNumber: -2 }',
    'name: "B"; Signal { name: "s"; Parameter { type: "int"; isTypeConstant: 1 } }',
    'name: "B"; Property { name: "p"; isConstructor: true }',
    'name: "B"; Signal { name: "s"; Parameter { type: "int"; lineNumber: 1 } }',
    'name: "B"; Property { name: "p"; isPropertyConstant: true; write: "set" }',
    'name: "B"; Property { name: "p"; isPropertyConstant: true; isReadonly: false }',
    'name: "B"; Enum { name: "E"; values: { "A": true } }',
    'name: "B"; Property { name: "p"; revision: 65536 }',
    'name: "B"; exportMetaObjectRevisions: [-1]',
    'name: "B"; accessSemantics: "unknown"',
    'name: "B"; parentProperty: "bad\\u0000hint"',
    'name: "B"; resolvedFile: "bad\\ud800hint"',
    'name: "B"; unknownField: true', 'name: "B"; lineNumber: 1; lineNumber: 2',
])
def test_req_qml022_ac04_typed_fields_reject_corruption_without_partial_facts(component):
    """Invalid types, bounded integers, duplicates and unknown fields fail before output."""
    result = parse_qmltypes(module(component))
    assert result["nodes"] == [] and result["qml_failures"]
    assert result["qml_failures"][0]["code"] == "QML_TYPES_UNSUPPORTED"


@pytest.mark.parametrize("field,value", [
    ("lineNumber", "2147483647"), ("lineNumberInResolvedFile", "0"),
    ("resolvedFile", json.dumps("é" * 192)), ("parentProperty", json.dumps("owner")),
])
def test_req_qml022_ac04_field_boundaries_are_lossless(field, value):
    """Largest admitted line/string facts survive the existing lossless transport."""
    result = parse_qmltypes(module('name: "B"; ' + field + ': ' + value))
    assert not result.get("error")
    assert any(m["field_name"] == field and m["value"] == json.loads(value)
               for m in records(result, "qmltypes_field"))


def test_req_qml022_ac04_oversized_field_reports_existing_limit_code():
    """A field exceeding the established string transport bound rejects explicitly."""
    result = parse_qmltypes(module('name: "B"; resolvedFile: ' + json.dumps("é" * 193)))
    assert result["nodes"] == []
    assert result["qml_failures"][0]["code"] == "QML_PROJECT_LIMIT"


def test_req_qml022_ac04_module_dependencies_are_typed_and_bounded():
    """The top-level generator list shares typed limits rather than a loose literal escape."""
    for value in ('"Example 1.0"', '[true]', '[["nested"]]'):
        result = parse_qmltypes('Module { dependencies: ' + value + ' }')
        assert result["nodes"] == [] and result["qml_failures"]
    result = parse_qmltypes('Module { dependencies: [' + ','.join('"D"' for _ in range(10_001)) + '] }')
    assert result["qml_failures"][0]["code"] == "QML_PROJECT_LIMIT"


def test_req_qml022_ac04_enum_values_keep_full_signed_unsigned_integer_boundaries():
    """Tooling enum maps retain exact integers and reject overflow without evaluation."""
    enum = 'name: "B"; Enum { name: "E"; values: { "Low": -9223372036854775808, "High": 18446744073709551615 } }'
    result = parse_qmltypes(module(enum))
    assert not result.get("error")
    assert {m["value"] for m in records(result, "qmltypes_field") if m["field_name"] == "values"} == {
        -(2**63), 2**64 - 1}
    assert parse_qmltypes(module(enum.replace("18446744073709551615", "18446744073709551616")))["qml_failures"]
