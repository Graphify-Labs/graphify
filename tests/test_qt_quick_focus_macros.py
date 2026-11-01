"""INC-QML-82: documented QuickTest focus assertions provide source facts only."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.qt_external_singleton_helpers import sources
from tests.test_qt_cmake_mutation_updates import compare_clean, published
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_external_singleton_helpers import SETUP, LOAD, analyzed, binding_edges, setup_metadata


@pytest.mark.parametrize("name", ["QTRY_VERIFY_ACTIVE_FOCUS", "QVERIFY_ACTIVE_FOCUS"])
def test_req_qml022_ac03_quick_focus_assertion_keeps_source_and_genuine_argument_call(tmp_path, name):
    """SDK source syntax preserves nested actual calls without claiming focus or execution."""
    result = analysis(tmp_path, {"focus.cpp": '#include <QtQuickTest>\nQQuickItem* item(){return nullptr;} void run(){' + name + '(item());}'})
    assertion = sites(result, "test_assertion")
    assert len(assertion) == 1
    md = qt_metadata(assertion[0])
    assert md["mechanism"] == name and md["framework"] == "qt_quick_test"
    assert md["status"] == "source_only" and md["runtime_status"] == "unverified"
    assert (md.get("repeated_evaluation") is True) == name.startswith("QTRY_")
    assert "repeated_evaluation" in md or md["evaluation_status"] == "unverified"
    target = next(node["id"] for node in result["nodes"] if node["label"] == "item()")
    assert any(edge.get("relation") == "calls" and edge["target"] == target for edge in result["edges"])


def test_req_qml022_ac05_active_focus_retry_does_not_prove_single_external_setup(tmp_path):
    """The actual valid item expression can repeat the SDK setter before returning an item."""
    source = '#include <QtQuickTest>\nvoid boot(QQuickItem* item){Service singleton; QQmlApplicationEngine engine; '
    result = analyzed(tmp_path, source + 'QTRY_VERIFY_ACTIVE_FOCUS((' + SETUP[:-1] + ',item));' + LOAD + '}')
    assert not binding_edges(result)
    assert setup_metadata(result)["api_supported"] is False


def test_req_qml022_ac05_undefined_focus_macro_name_keeps_ordinary_function_call_control(tmp_path):
    """An explicit source replacement has no QuickTest assertion/retry authority."""
    source = '#include <QtQuickTest>\n#undef QTRY_VERIFY_ACTIVE_FOCUS\nvoid QTRY_VERIFY_ACTIVE_FOCUS(QQuickItem*);\nvoid boot(QQuickItem* item){Service singleton; QQmlApplicationEngine engine; '
    result = analyzed(tmp_path, source + 'QTRY_VERIFY_ACTIVE_FOCUS((' + SETUP[:-1] + ',item));' + LOAD + '}')
    assert len(binding_edges(result)) == 3
    assert not sites(result, "test_assertion")


@pytest.mark.parametrize("statement", ["QTRY_VERIFY_ACTIVE_FOCUS();", "QVERIFY_ACTIVE_FOCUS(item,other);",
                                         "return QTRY_VERIFY_ACTIVE_FOCUS(item);", "sizeof(QVERIFY_ACTIVE_FOCUS(item));"])
def test_req_qml022_ac06_focus_assertion_bad_arity_scope_does_not_become_success(tmp_path, statement):
    """Only a standalone callable assertion with the official one argument is admitted."""
    path = tmp_path / "focus.cpp"
    path.write_text('#include <QtQuickTest>\nvoid run(){' + statement + '}', encoding="utf-8")
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path)
    assert error.value.code == "QT_CPP_SYNTAX"


def test_req_qml022_ac06_focus_rewrite_retires_singleton_edges_and_rejected_write_recovers(tmp_path):
    """Real source mutation removes stale setup proof; malformed retry retains products."""
    body = '#include <QtQuickTest>\nvoid boot(QQuickItem* item){Service singleton; QQmlApplicationEngine engine; ' + SETUP + LOAD + '}'
    for name, source in sources(body).items():
        (tmp_path / name).write_bytes(source.encode())
    path = tmp_path / "main.cpp"
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert len([edge for _, _, edge in published(tmp_path).edges(data=True)
                if edge.get("context", "").startswith("qt_external_singleton_")]) == 3
    changed = body.replace(SETUP, 'QTRY_VERIFY_ACTIVE_FOCUS((' + SETUP[:-1] + ',item));')
    path.write_bytes(changed.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not [edge for _, _, edge in published(tmp_path).edges(data=True)
                if edge.get("context", "").startswith("qt_external_singleton_")]
    compare_clean(tmp_path)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted focus assertion source report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(changed.replace('QTRY_VERIFY_ACTIVE_FOCUS((', 'QTRY_VERIFY_ACTIVE_FOCUS(extra,(').encode())
    assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(changed.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
