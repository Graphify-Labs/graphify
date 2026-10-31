"""INC-QML-81: launcher source facts survive cache and real retained updates."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

SOURCE = '''#include "framework.hpp"
class Checks:public QObject{Q_OBJECT private slots:void run(){QFETCH(int,value);QTRY_COMPARE(value,1);}};
QTEST_MAIN(Checks)
#include "checks.moc"
'''


def project(root):
    (root / "framework.hpp").write_bytes(b"#include <QTest>\n")
    path = root / "checks.cpp"
    path.write_bytes(SOURCE.encode())
    return path


def launchers(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") == "test_launcher"}


def test_req_qml022_ac06_launcher_cold_warm_source_removal_matches_full(tmp_path):
    """Different/removed source launcher occurrences replace old facts and file links."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original, before = launchers(tmp_path), normalized(published(tmp_path))
    assert len(original) == 1
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    path.write_bytes(SOURCE.replace("QTEST_MAIN", "QTEST_GUILESS_MAIN").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {md["mechanism"] for md in launchers(tmp_path).values()} == {"QTEST_GUILESS_MAIN"}
    assert not set(original) & set(published(tmp_path))
    compare_clean(tmp_path)
    path.write_bytes(SOURCE.replace("QTEST_MAIN(Checks)", "").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not launchers(tmp_path)
    compare_clean(tmp_path)


@pytest.mark.parametrize("failure", ["arity", "header"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_launcher_syntax_context_rejection_retains_products_then_recovers(tmp_path, failure, force):
    """Invalid syntax or a missing SDK chain cannot replace a previously accepted graph."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted launcher source report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    changed = path if failure == "arity" else tmp_path / "framework.hpp"
    changed.write_bytes(SOURCE.replace("QTEST_MAIN(Checks)", "QTEST_MAIN(Checks,Other)").encode()
                        if failure == "arity" else b"// SDK context removed\n")
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[changed], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    (tmp_path / "framework.hpp").write_bytes(b"#include <QTest>\n")
    assert _rebuild_code(tmp_path, changed_paths=[changed], no_cluster=True, acquire_lock=False)
    assert len(launchers(tmp_path)) == 1
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[changed], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
