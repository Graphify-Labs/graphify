"""INC-QML-75: QtTest source compatibility does not grant runtime native authority."""
from __future__ import annotations

import pytest

from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_external_singleton_helpers import LOAD, SETUP, analyzed, binding_edges, setup_metadata


@pytest.mark.parametrize("mechanism", ["QFETCH", "QFETCH_GLOBAL"])
def test_req_qml022_ac03_data_type_is_opaque_even_when_original_prefix_names_sdk_alias(tmp_path, mechanism):
    """The actual ordinary QFE alias stays useful; a synthetic binder never borrows it."""
    result = analysis(tmp_path, {"checks.cpp": f'''#include <QTest>
using QFE = QQmlApplicationEngine;
void run(){{ QFE actual; actual.load("Main.qml"); {mechanism}(QQmlApplicationEngine, fetched); fetched.load("Main.qml"); }}
'''})
    assert len(sites(result, "test_data")) == 1
    loads = [qt_metadata(node) for node in sites(result, "qml_load")]
    assert len(loads) == 1 and loads[0]["receiver_reference"] == "actual"
    assert not sites(result, "context_binding")


def test_req_qml022_ac03_direct_sdk_include_in_a_literal_file_guard_is_accepted(tmp_path):
    """A proven whole-file guard is inclusion syntax, not an unknown feature branch."""
    result = analysis(tmp_path, {"checks.hpp": '''#ifndef PUBLIC_CHECKS_H
#define PUBLIC_CHECKS_H
#include <QtTest/QtTest>
class Checks { public: void run(){ QFETCH(int, value); QTRY_COMPARE_WITH_TIMEOUT(value, 3, 100); } };
#endif
'''})
    assert len(sites(result, "test_data")) == len(sites(result, "test_assertion")) == 1
    assert qt_metadata(sites(result, "test_assertion")[0])["mechanism"] == "QTRY_COMPARE_WITH_TIMEOUT"


@pytest.mark.parametrize("body", [
    'QTRY_COMPARE(engine.setExternalSingletonInstance("Public.Tools", "State", &singleton), true); ' + LOAD,
    SETUP + ' QTRY_COMPARE(engine.setExternalSingletonInstance("Public.Tools", "State", &singleton), true); ' + LOAD,
    SETUP + ' QTRY_COMPARE((engine.clearSingletons(), true), true); ' + LOAD,
    'QTRY_COMPARE(engine.singletonInstance("Public.Tools", "State"), nullptr); ' + SETUP + LOAD,
])
def test_req_qml022_ac05_retry_arguments_cannot_prove_unique_external_setup_order(tmp_path, body):
    """Actual nested API occurrences remain, while repeated evaluation blocks binding."""
    source = '#include <QTest>\nvoid boot(){ Service singleton; QQmlApplicationEngine engine; ' + body + ' }'
    result = analyzed(tmp_path, source)
    assert sites(result, "test_assertion") and sites(result, "external_singleton_setup")
    assert not binding_edges(result)


def test_req_qml022_ac05_opaque_test_column_cannot_be_external_singleton_engine(tmp_path):
    """Original SDK-looking payload/type aliases do not prove a runtime engine instance."""
    result = analyzed(tmp_path, '#include <QTest>\nusing QFE=QQmlApplicationEngine; void boot(){ Service singleton; QFETCH(QQmlApplicationEngine,engine); ' + SETUP + LOAD + ' }')
    assert sites(result, "test_data")
    assert not sites(result, "external_singleton_setup") and not binding_edges(result)


def test_req_qml022_ac03_macro_payload_does_not_reenter_an_outer_annotation(tmp_path):
    """An outer stringifying Qt annotation owns all nested familiar spellings."""
    result = analysis(tmp_path, {"native.hpp": '#include <QTest>\nclass Native { Q_GADGET QML_NAMED_ELEMENT(QFETCH) public: int value; };'})
    assert not sites(result, "test_data") and not sites(result, "test_assertion")
    assert qt_metadata(sites(result, "registration")[0])["raw_name"] == "QFETCH"


@pytest.mark.parametrize("statement", ["QFETCH(void, x);", "QFETCH(int, x)",
                                         "QTRY_COMPARE(1, 1, 2);", "if (QTRY_COMPARE(1,1)) {}",
                                         "obj.QFETCH(int, x);", "Scope::QFETCH(int, x);"])
def test_req_qml022_ac03_unsupported_qt_test_shapes_do_not_become_success(tmp_path, statement):
    """Malformed/unproven grammar retains the existing explicit syntax diagnostic."""
    path = tmp_path / "checks.hpp"
    path.write_text('#include <QTest>\nvoid run(bool ready){' + statement + '}', encoding="utf-8")
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert result["qml_failures"] == [{"code": "QT_CPP_SYNTAX", "source_file": "checks.hpp"}]
    assert not sites(result, "test_data") and not sites(result, "test_assertion")


def test_req_qml022_ac03_override_does_not_hide_genuine_ordinary_call(tmp_path):
    """An explicitly replaced macro can retain its ordinary typed function call."""
    result = analysis(tmp_path, {"checks.cpp": '#include <QTest>\n#undef QTRY_COMPARE\nvoid QTRY_COMPARE(int,int){} void run(){QTRY_COMPARE(1,2);}'})
    assert not sites(result, "test_assertion")
    target = next(node["id"] for node in result["nodes"] if node["label"] == "QTRY_COMPARE()")
    assert any(edge["relation"] == "calls" and edge["target"] == target for edge in result["edges"])


@pytest.mark.parametrize("name,args", [
    (f"QTRY_COMPARE_{comparison}{suffix}", "value, 2" + (", 100" if suffix else ""))
    for comparison in ("EQ", "NE", "LT", "LE", "GT", "GE") for suffix in ("", "_WITH_TIMEOUT")
] + [("QTRY_VERIFY", "value"), ("QTRY_VERIFY_WITH_TIMEOUT", "value, 100"),
     ("QTRY_VERIFY2", 'value, "message"'), ("QTRY_VERIFY2_WITH_TIMEOUT", 'value, "message", 100')])
def test_req_qml022_ac03_documented_retry_family_has_exact_source_only_arity(tmp_path, name, args):
    """Every selected official retry spelling retains only source/runtime-unknown facts."""
    result = analysis(tmp_path, {"checks.hpp": "#include <QTest>\nvoid run(){int value; " + name + "(" + args + ");}"})
    assertion = sites(result, "test_assertion")
    assert len(assertion) == 1 and qt_metadata(assertion[0])["mechanism"] == name
    assert qt_metadata(assertion[0])["runtime_status"] == "unverified"


@pytest.mark.parametrize("name,args", [("QTRY_COMPARE_EQ", ",true"), ("QTRY_VERIFY", ""),
                                         ("QTRY_VERIFY2_WITH_TIMEOUT", ',"waiting",100')])
def test_req_qml022_ac05_all_retry_mechanisms_reject_single_setup_authority(tmp_path, name, args):
    """A retry family variation cannot launder a repeated bool API into unique setup."""
    body = '#include <QTest>\nvoid boot(){Service singleton; QQmlApplicationEngine engine; '
    result = analyzed(tmp_path, body + name + '(' + SETUP[:-1] + args + ');' + LOAD + '}')
    assert not binding_edges(result)
    assert setup_metadata(result)["api_supported"] is False
