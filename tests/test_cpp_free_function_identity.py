"""INC-QML-73: free definitions keep source scope, overloads and call uncertainty."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.base import _file_stem, _make_id


def definitions(result):
    return [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_function", {}).get("role") == "definition"]


def name(node):
    return base64.b64decode(node["metadata"]["cpp_function"]["qualified_name_b64"]).decode()


@pytest.mark.parametrize("source,expected", [
    ("namespace First { int work(int value) { return value; } }\nnamespace Second { int work(int value) { return value; } }", ["First::work", "Second::work"]),
    ("int work(int value) { return value; }\nint work(double value) { return 1; }", ["work", "work"]),
    ("int Read(int value) { return value; }\nint read(int value) { return value; }", ["Read", "read"]),
])
def test_req_qml022_ac02_free_definitions_preserve_case_scope_and_overload_identity(tmp_path, source, expected):
    """Distinct valid source functions cannot disappear during ordinary name normalization."""
    path = tmp_path / "api.cpp"
    raw = ("\ufeff// café 雪\r\n" + source.replace("\n", "\r\n") + "\r\n").encode()
    path.write_bytes(raw)
    result = extract_cpp(path)
    callables = [node for node in result["nodes"] if node.get("_callable") and not node.get("_callable_class")]
    assert len(callables) == len(expected)
    nodes = definitions(result)
    assert len(nodes) == len({node["id"] for node in nodes}) == len(expected)
    assert sorted(name(node) for node in nodes) == sorted(expected)
    for node in nodes:
        fact = node["metadata"]["cpp_function"]
        assert fact["contract_version"] == 1 and fact["function_kind"] == "free"
        span = fact["span"]
        fragment = raw[span["start_byte"]:span["end_byte"]]
        assert b"{" in fragment and fragment.endswith(b"}")
        assert node["source_location"] == f"L{span['start_row'] + 1}"


def test_req_qml022_ac02_unique_global_definition_keeps_existing_id_and_call_target(tmp_path):
    """A new provenance contract must preserve existing unambiguous ordinary-function consumers."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(int value) { return value; } int caller() { return work(1); }", encoding="utf-8")
    direct = extract_cpp(path)
    node = next(node for node in definitions(direct) if name(node) == "work")
    assert node["id"] == _make_id(_file_stem(path), "work")
    assert any(edge["target"] == node["id"] and edge["relation"] == "calls" for edge in direct["edges"])


def test_req_qml022_ac02_unrelated_qualified_class_does_not_resalt_global_function(tmp_path):
    """Existing qualified type IDs already separate their role from an ordinary global body."""
    path = tmp_path / "api.cpp"
    path.write_text("namespace Other{class Callback{};} void callback(){}")
    node = next(node for node in extract_cpp(path)["nodes"] if "cpp_function" in node.get("metadata", {}) and name(node) == "callback")
    assert node["id"] == _make_id(_file_stem(path), "callback")


@pytest.mark.parametrize("call,namespace,expected", [
    ("First::work(1)", "", "First::work"),
    ("work(1)", "First", "First::work"),
    ("work(1)", "", None),
    ("Missing::work(1)", "", None),
])
def test_req_qml022_ac06_free_calls_require_actual_lexical_or_qualified_namespace(tmp_path, call, namespace, expected):
    """Neither a matching basename nor a sibling namespace can supply the chosen body."""
    path = tmp_path / "api.cpp"
    caller = f"int caller() {{ return {call}; }}"
    if namespace:
        caller = f"namespace {namespace} {{ {caller} }}"
    path.write_text("namespace First { int work(int value) { return value; } }\n"
                    "namespace Second { int work(int value) { return value; } }\n" + caller, encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    funcs = {node["id"]: node for node in definitions(result)}
    caller_id = next(identity for identity, node in funcs.items() if name(node).endswith("caller"))
    targets = {name(funcs[edge["target"]]) for edge in result["edges"]
               if edge["source"] == caller_id and edge["relation"] == "calls" and edge["target"] in funcs}
    assert targets == ({expected} if expected else set())


@pytest.mark.parametrize("shadow", ["int (*work)(int)", "local"])
def test_req_qml022_ac06_local_function_pointer_shadow_cannot_bind_global_body(tmp_path, shadow):
    """A local or formal callback is runtime data even beside an identically named global function."""
    path = tmp_path / "api.cpp"
    body = "return work(1);" if shadow != "local" else "auto work=[](int value){return value;}; return work(1);"
    parameter = shadow if shadow != "local" else ""
    path.write_text("int work(int value) { return value; } " + f"int caller({parameter}) {{ {body} }}", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    by_label = {node["label"]: node for node in result["nodes"]}
    assert not any(edge["source"] == by_label["caller()"]["id"] and edge["target"] == by_label["work()"]["id"]
                   and edge["relation"] in {"calls", "indirect_call"} for edge in result["edges"])
    nodes = {name(node): node for node in definitions(result)}
    assert not any(edge["source"] == nodes["caller"]["id"] and edge["target"] == nodes["work"]["id"]
                   and edge["relation"] in {"calls", "indirect_call"} for edge in result["edges"])


def test_req_qml022_ac06_same_arity_overloads_and_cross_file_static_remain_unresolved(tmp_path):
    """Argument count alone cannot choose a conversion overload or another file's static body."""
    sources = {
        "api.cpp": "int work(int value) { return value; } int work(double value) { return 1; } int caller() {return work(1);}",
        "private.cpp": "static int hidden(int value) { return value; }",
        "caller.cpp": "extern int hidden(int value); int externalCaller() { return hidden(1); }",
    }
    for relative, source in sources.items():
        (tmp_path / relative).write_text(source, encoding="utf-8")
    result = extract([tmp_path / relative for relative in sources], root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {node["id"]: node for node in definitions(result)}
    for caller in ("caller", "externalCaller"):
        source = next(identity for identity, node in nodes.items() if name(node) == caller)
        assert not any(edge["source"] == source and edge["target"] in nodes and edge["relation"] == "calls"
                       for edge in result["edges"])
