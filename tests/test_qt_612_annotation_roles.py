"""REQ-QML-022-AC03: annotations need source roles, not matching spellings."""
from __future__ import annotations

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, normalize_qt_cpp, read_cpp
from tests.qt_cpp_test_helpers import collect, facts, write


@pytest.mark.parametrize("name", ["Q_OBJECT", "Q_GADGET", "Q_PROPERTY", "Q_INVOKABLE",
                                  "Q_SIGNAL", "Q_SLOT", "QML_ELEMENT", "Q_NAMESPACE"])
def test_annotation_spelling_can_name_an_ordinary_member(tmp_path, name):
    """Valid data and callable declarators survive direct parsing and Qt admission."""
    source = f"struct Cell {{ int {name}; }}; int {name}() {{ return 1; }}"
    path = write(tmp_path, "names.cpp", source)
    unit = read_cpp(path, tmp_path)
    assert unit.parsed_source == source.encode() and unit.macros == []
    assert normalize_qt_cpp(source.encode()) is None
    result = extract_cpp(path)
    assert not result.get("parse_errors")
    assert any(node["label"].removesuffix("()") == name for node in result["nodes"])


def test_ordinary_identifier_uses_survive_alongside_real_annotations(tmp_path):
    """Mixed valid annotations do not erase names in another clean declaration."""
    source = ("struct Cell { int Q_OBJECT; int Q_PROPERTY; int Q_SLOT(){ return Q_OBJECT; } };\n"
              "class Backend : public QObject { Q_OBJECT public: Q_INVOKABLE int go(); };\n"
              "int use(Cell& c){ return c.Q_SLOT() + c.Q_PROPERTY; }")
    unit = read_cpp(write(tmp_path, "mixed.hpp", source), tmp_path)
    assert [item["name"] for item in unit.macros] == ["Q_OBJECT", "Q_INVOKABLE"]
    assert b"int Q_OBJECT;" in unit.parsed_source and b"c.Q_SLOT()" in unit.parsed_source
    result = collect(tmp_path, {"mixed.hpp": source})
    assert not any(item.get("qml_failures") for item in result["per_file"])
    assert qt_metadata(facts(result, "member", "go")[0])["roles"] == ["invokable"]


@pytest.mark.parametrize("annotation", ["Q_OBJECT", "Q_GADGET", "Q_GADGET_EXPORT(PUBLIC_API)"])
@pytest.mark.parametrize("kind", ["class", "struct"])
@pytest.mark.parametrize("later,expected", [("", "private"), ("public:", "public"),
                                             ("protected:", "protected"), ("private:", "private")])
def test_actual_annotation_resets_access_in_source_order(tmp_path, annotation, kind, later, expected):
    """The macro resets prior public/signal access; a later explicit label wins."""
    source = (f"{kind} Backend {{ public: void before(); {annotation} {later} "
              "Q_INVOKABLE int after(); };")
    result = collect(tmp_path, {"backend.hpp": source})
    before = qt_metadata(facts(result, "member", "before")[0])
    after = qt_metadata(facts(result, "member", "after")[0])
    assert before["access"] == "public" and after["access"] == expected
    assert after["roles"] == ["invokable"]
    assert source.encode()[after["span"]["start_byte"]:after["span"]["end_byte"]] == b"int after();"


def test_access_reset_is_owned_by_innermost_class(tmp_path):
    """A nested class macro cannot change the surrounding class's public state."""
    source = ("class Outer { public: class Inner { Q_OBJECT Q_INVOKABLE int hidden(); }; "
              "Q_INVOKABLE int visible(); int Q_GADGET; Q_INVOKABLE int stillVisible(); };")
    result = collect(tmp_path, {"nested.hpp": source})
    values = {qt_metadata(n)["raw_name"]: qt_metadata(n)["access"] for n in facts(result, "member")}
    assert values["hidden"] == "private" and values["visible"] == values["stillVisible"] == "public"


@pytest.mark.parametrize("annotation", ["Q_GADGET_EXPORT(PUBLIC_API)", "Q_GADGET"])
def test_gadget_annotation_has_no_qobject_or_registration_authority(tmp_path, annotation):
    """Export syntax admits source facts without granting a QObject/provider role."""
    source = f"class Point {{ {annotation} public: int x; enum Scale {{ Unit, Double }}; Q_ENUM(Scale) }};"
    result = collect(tmp_path, {"point.hpp": source})
    md = qt_metadata(facts(result, "class", "Point")[0])
    assert md["is_gadget"] and not md["is_qobject"]
    assert not facts(result, "registration")
    assert any(n["label"] == "Scale" for n in result["nodes"])


@pytest.mark.parametrize("annotation", ["Q_NAMESPACE", "Q_NAMESPACE_EXPORT(PUBLIC_API)"])
def test_namespace_annotations_preserve_generic_enums(tmp_path, annotation):
    """Namespace annotations are source evidence, never QObject or engine identity."""
    source = f"namespace Values {{ {annotation} enum Scale {{ Unit, Double }}; Q_ENUM_NS(Scale) }}"
    result = collect(tmp_path, {"values.hpp": source})
    assert not any(item.get("qml_failures") for item in result["per_file"])
    assert any(n["label"] == "Scale" for n in result["nodes"])
    namespace = qt_metadata(facts(result, "namespace", "Values")[0])
    assert namespace["source_q_namespace"] and namespace["status"] == "source_only"
    assert not facts(result, "class") and not facts(result, "registration")


