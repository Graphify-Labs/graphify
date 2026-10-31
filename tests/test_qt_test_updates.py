"""INC-QML-75: source-only QtTest records obey cache/publication transactions."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.qt_cpp_test_helpers import collect, facts
from tests.qt_external_singleton_helpers import LOAD, SETUP, sources
from tests.qt_publication_faults import publication_fault
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

SOURCE = '''#include <QTest>
class Checks { public: void run(){ QFETCH(int, state); QTRY_COMPARE(state, 2); } };
'''


def _test_facts(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") in {"test_data", "test_assertion"}}


def test_req_qml022_ac06_direct_qt_overlay_borrows_canonical_owners_without_mutation(tmp_path):
    """The public overlay producer creates original records independently of facade reuse."""
    result = collect(tmp_path, {"checks.hpp": SOURCE})
    assert len(facts(result, "test_data")) == len(facts(result, "test_assertion")) == 1
    generic_ids = {node["id"] for node in result["nodes"] if not qt_metadata(node)}
    assert all(qt_metadata(node)["owner_id"] in generic_ids
               for kind in ("test_data", "test_assertion") for node in facts(result, kind))


def test_req_qml022_ac06_qt_test_cold_warm_incremental_cleanup_matches_full(tmp_path):
    """Original typed spans and source facts survive cache and retire on source edits."""
    path = tmp_path / "checks.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    before, original = normalized(published(tmp_path)), _test_facts(tmp_path)
    assert len(original) == 2
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before and _test_facts(tmp_path) == original
    path.write_bytes(SOURCE.replace("QFETCH(int, state);", "int state;").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {item["kind"] for item in _test_facts(tmp_path).values()} == {"test_assertion"}
    assert not (set(original) - set(_test_facts(tmp_path))) & set(published(tmp_path))
    compare_clean(tmp_path)
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert _test_facts(tmp_path) == original
    compare_clean(tmp_path)


@pytest.mark.parametrize("failure", ["syntax", "readonly", "replace"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_qt_test_failure_retains_graph_and_recovers(tmp_path, monkeypatch, capsys, failure, force):
    """Actual replacement/parse rejection retains every product, then repair/repeat succeeds."""
    path = tmp_path / "checks.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted QtTest source report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    destination = out / "graph.json"
    path.write_bytes(SOURCE.replace("QFETCH(int, state);", "QFETCH(int);").encode() if failure == "syntax"
                     else SOURCE.replace("state", "value").encode())

    def rejected_attempts():
        for _ in range(2):
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
            assert {name: (out / name).read_bytes() for name in names} == prior
            expected = "QML_GRAPH_PRESERVED" if failure == "syntax" else "GRAPH_PUBLICATION_FAILED"
            assert expected in capsys.readouterr().out

    if failure == "syntax":
        rejected_attempts()
    else:
        with publication_fault(destination, failure, monkeypatch) as fault:
            assert fault.qualified
            rejected_attempts()
            if failure == "replace":
                assert fault.hits >= 2
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(_test_facts(tmp_path)) == 2
    compare_clean(tmp_path)
    accepted = destination.read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert destination.read_bytes() == accepted


def test_req_qml022_ac06_retry_mutation_removes_singleton_binding_and_matches_full(tmp_path):
    """A new retry source context invalidates previously accepted unique setup proof."""
    for name, source in sources().items():
        (tmp_path / name).write_bytes(source.encode())
    path = tmp_path / "main.cpp"
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert len([edge for _, _, edge in published(tmp_path).edges(data=True)
                if edge.get("context", "").startswith("qt_external_singleton_")]) == 3
    source = '#include <QTest>\n' + path.read_text().replace(SETUP, 'QTRY_COMPARE(' + SETUP[:-1] + ',true);')
    assert LOAD in source
    path.write_bytes(source.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not [edge for _, _, edge in published(tmp_path).edges(data=True)
                if edge.get("context", "").startswith("qt_external_singleton_")]
    compare_clean(tmp_path)
