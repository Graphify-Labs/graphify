"""INC-QML-81: TU launchers are source occurrences, never generated program execution."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("macro", ["QTEST_MAIN", "QTEST_GUILESS_MAIN", "QTEST_APPLESS_MAIN"])
@pytest.mark.parametrize("header", ["QTest", "QtTest"])
def test_req_qml022_ac03_qt_test_launcher_preserves_actual_body_without_invented_main(tmp_path, macro, header):
    """No-semicolon harness syntax cannot erase genuine class/method/data source facts."""
    source = f'''\ufeff#include <{header}>\r
// café 雪\r
class Checks:public QObject{{Q_OBJECT private slots:void run(){{QFETCH(int,value);QTRY_COMPARE(value,1);}}}};\r
{macro}(Checks)\r
#include "checks.moc"\r
'''
    path = tmp_path / "checks.cpp"
    path.write_bytes(source.encode())
    assert not extract_cpp(path).get("parse_errors")
    unit = read_cpp(path, tmp_path)
    assert unit.source == source.encode() and len(unit.parsed_source) == len(unit.source)
    assert len(unit.test_launchers) == 1
    result = analysis(tmp_path, {"checks.cpp": source})
    launcher = sites(result, "test_launcher")
    assert len(launcher) == len(sites(result, "test_data")) == 1
    md = qt_metadata(launcher[0])
    assert md["mechanism"] == macro and md["class_hint"] == "Checks"
    assert md["status"] == "source_only" and md["runtime_status"] == "unverified"
    assert source.encode()[md["span"]["start_byte"]:md["span"]["end_byte"]] == f"{macro}(Checks)".encode()
    assert not any(node.get("_callable") and node["label"].removesuffix("()") == "main" for node in result["nodes"])
    assert not sites(result, "qml_load") and not sites(result, "context_binding")
    assert any(edge.get("context") == "qt_source_file" and edge["target"] == launcher[0]["id"]
               for edge in result["edges"])
    graph = build_from_json(result, root=tmp_path, directed=True)
    destination = tmp_path / "roundtrip.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert qt_metadata(loaded.nodes[launcher[0]["id"]]) == md


@pytest.mark.parametrize("macro,args", [("QUICK_TEST_MAIN", "example"), ("QUICK_TEST_MAIN_WITH_SETUP", "example, Setup")])
def test_req_qml022_ac03_quick_launcher_cannot_invent_engine_setup_callbacks(tmp_path, macro, args):
    """The documented SDK family records hints without supplying implicit engine/load identity."""
    result = analysis(tmp_path, {"quick.cpp": '''#include <QtQuickTest>
class Setup:public QObject{ Q_OBJECT public slots:
 void qmlEngineAvailable(QQmlEngine* engine){ engine->rootContext()->setContextProperty("backend",this); }
};
''' + macro + '(' + args + ')\n#include "quick.moc"\n'})
    md = qt_metadata(sites(result, "test_launcher")[0])
    assert md["framework"] == "qt_quick_test" and md["suite_name"] == "example"
    assert md["class_hint"] == ("Setup" if "WITH_SETUP" in macro else "")
    assert not sites(result, "qml_load") and not sites(result, "context_binding")
    assert not [edge for edge in result["edges"] if edge.get("relation") == "calls"
                and edge.get("context", "").startswith("qt_test_")]


@pytest.mark.parametrize("header,macro", [("QTest", "QUICK_TEST_MAIN"), ("QtQuickTest", "QTEST_MAIN")])
def test_req_qml022_ac03_sdk_families_cannot_lend_each_other_launcher_authority(tmp_path, header, macro):
    """A familiar macro spelling requires its own literal/documented SDK context."""
    path = tmp_path / "checks.cpp"
    path.write_text('#include <' + header + '>\n' + macro + '(Checks)\n', encoding="utf-8")
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)


@pytest.mark.parametrize("statement", ["QTEST_MAIN();", "QTEST_MAIN(Checks,Other);", "QTEST_MAIN(factory());",
                                         "namespace N{QTEST_MAIN(Checks)}", "void run(){QTEST_MAIN(Checks)}",
                                         "QUICK_TEST_MAIN_WITH_SETUP(name);", "QUICK_TEST_MAIN_WITH_SETUP(1,Setup);"])
def test_req_qml022_ac06_invalid_or_non_tu_launcher_stays_explicitly_rejected(tmp_path, statement):
    """Balanced names alone cannot launder launcher scope/arity/expression syntax."""
    path = tmp_path / "checks.cpp"
    path.write_text('#include <QTest>\n#include <QtQuickTest>\n' + statement, encoding="utf-8")
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"


def test_req_qml022_ac06_launcher_class_hint_does_not_grant_metaobject_marker(tmp_path):
    """A stringified type-looking macro argument stays opaque to annotation scanning."""
    result = analysis(tmp_path, {"checks.cpp": '#include <QTest>\nclass Native{public:int value;};\nQTEST_MAIN(Q_OBJECT)\n'})
    assert qt_metadata(sites(result, "test_launcher")[0])["class_hint"] == "Q_OBJECT"
    assert all(qt_metadata(node)["source_q_object"] is False for node in sites(result, "class"))
    assert not sites(result, "metaobject")


@pytest.mark.parametrize("name", ["ÅQTEST_MAIN", "QTEST_MAINÅ", r"\u0041QTEST_MAIN", r"QTEST_MAIN\u0041"])
def test_req_qml022_ac06_launcher_fragment_remains_ordinary_identifier(tmp_path, name):
    """Complete raw UTF8/UCN identifiers cannot become launcher candidates."""
    result = analysis(tmp_path, {"checks.cpp": '#include <QTest>\nvoid ' + name + '(int){} void run(){' + name + '(1);}'})
    assert not sites(result, "test_launcher")
    target = next(node["id"] for node in result["nodes"] if node["label"] == name + '()')
    assert any(edge.get("relation") == "calls" and edge["target"] == target for edge in result["edges"])


def test_req_qml022_ac06_locally_undefined_launcher_stays_an_ordinary_declared_call(tmp_path):
    """Source replacement/ordinary binding cannot acquire implicit framework semantics."""
    result = analysis(tmp_path, {"checks.cpp": '#include <QTest>\n#undef QTEST_MAIN\nvoid QTEST_MAIN(int){} void run(){QTEST_MAIN(1);}'})
    assert not sites(result, "test_launcher")
