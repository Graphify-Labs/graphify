"""INC-QML-85: composed source adapters retain whole-file Qt update safety."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, published

SOURCE = '''#include <QTest>
class Owner{public:int value;};
class Checks{public:int Owner::*data;void run(){QFETCH(int,value);}};
'''


def test_req_qml022_ac06_composed_adapters_cache_stale_cleanup_and_rejection_recovery(tmp_path):
    """Local proofs compose; an unrelated syntax failure still retains the accepted graph."""
    path = tmp_path / "checks.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    field = next(node for _, node in graph.nodes(data=True) if node.get("label") == "data")
    assert field["metadata"]["cpp_declarator"]["member_pointer"]["owner_spelling"] == "Owner"
    assert any(qt_metadata(node).get("kind") == "test_data" for _, node in graph.nodes(data=True))
    accepted = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == accepted
    path.write_bytes(SOURCE.replace("int Owner::*data;", "").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not any(node.get("label") == "data" for _, node in published(tmp_path).nodes(data=True))
    compare_clean(tmp_path)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted composed source report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.encode() + b"void unfinished(")
    assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
