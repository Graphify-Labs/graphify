"""INC-QML-85: locally proven C++ adapters compose before a strict Qt final gate."""
from __future__ import annotations

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_syntax import QtCppError, normalize_qt_cpp, read_cpp


@pytest.mark.parametrize("data,body", [
    ("int Owner::*data;", ""),
    ("", "void run(){QFETCH(int,value);}"),
    ("int Owner::*data;", "void run(){QFETCH(int,value);}"),
])
def test_req_qml022_ac06_member_pointer_and_qt_test_supported_views_compose(tmp_path, data, body):
    """Each isolated mechanism and their combination retain original source/member identity."""
    path = tmp_path / "checks.hpp"
    source = '#include <QTest>\nclass Owner{public:int value;};class Checks{public:' + data + body + '};'
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    assert not unit.tree.has_error and unit.source == source.encode()
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    if data:
        node = next(node for node in direct["nodes"] if node["label"] == "data")
        assert node["metadata"]["cpp_declarator"]["member_pointer"]["owner_spelling"] == "Owner"
        assert node.get("_callable") is not True
    if body:
        assert len(unit.qt_test_macros) == 1


@pytest.mark.parametrize("qt_test", [False, True])
def test_req_qml022_ac06_reclassified_template_default_and_qt_test_views_compose(tmp_path, qt_test):
    """Unrelated body recovery cannot suppress a previously supported template declaration."""
    path = tmp_path / "checks.hpp"
    source = '#include <QTest>\nstruct P{};struct T{};namespace Lib{template<class V>struct Box{};} '
    source += 'T*f(Lib::Box<P> p = {}); class Checks{void run(){' + ('QFETCH(int,value);' if qt_test else '') + '}};'
    path.write_bytes(source.encode())
    unit = read_cpp(path, tmp_path)
    assert not unit.tree.has_error and unit.source == source.encode()
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    assert any(node["label"] == "f()" for node in direct["nodes"])


def test_req_qml022_ac06_generic_partial_view_does_not_weaken_final_qt_syntax_gate(tmp_path):
    """Known local compatibility survives while unrelated malformed input remains an error."""
    path = tmp_path / "partial.hpp"
    source = b'class Owner{};class Holder{int Owner::*data;};void unfinished('
    path.write_bytes(source)
    normalized = normalize_qt_cpp(source)
    assert normalized is not None and normalized != source
    result = extract_cpp(path)
    assert result.get("parse_errors")
    field = next(node for node in result["nodes"] if node["label"] == "data")
    metadata = field["metadata"]["cpp_declarator"]
    assert metadata["member_pointer"]["owner_spelling"] == "Owner"
    assert source[metadata["span"]["start_byte"]:metadata["span"]["end_byte"]] == b"Owner::*data"
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"
