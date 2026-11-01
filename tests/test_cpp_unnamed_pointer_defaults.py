"""INC-QML-83: unnamed pointer defaults retain source type, optional arity and no binder."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from tests.qt_analysis_helpers import analysis, sites

SOURCE = '''struct Input {}; struct Service {};
struct Base {virtual Service *createRequest(int,const Input&,Service * = nullptr)=0;};
struct Derived:Base {Service *createRequest(int,const Input&,Service * = nullptr) override {return nullptr;}};
'''


def test_req_qml022_ac02_actual_unnamed_pointer_default_override_preserves_type_and_span(tmp_path):
    """The real valid declaration/override shape cannot become an erased/defaultless method."""
    path = tmp_path / "service.hpp"
    source = '\ufeff// café 雪\r\n' + SOURCE.replace('\n', '\r\n')
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    original = path.read_bytes()
    assert unit.source == original and len(unit.parsed_source) == len(original)
    changed = [position for position, (left, right) in enumerate(zip(original, unit.parsed_source)) if left != right]
    assert len(changed) == 2 and all(original[position] == 42 and unit.parsed_source[position] == 38 for position in changed)
    assert original.count(b"= nullptr") == unit.parsed_source.count(b"= nullptr") == 2
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    mapping = map_cpp(unit, direct["nodes"], direct["edges"], root=tmp_path)
    methods = [record for record in mapping.functions if record["name"] == "createRequest"]
    assert len(methods) == 2
    for record in methods:
        assert record["parameter_types"] == ["int", "const Input&", "Service*"]
        assert [item["name"] for item in record["parameters"]] == ["", "", ""]
        span = record["span"]
        assert b"Service * = nullptr" in original[span["start_byte"]:span["end_byte"]]
        assert original[:span["start_byte"]].count(b"\n") == span["start_row"]


def test_req_qml022_ac06_original_pointer_signature_is_distinct_from_reference_and_keeps_optional_arity(tmp_path):
    """Parse-view reference syntax cannot contaminate durable signature hashes or call arity."""
    path = tmp_path / "functions.cpp"
    path.write_text('struct Service{}; void pointer(Service*){} void reference(Service&){} '
                    'void optional(Service* = nullptr){} void run(){optional();}', encoding="utf-8")
    result = extract_cpp(path)
    assert not result.get("parse_errors")
    facts = {node["label"].removesuffix("()"): node for node in result["nodes"] if node.get("metadata", {}).get("cpp_function")}
    pointer, reference, optional = [facts[name]["metadata"]["cpp_function"] for name in ("pointer", "reference", "optional")]
    assert pointer["signature"] == optional["signature"] != reference["signature"]
    assert optional["min_args"] == 0 and optional["max_args"] == 1
    assert any(edge.get("relation") == "calls" and edge["target"] == facts["optional"]["id"] for edge in result["edges"])


def test_req_qml022_ac06_no_synthetic_parameter_can_shadow_global_name(tmp_path):
    """The adapter introduces no hidden binder to suppress a genuine source call."""
    path = tmp_path / "scope.cpp"
    path.write_text('class QObject; void sentinel(){} void optional(QObject* = nullptr){sentinel();}', encoding="utf-8")
    result = extract_cpp(path)
    assert not result.get("parse_errors")
    target = next(node["id"] for node in result["nodes"] if node["label"] == "sentinel()")
    assert any(edge.get("relation") == "calls" and edge["target"] == target for edge in result["edges"])
    mapping = map_cpp(read_cpp(path, tmp_path), result["nodes"], result["edges"], root=tmp_path)
    assert next(record for record in mapping.functions if record["name"] == "optional")["parameters"][0]["name"] == ""


def test_req_qml022_ac06_original_constructor_pointer_and_reference_overloads_do_not_merge(tmp_path):
    """Constructor source proof must inspect the original operator, not adapter AST kind."""
    result = analysis(tmp_path, {"owner.hpp": '#include <QObject>\nclass Owner {public:Owner(QObject* = nullptr);Owner(QObject&);};\n',
                                 "owner.cpp": '#include "owner.hpp"\nOwner::Owner(QObject*){} Owner::Owner(QObject&){}\n'})
    constructors = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    signatures = {base64.b64decode(node["metadata"]["cpp_constructor"]["signature_b64"])
                  for node in constructors if node["metadata"]["cpp_constructor"].get("signature_b64")}
    assert signatures == {b"ctor2\x00QObject*", b"ctor2\x00QObject&"}
    assert len({node["id"] for node in constructors}) == 2


def test_req_qml022_ac02_unnamed_qt_member_default_has_no_public_parameter_name(tmp_path):
    """Qt declaration metadata uses the original pointer, without exposing an adapter binder."""
    result = analysis(tmp_path, {"owner.hpp": '#include <QObject>\nclass Owner:public QObject{Q_OBJECT public:Q_INVOKABLE void accept(QObject* = nullptr){} };'})
    member = next(qt_metadata(node) for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "accept")
    assert member["parameter_types"] == ["QObject*"] and member["parameter_names"] == [""]
    assert member["roles"] == ["invokable"]


@pytest.mark.parametrize("spelling", ["Service ** = nullptr", "Service *const = nullptr", "Service (*)(int) = nullptr"])
def test_req_qml022_ac06_uncharacterized_abstract_pointer_shapes_do_not_invent_named_binders(tmp_path, spelling):
    """Unsupported compound forms keep an explicit syntax failure under this bounded profile."""
    path = tmp_path / "unsupported.hpp"
    path.write_text('struct Service{}; struct Owner{void use(' + spelling + ');};', encoding="utf-8")
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"
