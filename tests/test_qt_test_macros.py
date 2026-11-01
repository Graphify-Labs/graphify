"""INC-QML-75: typed QtTest source is opaque data, never runtime/provider proof."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("header", ["QTest", "QtTest", "QtTest/QTest", "QtTest/QtTest"])
def test_req_qml022_ac03_qt_test_data_and_retry_keep_source_and_real_inner_calls(tmp_path, header):
    """Literal SDK context admits typed local data and retains actual expression calls."""
    path = tmp_path / "checks.hpp"
    source = (f'\ufeff#include <{header}>\r\n// café 雪\r\nint actual() {{ return 1; }} int expected() {{ return 1; }}\r\n'
              'class Checks { public: void dataDriven() {\r\n QFETCH(int, state);\r\n QTRY_COMPARE(actual(), expected());\r\n} };\r\n').encode()
    path.write_bytes(source)
    direct = extract_cpp(path)
    assert not direct.get("parse_errors")
    # The generic producer resolves local callees into edges; raw_calls carries
    # only its still-unresolved references, so inspect the durable endpoints.
    targets = {edge["target"] for edge in direct["edges"] if edge.get("relation") == "calls"}
    assert {node["label"] for node in direct["nodes"] if node["id"] in targets} >= {"actual()", "expected()"}
    assert not {"QFETCH", "QTRY_COMPARE"} & {call["callee"] for call in direct["raw_calls"]}
    unit = read_cpp(path, tmp_path)
    assert len(unit.qt_test_macros) == 2
    assert len(unit.source) == len(unit.parsed_source) and unit.source == source
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    data = sites(result, "test_data")[0]
    md = qt_metadata(data)
    assert md["raw_name"] == "state" and md["raw_type"] == "int"
    assert md["status"] == "source_only" and md["runtime_status"] == "unverified"
    assert source[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"QFETCH(int, state)"
    assert source[md["variable_span"]["start_byte"]:md["variable_span"]["end_byte"]] == b"state"
    assertion = sites(result, "test_assertion")[0]
    assert qt_metadata(assertion)["repeated_evaluation"] is True
    assert not [node for node in result["nodes"] if node["label"] == "state" and node.get("_callable")]
    graph = build_from_json(result, root=tmp_path, directed=True)
    destination = tmp_path / "proof.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert qt_metadata(loaded.nodes[data["id"]]) == md


def test_req_qml022_ac03_typed_qt_test_payload_cannot_grant_qobject_or_invokable_role(tmp_path):
    """Annotation-looking type arguments remain opaque under their actual outer macro."""
    result = analysis(tmp_path, {"checks.hpp": "#include <QTest>\nclass Checks { public: void run() { QFETCH(Q_OBJECT, state); } };"})
    assert all(not qt_metadata(node).get("source_q_object") for node in sites(result, "class"))
    assert not sites(result, "registration")
    assert all(qt_metadata(node).get("roles") == [] for node in sites(result, "member"))


@pytest.mark.parametrize("statement", ["QFETCH(int);", "QFETCH(int, state, extra);",
                                        "QFETCH(QMap<int,int>, state);", "QFETCH(int, 42);",
                                        "QTRY_COMPARE(1);", "QTRY_COMPARE_WITH_TIMEOUT(1, 1);",
                                        "sizeof(QTRY_COMPARE(1, 1));", "return QTRY_COMPARE(1, 1);"])
def test_req_qml022_ac03_invalid_or_nonstatement_qt_test_usage_is_explicit_failure(tmp_path, statement):
    """Macro arity follows preprocessing parentheses and cannot launder bad contexts."""
    path = tmp_path / "checks.hpp"
    path.write_bytes(("#include <QTest>\nvoid run() { " + statement + " }").encode())
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"


@pytest.mark.parametrize("prefix", ["", '#include "QTest"\n', "#if ENABLE_TESTS\n#include <QTest>\n#endif\n",
                                     "/*\n#include <QTest>\n*/\n", "#include TEST_FRAMEWORK\n"])
def test_req_qml022_ac03_unproven_qt_test_context_does_not_recover_typed_payload(tmp_path, prefix):
    """Unknown/quoted/conditional/transitive-only contexts need separate accepted evidence."""
    path = tmp_path / "checks.hpp"
    path.write_bytes((prefix + "void run() { QFETCH(int, state); }").encode())
    with pytest.raises(QtCppError):
        read_cpp(path, tmp_path)


def test_req_qml022_ac03_ordinary_overridden_qt_test_spelling_stays_an_ordinary_call(tmp_path):
    """An explicit undef and ordinary declaration do not acquire QtTest facts."""
    result = analysis(tmp_path, {"checks.hpp": "#include <QTest>\n#undef QTRY_COMPARE\nvoid QTRY_COMPARE(int,int) {} void run() { QTRY_COMPARE(1,2); }"})
    assert not sites(result, "test_assertion") and not sites(result, "test_data")


def test_req_qml022_ac03_fetched_binder_shadows_global_callback_without_provider_authority(tmp_path):
    """Opaque local data blocks global callable/type guesses in the normalized view."""
    source = '''#include <QTest>
using Handler = void(*)();
void callback() {}
class Checks { public: void run() { QFETCH(Handler, callback); callback(); } };
'''
    result = analysis(tmp_path, {"checks.hpp": source})
    data = sites(result, "test_data")[0]
    assert qt_metadata(data)["raw_name"] == "callback"
    target = [node["id"] for node in result["nodes"] if node.get("_callable") and node["label"].removesuffix("()") == "callback"][0]
    assert not [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge["target"] == target]
    assert not sites(result, "context_binding")
