"""INC-QML-63/75/77: complete source identifiers own annotation spellings."""
from __future__ import annotations

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("name", ["ÅQ_OBJECT", "Q_OBJECTÅ", r"\u0041Q_OBJECT",
                                  r"Q_OBJECT\u0041", r"\U000000C5Q_OBJECT", r"Q_OBJECT\U000000C5"])
def test_req_qml022_ac06_annotation_fragment_cannot_erase_ordinary_source_identifier(tmp_path, name):
    """Unicode/UCN field identifiers survive and supply no metaobject authority."""
    path = tmp_path / "native.hpp"
    original = ("class Native { int " + name + "; public: Q_INVOKABLE void run(); };").encode()
    path.write_bytes(original)
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    field = next(node for node in direct["nodes"] if node["label"] == name)
    assert field["metadata"]["cpp_declarator"]["kind"] == "field"
    unit = read_cpp(path, tmp_path)
    start = original.index(name.encode())
    assert unit.parsed_source[start:start + len(name.encode())] == name.encode()
    result = analysis(tmp_path, {"native.hpp": original.decode()})
    native = qt_metadata(sites(result, "class")[0])
    assert native["source_q_object"] is False and native["metaobject_count"] == 0
    assert all(qt_metadata(node)["raw_name"] != name for node in sites(result, "member"))
    assert qt_metadata(sites(result, "member")[0])["roles"] == ["invokable"]


@pytest.mark.parametrize("name", ["ÅQFETCH", "QFETCHÅ", r"\u0041QFETCH", r"QFETCH\u0041"])
def test_req_qml022_ac03_qt_test_identifier_fragment_remains_ordinary(tmp_path, name):
    """A larger function identifier cannot become QtTest typed data syntax."""
    result = analysis(tmp_path, {"checks.cpp": "#include <QTest>\nvoid " + name + "(int,int){} void run(){" + name + "(1,2);}"})
    assert not result.get("qml_failures")
    assert not sites(result, "test_data") and not sites(result, "test_assertion")
    target = next(node["id"] for node in result["nodes"] if node["label"] == name + "()")
    assert any(edge["relation"] == "calls" and edge["target"] == target for edge in result["edges"])


def test_req_qml022_ac06_standalone_marker_survives_unicode_surroundings(tmp_path):
    """Actual standalone tokens retain positive authority and original byte ranges."""
    result = analysis(tmp_path, {"native.hpp": '\ufeff// café 雪\r\nclass Native: public QObject { Q_OBJECT public: Q_INVOKABLE void run(); };\r\n'})
    native = qt_metadata(sites(result, "class")[0])
    assert native["source_q_object"] is True and native["metaobject_count"] == 1
    assert any("invokable" in qt_metadata(node)["roles"] for node in sites(result, "member"))