@pytest.mark.parametrize("annotation", ["Q_DECL_NONALLOCATING_FUNCTION", "Q_DECL_NONBLOCKING_FUNCTION"])
def test_compiler_function_annotations_do_not_make_methods_invokable(tmp_path, annotation):
    """Qt6.12 compiler hints retain normal callable identity and no Qt member role."""
    source = f"class Value {{ public: {annotation} int compute() const; }};"
    result = collect(tmp_path, {"value.hpp": source})
    member = qt_metadata(facts(result, "member", "compute")[0])
    assert member["roles"] == [] and member["access"] == "public"


@pytest.mark.parametrize("annotation", ["Q_GADGET_EXPORT()", "Q_NAMESPACE_EXPORT(A,B)",
                                        "Q_GADGET_EXPORT(A", "Q_DECL_NONBLOCKING_FUNCTION(x)"])
def test_malformed_new_annotations_remain_explicit_failure(tmp_path, annotation):
    """Unsupported annotation forms must not be laundered into accepted source."""
    source = f"class Bad {{ {annotation} public: int x; }};"
    with pytest.raises(QtCppError) as failure:
        read_cpp(write(tmp_path, "bad.hpp", source), tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"


def test_annotation_recovery_preserves_bom_unicode_crlf_bytes(tmp_path):
    """Original-byte locations survive BOM/UTF-8 text and newline-preserving blanks."""
    source = "\ufeff// café\r\nclass Value { Q_GADGET_EXPORT(API) public: int x; };\r\n"
    unit = read_cpp(write(tmp_path, "value.hpp", source), tmp_path)
    macro = unit.macros[0]
    span = macro["span"]
    assert unit.source[span["start_byte"]:span["end_byte"]] == b"Q_GADGET_EXPORT(API)"
    assert len(unit.source) == len(unit.parsed_source) and unit.parsed_source.count(b"\r\n") == 2


@pytest.mark.parametrize("source", ["struct Q_OBJECT { Q_OBJECT(); };",
                                    "struct Q_OBJECT { ~Q_OBJECT(); };",
                                    "struct Q_OBJECT {}; Q_OBJECT value;",
                                    "using Q_SLOT=int; Q_SLOT value;",
                                    "namespace N { struct Q_INVOKABLE {}; } N::Q_INVOKABLE value;"])
def test_macro_named_types_constructors_and_destructors_are_not_annotations(tmp_path, source):
    """Clean declaration identity protects type uses and typeless special members."""
    unit = read_cpp(write(tmp_path, "ordinary.cpp", source), tmp_path)
    assert unit.parsed_source == source.encode() and unit.macros == []
    result = collect(tmp_path, {"ordinary.cpp": source})
    assert all(not qt_metadata(n).get("source_q_object") for n in facts(result, "class"))


@pytest.mark.parametrize("marker", ["Q_OBJECT", "Q_GADGET", "QML_ELEMENT", "Q_NAMESPACE"])
def test_executable_body_cannot_supply_class_or_namespace_annotation(tmp_path, marker):
    """An invalid marker in a method body cannot launder QObject/provider authority."""
    source = f"class Backend {{ public: void f(){{ {marker} }} Q_INVOKABLE int go(); }};"
    with pytest.raises(QtCppError) as failure:
        read_cpp(write(tmp_path, "bad.hpp", source), tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"
    span = failure.value.span
    assert isinstance(span, dict)
    assert source.encode()[span["start_byte"]:span["end_byte"]] == marker.encode()


@pytest.mark.parametrize("directive", ["#define Q_OBJECT public:", "#undef Q_OBJECT",
                                        "#define Q_INVOKABLE", "#undef Q_INVOKABLE"])
def test_local_preprocessor_override_cannot_supply_sdk_annotation_authority(tmp_path, directive):
    """Local override uncertainty rejects rather than applying Qt access/provider rules."""
    source = directive + "\nclass Backend { Q_OBJECT public: Q_INVOKABLE int value(); };"
    with pytest.raises(QtCppError) as failure:
        read_cpp(write(tmp_path, "override.hpp", source), tmp_path)
    assert failure.value.code == "QT_CPP_SYNTAX"


def test_namespace_marker_retains_nested_qualified_source_owner(tmp_path):
    """Same-named namespace blocks retain distinct lexical source qualification."""
    source = ("namespace Left { namespace Shared { Q_NAMESPACE enum Kind { A }; } } "
              "namespace Right::Shared { Q_NAMESPACE enum Kind { B }; }")
    result = collect(tmp_path, {"nested.hpp": source})
    values = [qt_metadata(n) for n in facts(result, "namespace")]
    assert {md["qualified_name"] for md in values} == {"Left::Shared", "Right::Shared"}
    assert all(md["namespace_identity_status"] == "named" and md["status"] == "source_only" for md in values)


@pytest.mark.parametrize("name", ["Q_OBJECT", "Q_INVOKABLE", "Q_GADGET"])
def test_stringified_export_name_cannot_create_nested_annotation_authority(tmp_path, name):
    """QML_NAMED_ELEMENT stringifies NAME; payload spelling is never another marker."""
    source = f"class Value {{ Q_GADGET public: QML_NAMED_ELEMENT({name}) int ordinary(); }};"
    unit = read_cpp(write(tmp_path, "value.hpp", source), tmp_path)
    assert [md["name"] for md in unit.macros] == ["Q_GADGET", "QML_NAMED_ELEMENT"]
    result = collect(tmp_path, {"value.hpp": source})
    cls = qt_metadata(facts(result, "class", "Value")[0])
    assert cls["is_gadget"] and not cls["source_q_object"] and not cls["is_qobject"]
    member = qt_metadata(facts(result, "member", "ordinary")[0])
    assert member["roles"] == [] and member["access"] == "public"
    registration = qt_metadata(facts(result, "registration", name)[0])
    assert registration["raw_name"] == name
