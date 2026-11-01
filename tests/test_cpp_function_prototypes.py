"""INC-QML-70: explicit C++ prototype facts preserve scope without guessed bodies."""
from __future__ import annotations

import base64
import json

import pytest

from graphify.build import build_from_json
from graphify.cpp_header import is_cpp_header
from graphify.export import to_json
from graphify.extract import _get_extractor, extract, extract_c, extract_cpp, extract_objc
from graphify.paths import load_node_link_graph


def prototypes(result):
    return [node for node in result["nodes"] if "cpp_prototype" in node.get("metadata", {})]


@pytest.mark.parametrize("body", [
    "struct Value; bool update(Value &value);",
    "struct Value; const Value &inspect(const Value &value);",
    "struct Value; bool update(Value &&);",
    "struct Value; void update(void (*callback)(Value &));",
])
def test_req_qml022_ac02_reference_only_header_selects_actual_cpp_grammar(tmp_path, body):
    """Reference-only headers cannot report C syntax errors for valid C++ declarations."""
    path = tmp_path / "api.h"
    path.write_text(body, encoding="utf-8")
    assert is_cpp_header(path) is True and _get_extractor(path) is extract_cpp
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result.get("parse_errors")
    assert len(prototypes(result)) == 1


@pytest.mark.parametrize("body", [
    "int update(int left, int right) { return left & right; }",
    "int update(int left, int right) { return nested(left & right); }",
    "void update(void) { left & nested(right); }",
    "void update(void) { left && nested(right); }",
    "int mask = 1 & 2; int update(int value);",
    'const char *text = "Value &inspect(Value &); class Invented {};";',
    "/* Value &inspect(Value &); */ int update(int value);",
    "typedef int (*Callback)(int); void install(Callback callback);",
    "#define REFERENCE_API Value &inspect(Value &);\nint update(int value);",
    "#define REFERENCE_API " + "\\\n" + "Value &inspect(Value &);\nint update(int value);",
])
def test_req_qml022_ac06_c_header_expressions_callbacks_and_inert_text_keep_admission(tmp_path, body):
    """C expressions and callback pointers cannot supply a C++ reference declaration hint."""
    path = tmp_path / "api.h"
    path.write_text(body, encoding="utf-8")
    assert is_cpp_header(path) is False
    assert _get_extractor(path) is extract_c


def test_req_qml022_ac06_objc_admission_precedes_cpp_reference_hint(tmp_path):
    path = tmp_path / "api.h"
    path.write_text("@interface Owner\n- (void)update;\n@end\n", encoding="utf-8")
    assert _get_extractor(path) is extract_objc


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac02_scoped_overloads_have_exact_bytes_and_survive_reload(tmp_path, directed):
    """Distinct namespaces/signatures survive the real facade/cache/build/export path."""
    raw = ("\ufeff// café 雪\r\nint work(int value);\r\n"
           "namespace First { int work(int value); int work(double value); }\r\n"
           "namespace Second { int work(int value); }\r\n").encode()
    path = tmp_path / "api.hpp"
    path.write_bytes(raw)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert result == extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = prototypes(result)
    assert len(nodes) == len({node["id"] for node in nodes}) == 4
    assert sorted(base64.b64decode(node["metadata"]["cpp_prototype"]["qualified_name_b64"]).decode()
                  for node in nodes) == ["First::work", "First::work", "Second::work", "work"]
    for node in nodes:
        fact = node["metadata"]["cpp_prototype"]
        assert fact["contract_version"] == 1 and fact["role"] == "declaration"
        assert len(fact["signature"]) == 64
        span = fact["span"]
        assert raw[span["start_byte"]:span["end_byte"]] in {b"int work(int value);", b"int work(double value);"}
        assert node["source_location"] == f"L{span['start_row'] + 1}"
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert {node["id"] for node in nodes} <= set(loaded)
    for node in nodes:
        assert loaded.nodes[node["id"]]["metadata"]["cpp_prototype"] == node["metadata"]["cpp_prototype"]


def test_req_qml022_ac06_callback_data_and_partial_or_local_declarations_are_not_free_prototypes(tmp_path):
    """Function syntax inside data/local/error shapes supplies no namespace callable authority."""
    path = tmp_path / "api.hpp"
    path.write_text("void (*callback)(int); int (&array)[2];\n"
                    "void outer() { void local(int value); }\n"
                    "int malformed(Value &value;\n", encoding="utf-8")
    result = extract_cpp(path)
    assert not prototypes(result)
    assert result.get("parse_errors")


@pytest.mark.parametrize("call", ["work(1)", "First::work(1)", "Missing::work(1)"])
def test_req_qml022_ac06_prototypes_cannot_supply_guessed_body_or_namespace_calls(tmp_path, call):
    """Prototype-only source evidence stays separate from scope/overload body resolution."""
    path = tmp_path / "api.hpp"
    path.write_text("namespace First { int work(int value); }\nnamespace Second { int work(double value); }\n"
                    f"void caller() {{ {call}; }}\n", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    declarations = prototypes(result)
    assert len(declarations) == 2
    identities = {node["id"] for node in declarations}
    assert not any(edge["target"] in identities and edge["relation"] in {"calls", "indirect_call"} for edge in result["edges"])


def test_req_qml022_ac06_new_prototypes_preserve_existing_definition_call_target(tmp_path):
    """Adding sibling/overload declarations does not steal an existing definition-backed call."""
    path = tmp_path / "api.hpp"
    body = "int work(int value) { return value; }\nint caller() { return work(1); }\n"
    path.write_text(body, encoding="utf-8")
    before = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    original = next(node["id"] for node in before["nodes"] if node["label"] == "work()")
    path.write_text("int work(int value); namespace Other { int work(double value); }\n" + body, encoding="utf-8")
    after = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len(prototypes(after)) == 2
    assert original in {node["id"] for node in after["nodes"]}
    assert any(edge["target"] == original and edge["relation"] == "calls" for edge in after["edges"])


def test_req_qml022_ac02_actual_function_parameters_own_callback_return_overload_ids(tmp_path):
    """The nearest function binding supplies parameters, while its callback return type does not."""
    path = tmp_path / "api.hpp"
    path.write_text("void (*factory(int value))(double); void (*factory(double value))(int);\n"
                    "template<class T> T query(T value);\n", encoding="utf-8")
    result = extract_cpp(path)
    nodes = prototypes(result)
    assert len(nodes) == len({node["id"] for node in nodes}) == 3
    first = {node["metadata"]["cpp_prototype"]["signature"] for node in nodes if node["label"] == "factory()"}
    assert len(first) == 2 and all(len(signature) == 64 for signature in first)
    prior = {node["id"] for node in nodes}
    path.write_text(path.read_text().replace("value", "renamed"), encoding="utf-8")
    assert {node["id"] for node in prototypes(extract_cpp(path))} == prior


@pytest.mark.parametrize("scope", ["namespace {", "namespace " + "A" * 400 + " {"])
def test_req_qml022_ac06_anonymous_or_oversize_scope_keeps_identity_without_truncated_name(tmp_path, scope):
    """Unavailable canonical text cannot become a truncated lookup key or a global owner."""
    path = tmp_path / "api.hpp"
    path.write_text(scope + " int work(int value); }\n", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert len(prototypes(result)) == 1
    fact = prototypes(result)[0]["metadata"]["cpp_prototype"]
    assert fact["qualified_name_b64"] == ""
    assert fact["qualified_name_status"] == ("anonymous" if scope == "namespace {" else "oversize")
