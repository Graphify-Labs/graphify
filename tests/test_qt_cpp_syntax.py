"""Original-byte Qt recovery, false-positive rejection and bounded failure."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp, is_qt_cpp_source
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import QtCppError, lexical_code, read_cpp, source_span
from tests.qt_cpp_test_helpers import collect, facts, write
from graphify.extractors.qt_cpp_facts import qt_metadata


@pytest.mark.parametrize("section,access", [("public Q_SLOTS", "public"), ("protected Q_SLOTS", "protected"),
                                         ("private Q_SLOTS", "private"), ("Q_SLOTS", "public"),
                                         ("Q_SIGNALS", "public"), ("signals", "public")])
def test_access_sections_keep_original_roles_offsets(tmp_path, section, access):
    source = f'class B : public QObject {{ Q_OBJECT {section}: void changed(int x); }};'
    path = write(tmp_path, "b.hpp", source)
    result = collect(tmp_path, {"b.hpp": source})
    member = qt_metadata(facts(result, "member", "changed")[0])
    assert member["access"] == access
    assert member["roles"] == (["signal"] if section in {"signals", "Q_SIGNALS"} else ["slot"])
    span = member["span"]
    assert path.read_bytes()[span["start_byte"]:span["end_byte"]] == b"void changed(int x);"
    unit = read_cpp(path, tmp_path)
    assert len(unit.source) == len(unit.parsed_source) == len(unit.code)


def test_annotations_legacy_calls_and_ordinary_emit_are_distinct(tmp_path):
    source = '''class B : public QObject { Q_OBJECT public: Q_SIGNAL void changed(int); Q_SLOT void accept(int); };
void emit() {} void install(B *s,B *r) {
QObject::connect(s, SIGNAL(changed(int)), r, SLOT(accept(int)));
emit(); emit s->changed(1); Q_EMIT r->changed(2);
}'''
    unit = read_cpp(write(tmp_path, "calls.cpp", source), tmp_path)
    assert not unit.tree.has_error
    assert b"void emit()" in unit.parsed_source and b"emit();" in unit.parsed_source
    assert b"emit s" not in unit.parsed_source
    assert unit.source == source.encode()
    result = collect(tmp_path, {"calls.cpp": source})
    assert qt_metadata(facts(result, "member", "changed")[0])["roles"] == ["signal"]
    assert qt_metadata(facts(result, "member", "accept")[0])["roles"] == ["slot"]


def test_comments_strings_raw_literals_and_preprocessor_definitions_are_inert(tmp_path):
    source = '''// QML_ELEMENT Q_OBJECT
/* Q_PROPERTY(int bad READ bad) */
const char *a = "QML_NAMED_ELEMENT(Fake)";
const char *b = R"tag(QML_ELEMENT // Q_OBJECT)tag";
#define DECLARE_QML QML_ELEMENT
class Ordinary {};
'''
    path = write(tmp_path, "ordinary.cpp", source)
    unit = read_cpp(path, tmp_path)
    assert unit.macros == []
    assert lexical_code(source.encode()).count(b"\n") == source.count("\n")
    result = collect(tmp_path, {"ordinary.cpp": source})
    assert facts(result, "registration") == []
    assert not is_qt_cpp_source(write(tmp_path, "strings.cpp", 'const char *s = "QObject QML_ELEMENT";'))


def test_unicode_crlf_macro_spans_are_original_bytes(tmp_path):
    source = '// café ☃\r\nclass B : public QObject {\r\nQ_OBJECT\r\nQML_NAMED_ELEMENT(B)\r\n};\r\n'
    unit = read_cpp(write(tmp_path, "B.hpp", source), tmp_path)
    macro = next(item for item in unit.macros if item["name"] == "QML_NAMED_ELEMENT")
    start = source.encode().index(b"QML_NAMED_ELEMENT")
    assert macro["span"] == source_span(source.encode(), start, start + len(b"QML_NAMED_ELEMENT(B)"))
    assert macro["span"]["start_row"] == 3 and macro["span"]["start_column"] == 0
    assert unit.parsed_source.count(b"\r\n") == 5


@pytest.mark.parametrize("source", ["class B { Q_OBJECT Q_PROPERTY(int bad", "class B : QObject { Q_OBJECT void broken( };", "\xff"])
def test_invalid_qt_source_is_explicit_failure_without_authoritative_overlay(tmp_path, source):
    path = tmp_path / "bad.hpp"
    path.write_bytes(source.encode() if source != "\xff" else b"Q_OBJECT \xff")
    result = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [result], root=tmp_path)
    assert result["nodes"] == result["edges"] == []
    assert result["qml_failures"][0]["code"] in {"QT_CPP_SYNTAX", "QT_CPP_READ"}
    assert str(tmp_path) not in str(result["diagnostics"])


def test_non_qt_malformed_cpp_is_not_new_failure(tmp_path):
    path = write(tmp_path, "ordinary.cpp", "void unfinished(")
    result = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [result], root=tmp_path)
    assert "qml_failures" not in result


def test_read_limits_and_root_rejection(tmp_path, monkeypatch):
    path = write(tmp_path, "large.hpp", "Q_OBJECT " * 20)
    monkeypatch.setattr("graphify.extractors.qt_cpp_syntax.MAX_CPP_BYTES", 10)
    with pytest.raises(QtCppError, match="5 MB") as failure:
        read_cpp(path, tmp_path)
    assert failure.value.code == "QT_CPP_LIMIT"
    with pytest.raises(QtCppError) as outside:
        read_cpp(path, tmp_path / "other")
    assert outside.value.code == "QT_CPP_ROOT"


def test_missing_canonical_ids_are_not_reconstructed(tmp_path):
    unit = read_cpp(write(tmp_path, "b.hpp", "class B: public QObject { Q_OBJECT public: Q_INVOKABLE void go(void); };"), tmp_path)
    mapping = map_cpp(unit, [], [], root=tmp_path)
    assert mapping.classes[0]["node_id"] == ""
    assert mapping.functions[0]["node_id"] == ""
    assert mapping.functions[0]["signature"] == "go()"


def test_explicit_member_pointer_cast_recovery_preserves_source_signature(tmp_path):
    source = 'void install(){ QObject::connect(s, static_cast<void (Sender::*)(int)>(&Sender::changed), r, &Receiver::accept); }'
    unit = read_cpp(write(tmp_path, "cast.cpp", source), tmp_path)
    assert not unit.tree.has_error and unit.source == source.encode() and unit.code == source.encode()
    pointer = b"&Sender::changed"
    offset = source.encode().index(pointer)
    assert unit.parsed_source[offset:offset + len(pointer)] == pointer
    assert len(unit.parsed_source) == len(source.encode())
    assert b"static_cast" not in unit.parsed_source


def test_overlay_root_rejection_happens_before_admission_read(tmp_path, monkeypatch):
    path = tmp_path / "outside.hpp"
    path.write_text("class B { Q_OBJECT };", encoding="utf-8")
    def fail_read(_):
        raise AssertionError("out-of-root source was read")
    monkeypatch.setattr("graphify.extractors.qt_cpp_exposure.is_qt_cpp_source", fail_read)
    result = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [result], root=tmp_path / "allowed")
    assert result["qml_failures"][0]["code"] == "QT_CPP_ROOT"
    assert result["nodes"] == result["edges"] == []


def test_reference_pointer_parameter_names_are_not_part_of_type(tmp_path):
    result = collect(tmp_path, {"b.hpp": 'class B: public QObject { Q_OBJECT public: void accept(const int &value, QObject *object, int &&moved); };'})
    member = qt_metadata(facts(result, "member", "accept")[0])
    assert member["parameter_names"] == ["value", "object", "moved"]
    assert member["parameter_types"] == ["const int&", "QObject*", "int&&"]
    assert member["signature"] == "accept(const int&,QObject*,int&&)"
