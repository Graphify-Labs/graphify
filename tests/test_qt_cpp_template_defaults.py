"""INC-QML-53: REQ-QML-018-AC02 empty defaults preserve native declaration identity.

Public synthetic inputs exercise the actual parser, canonical C++ facade and
native fact producer. A clean parse alone cannot prove a declaration survived.
"""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import QtCppError, normalize_qt_cpp, read_cpp, walk


# Declaration success covers ordinary defaults, seven reported template shapes,
# a formerly clean-but-wrong void-return tree, and supported callback parameters.
DECLARATIONS = [
    ("ordinary", "void f(P p = {});", "f"),
    ("pointer_return", "T *f(P p = {});", "f"),
    ("template_pointer_return", "T *f(std::unique_ptr<P> p = {});", "f"),
    ("template_void_return", "void f(std::unique_ptr<P> p = {});", "f"),
    ("qualified_type", "T *f(ns::Owner<ns::Item> p = {});", "f"),
    ("qualified_function", "T *ns::f(std::unique_ptr<P> p = {});", "ns::f"),
    ("nested_templates", "T *f(std::unique_ptr<std::vector<P>> p = {});", "f"),
    ("multiple_parameters", "T *f(QObject *root, Logger &logger, std::unique_ptr<P> p = {}, std::optional<R> r = std::nullopt);", "f"),
    ("multiple_defaults", "T *f(std::unique_ptr<P> p = {}, std::vector<Q> q = {});", "f"),
    ("multiline_comment_default", "T *f(std::unique_ptr<P> p = { /* café */\r\n});", "f"),
    ("const_reference", "T *f(const std::vector<P> &p = {});", "f"),
    ("template_pointer", "T *f(std::vector<P> *p = {});", "f"),
    ("template_rvalue_reference", "T *f(std::vector<P> &&p = {});", "f"),
    ("comment_after_default", "T *f(std::vector<P> p = {} /* suffix */ );", "f"),
    ("definition", "T *f(std::unique_ptr<P> p = {}) { return nullptr; }", "f"),
    ("callback_primitive", "void f(void (*callback)(int) = {});", "f"),
    ("callback_named_type", "void f(void (*callback)(P value) = {});", "f"),
    ("nullopt", "T *f(std::optional<R> r = std::nullopt);", "f"),
    ("explicit_value", "T *f(std::unique_ptr<P> p = std::unique_ptr<P>{});", "f"),
]


def write(root, source):
    path = root / "adapter.hpp"
    path.write_bytes(source)
    return path


@pytest.mark.parametrize("name,text,expected", DECLARATIONS, ids=[row[0] for row in DECLARATIONS])
def test_req_qml018_ac02_template_default_retains_callable_and_original_spans(tmp_path, name, text, expected):
    """Recover declarations in-place without confusing error-free initializer ASTs."""
    source = (text + "\n").encode()
    path = write(tmp_path, source)
    unit = read_cpp(path, tmp_path)
    functions = [node for node in walk(unit.root) if node.type == "function_declarator"
                 and unit.field(node, "declarator") == expected]
    assert len(functions) == 1, name
    assert unit.source == source and len(unit.parsed_source) == len(source)
    assert [i for i, value in enumerate(source) if value in (10, 13)] == [
        i for i, value in enumerate(unit.parsed_source) if value in (10, 13)]
    assert unit.text(functions[0]).startswith(expected + "(")
    assert not extract_cpp(path).get("parse_errors")
    mapping = map_cpp(unit, [], [], root=tmp_path)
    records = [item for item in mapping.functions if item["qualified_name"] == expected]
    assert len(records) == 1 and records[0]["name"] == expected.split("::")[-1]
    assert records[0]["span"]["start_byte"] == 0
    assert records[0]["span"]["end_byte"] == len(source.rstrip())
    if "std::nullopt" in text:
        assert b"std::nullopt" in unit.parsed_source


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_req_qml008_ac02_template_recovery_retains_native_member_and_cold_warm_identity(tmp_path, newline):
    """The header's free function must not suppress its neighboring Qt member facts."""
    source = b"\xef\xbb\xbf" + newline.join([
        "// café ☃".encode(),
        b"QObject *make(QObject *root, std::unique_ptr<P> platform = {});",
        b"class Adapter : public QObject { Q_OBJECT public:",
        b" Q_INVOKABLE void accept(std::vector<P> values = {});",
        b"};", b"",
    ])
    path = write(tmp_path, source)
    unit = read_cpp(path, tmp_path)
    assert unit.source == source and unit.parsed_source.startswith(b"\xef\xbb\xbf")
    assert [i for i, byte in enumerate(unit.parsed_source) if byte in (10, 13)] == [
        i for i, byte in enumerate(source) if byte in (10, 13)]
    cold = extract([path], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path / ".cache", parallel=False)
    for result in (cold, warm):
        assert not result["failed_sources"] and not result["qt_failures"] and not result["qml_failures"]
        members = [node for node in result["nodes"] if qt_metadata(node).get("kind") == "member"
                   and qt_metadata(node).get("raw_name") == "accept"]
        assert len(members) == 1
        metadata = qt_metadata(members[0])
        assert metadata["generic_target_id"] and metadata["parameter_names"] == ["values"]
        assert metadata["parameter_types"] == ["std::vector<P>"] and metadata["roles"] == ["invokable"]
        span = metadata["span"]
        assert source[span["start_byte"]:span["end_byte"]] == b"void accept(std::vector<P> values = {});"
        assert span["start_row"] == 3
        ids = {node["id"] for node in result["nodes"]}
        assert metadata["generic_target_id"] in ids
    assert sorted(node["id"] for node in cold["nodes"]) == sorted(node["id"] for node in warm["nodes"])
    assert path.read_bytes() == source


