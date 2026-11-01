"""INC-QML-86: accepted empty-default omission retains optional source arity."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp, extract
from graphify.extractors.cpp_empty_default_proof import erased_default_parameters, ErasedDefaultLimitError
from graphify.extractors.qt_cpp_syntax import read_cpp, walk
from graphify.paths import load_node_link_graph


def function(result, label="f()", kind="cpp_function"):
    return next(node for node in result["nodes"] if node["label"] == label and node.get("metadata", {}).get(kind))


def test_req_qml022_ac06_erased_empty_default_retains_actual_zero_argument_call(tmp_path):
    """A valid zero-argument call cannot disappear because the parser view omits its default."""
    path = tmp_path / "defaults.cpp"
    path.write_bytes(b'template<class T>struct Box{};void f(Box<int> value={}){} void run(){f();}')
    result = extract_cpp(path)
    target = function(result)
    fact = target["metadata"]["cpp_function"]
    assert fact["min_args"] == 0 and fact["max_args"] == 1
    assert fact["arity_status"] == "available"
    assert len(fact["erased_default_parameters"]) == 1
    assert any(edge.get("relation") == "calls" and edge["target"] == target["id"] for edge in result["edges"])


def test_req_qml022_ac06_source_sidecar_exact_byte_ranges_survive_facade_export(tmp_path):
    """Only actual omitted default bytes produce source provenance, with BOM/CRLF intact."""
    source = b'\xef\xbb\xbf// caf\xc3\xa9 \xe9\x9b\xaa\r\ntemplate<class T>struct Box{};void f(Box<int> value = { /* original */\r\n}){}\r\n'
    path = tmp_path / "defaults.cpp"
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    syntax = next(node for node in walk(unit.tree) if node.type == "function_declarator")
    records = erased_default_parameters(syntax, source)
    assert len(records) == 1
    assert source[slice(*records[0].default_span)].startswith(b"= {")
    assert source[slice(*records[0].default_span)].endswith(b"}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    target = function(result)
    md = target["metadata"]["cpp_function"]
    proof = md["erased_default_parameters"][0]
    assert proof == records[0].fact(source)
    assert md["min_args"] == 0 and md["max_args"] == 1
    graph = build_from_json(result, root=tmp_path)
    destination = tmp_path / "roundtrip.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert loaded.nodes[target["id"]]["metadata"]["cpp_function"] == md


@pytest.mark.parametrize("parameter", ["int value", 'const char* value = "= {}"', "int value /* = {} */"])
def test_req_qml022_ac06_unchanged_source_or_quoted_comment_equal_is_not_erased_proof(tmp_path, parameter):
    """Existing AST defaults remain primary; unchanged words/comments cannot invent a sidecar."""
    path = tmp_path / "plain.cpp"
    path.write_bytes(('void f(' + parameter + '){}').encode())
    unit = read_cpp(path, tmp_path)
    syntax = next(node for node in walk(unit.tree) if node.type == "function_declarator")
    assert erased_default_parameters(syntax, unit.source) == ()


def test_req_qml022_ac06_free_prototype_has_original_default_arity_without_body_guess(tmp_path):
    """Prototype source evidence records optionality independently of any definition join."""
    path = tmp_path / "defaults.hpp"
    path.write_bytes(b'template<class T>struct Box{};void f(Box<int> value={});')
    result = extract_cpp(path)
    node = function(result, kind="cpp_prototype")
    fact = node["metadata"]["cpp_prototype"]
    assert fact["min_args"] == 0 and fact["max_args"] == 1
    assert len(fact["erased_default_parameters"]) == 1
    assert not node.get("metadata", {}).get("cpp_function")


def test_req_qml022_ac06_erased_default_bound_never_truncates_into_arity_authority(tmp_path):
    """Fifty-one original omissions have an explicit unsupported status and no guessed call."""
    source = 'template<class T>struct Box{};void f(' + ','.join(f'Box<int> p{i}={{}}' for i in range(51)) + '){} void run(){f();}'
    path = tmp_path / "limit.cpp"
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    syntax = next(node for node in walk(unit.tree) if node.type == "function_declarator")
    with pytest.raises(ErasedDefaultLimitError):
        erased_default_parameters(syntax, unit.source)
    result = extract_cpp(path)
    node = function(result)
    fact = node["metadata"]["cpp_function"]
    assert fact["arity_status"] == "unsupported" and fact["arity_reason"] == "erased_default_parameter_limit"
    assert fact["min_args"] is None and fact["erased_default_parameters"] == []
    assert not [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge["target"] == node["id"]]
