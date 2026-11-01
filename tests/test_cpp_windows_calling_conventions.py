"""INC-QML-92: source calling-convention compatibility preserves actual callables."""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import normalize_qt_cpp, read_cpp


@pytest.mark.parametrize("modifier", ["CALLBACK", "WINAPI", "APIENTRY"])
def test_req_qml022_ac02_sdk_convention_keeps_name_parameters_and_direct_calls(tmp_path, modifier):
    """A literal SDK include admits only the convention slot of the real declaration."""
    path = tmp_path / "callbacks.cpp"
    source = (f'#include <qt_windows.h>\nBOOL {modifier} callback(int,int,int value,LONG_PTR state)'
              '{return value;} void invoke(){callback(0,0,1,2);}\n').encode()
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    assert unit.source == source and len(unit.parsed_source) == len(source)
    start = source.index(modifier.encode())
    assert unit.parsed_source[start:start + len(modifier)] == b" " * len(modifier)
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    mapping = map_cpp(unit, direct["nodes"], direct["edges"], root=tmp_path)
    callback = next(record for record in mapping.functions if record["name"] == "callback")
    assert callback["return_type"] == "BOOL"
    assert callback["parameter_types"] == ["int", "int", "int", "LONG_PTR"]
    assert [item["name"] for item in callback["parameters"]] == ["", "", "value", "state"]
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    target = next(node["id"] for node in result["nodes"] if node["label"] == "callback()")
    assert any(edge.get("relation") == "calls" and edge["target"] == target for edge in result["edges"])
    assert not any(node["label"] in {modifier, modifier + "()"} for node in result["nodes"])


def test_req_qml022_ac02_primitive_return_cannot_absorb_convention_as_fake_type(tmp_path):
    """The grammar's error-free long-CALLBACK misclassification still needs source repair."""
    path = tmp_path / "callbacks.cpp"
    source = b'#include <windows.h>\nlong CALLBACK callback(int value){return value;}\n'
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    assert unit.parsed_source != source
    result = extract_cpp(path)
    callback = next(record for record in map_cpp(unit, result["nodes"], result["edges"], root=tmp_path).functions
                    if record["name"] == "callback")
    assert callback["return_type"] == "long"


def test_req_qml022_ac06_repeated_positive_windows_guards_keep_conditional_source_fact(tmp_path):
    """Exact guarded source context permits syntax recovery without claiming branch execution."""
    path = tmp_path / "callbacks.cpp"
    source = ('#ifdef Q_OS_WIN\n#include <qt_windows.h>\n#endif\n'
              '#ifdef Q_OS_WIN\nBOOL CALLBACK callback(int,int,int value,LONG_PTR state){return value;}\n#endif\n').encode()
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    assert unit.source == source and not unit.tree.has_error
    direct = extract_cpp(path)
    callback = next(node for node in direct["nodes"] if node["label"] == "callback()")
    assert callback["metadata"]["cpp_function"]["conditional"] is True
    assert not callback.get("_callable_class") and not callback.get("is_class")


def test_req_qml022_ac06_original_bom_crlf_unicode_spans_survive_calling_convention_view(tmp_path):
    """Only the convention token changes; declaration/parameter spans index original bytes."""
    path = tmp_path / "callbacks.cpp"
    source = '\ufeff// café 雪\r\n#include <QtCore/qt_windows.h>\r\nBOOL CALLBACK callback(int value){return value;}\r\n'.encode()
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    changed = [index for index, (left, right) in enumerate(zip(source, unit.parsed_source)) if left != right]
    start = source.index(b"CALLBACK")
    assert changed == list(range(start, start + len(b"CALLBACK")))
    direct = extract_cpp(path)
    callback = next(node for node in direct["nodes"] if node["label"] == "callback()")
    span = callback["metadata"]["cpp_function"]["span"]
    assert source[span["start_byte"]:span["end_byte"]] == b"BOOL CALLBACK callback(int value){return value;}"
    assert span["start_row"] == 2 and span["start_column"] == 0


def test_req_qml022_ac06_literal_stdcall_is_already_supported_without_sdk_recovery(tmp_path):
    """A compiler keyword is parsed directly and does not require SDK macro authority."""
    path = tmp_path / "callbacks.cpp"
    source = b'BOOL __stdcall callback(int value){return value;}'
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    assert unit.parsed_source == source and normalize_qt_cpp(source) is None
    assert not extract_cpp(path).get("parse_errors")


def test_req_qml022_ac06_convention_header_prototype_preserves_original_signature(tmp_path):
    """The same source slot keeps prototype role and arity without manufacturing a body."""
    path = tmp_path / "callbacks.hpp"
    source = b'#include <windows.h>\nBOOL CALLBACK callback(int value);\n'
    path.write_bytes(source)
    unit = read_cpp(path, tmp_path)
    direct = extract_cpp(path)
    prototype = next(node for node in direct["nodes"] if node.get("metadata", {}).get("cpp_prototype"))
    assert prototype["metadata"]["cpp_prototype"]["min_args"] == 1
    assert source[prototype["metadata"]["cpp_prototype"]["span"]["start_byte"]:
                  prototype["metadata"]["cpp_prototype"]["span"]["end_byte"]].startswith(b"BOOL CALLBACK callback")
    assert not unit.tree.has_error and not direct.get("parse_errors")