# Expression, storage, inert literal and ambiguous declaration contexts must not
# become parameters merely because removing an assignment yields a clean tree.
INERT = [
    b"void use() { callback(value = {}); }",
    b"P value = {};",
    b"void use() { P value = {}; }",
    b"void (*callback)(P) = {};",
    b"using Callback = void (*)(std::unique_ptr<P>);",
    b'const char *text = "T *f(std::unique_ptr<P> p = {});";',
    b"// T *f(std::unique_ptr<P> p = {});\nvoid use();",
    b"void use() { object.value = {}; object->value = {}; }",
    b"T value((assignment = {}));",
    b"T value(std::move<P>(assignment) = {});",
    b"void use() { callback(std::vector<P> = {}); }",
    b"#define DEFAULT_ARG std::vector<P> value = {}\nvoid use();",
    b"void f(void (*callback)(std::vector<P> value = {}));",
    b"void (*callback)(std::vector<P> value = {});",
    b"void f(std::vector<P> (*callback)(P) = {});",
]


@pytest.mark.parametrize("source", INERT)
def test_req_qml001_ac04_empty_defaults_do_not_reclassify_nonparameter_contexts(source):
    """Lexical candidates need proven named declaration ownership to be omitted."""
    assert normalize_qt_cpp(source) is None


@pytest.mark.parametrize("source", [
    b"T *f(std::unique_ptr<P> p = {;);",
    b"T *f(std::unique_ptr<P> p = {}, @);",
    b"T *f(std::unique_ptr<P> p = {}) @;",
    b"void use() { callback(value = {} @); }",
    b"T *f(std::unique_ptr<P> p = {} garbage);",
    b"T *f(std::unique_ptr<P> p = {1});",
])
def test_req_qml012_ac02_malformed_template_defaults_remain_unmodified_and_rejected(tmp_path, source):
    """An empty-default candidate cannot repair damage elsewhere or mask a value."""
    assert normalize_qt_cpp(source) is None
    with pytest.raises(QtCppError) as rejected:
        read_cpp(write(tmp_path, source), tmp_path)
    assert rejected.value.code == "QT_CPP_SYNTAX"


def test_req_qml018_ac02_bare_callback_ambiguity_is_not_synthetic_declaration(tmp_path):
    """Bare user-type callbacks are a separate pre-existing grammar limitation.

    Even without a default, this grammar reads the signature as initialization.
    The bounded recovery leaves it unchanged rather than inventing authority.
    Primitive or named callback arguments are covered by success fixtures above.
    """
    source = b"void f(void (*callback)(P) = {});"
    assert normalize_qt_cpp(source) is None
    unit = read_cpp(write(tmp_path, source), tmp_path)
    assert not any(node.type == "function_declarator" for node in walk(unit.root))
    mapping = map_cpp(unit, [], [], root=tmp_path)
    assert mapping.functions == []


def test_req_qml001_ac04_unnamed_template_default_keeps_conservative_rejection(tmp_path):
    """Unnamed template syntax lacks this recovery's named-parameter proof.

    It is valid C++ outside the new bounded profile; keep the syntax diagnostic
    rather than treating an initializer-like spelling as authoritative identity.
    """
    source = b"T *f(std::vector<P> = {});"
    assert normalize_qt_cpp(source) is None
    with pytest.raises(QtCppError) as rejected:
        read_cpp(write(tmp_path, source), tmp_path)
    assert rejected.value.code == "QT_CPP_SYNTAX"
