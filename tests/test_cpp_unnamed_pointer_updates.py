"""INC-QML-83: original nullable-parameter facts obey retained graph transactions."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

SOURCE = '''#include <QObject>
class Owner:public QObject {Q_OBJECT public:
 Q_INVOKABLE void accept(QObject* = nullptr) {}
};
'''


def member(root):
    return next(qt_metadata(node) for _, node in published(root).nodes(data=True)
                if qt_metadata(node).get("kind") == "member" and qt_metadata(node).get("raw_name") == "accept")


def test_req_qml022_ac06_unnamed_pointer_cold_warm_type_change_matches_clean(tmp_path):
    """An unchanged named scope retains its real pointer type through cache and source edits."""
    path = tmp_path / "owner.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert member(tmp_path)["parameter_types"] == ["QObject*"] and member(tmp_path)["parameter_names"] == [""]
    before = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    path.write_bytes(SOURCE.replace("QObject* = nullptr", "const QObject* = nullptr").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert member(tmp_path)["parameter_types"] == ["const QObject*"]
    assert member(tmp_path)["parameter_names"] == [""]
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_rejected_unnamed_pointer_source_retains_products_and_recovers(tmp_path, force):
    """Unadmitted compound/malformed syntax cannot replace a valid previous declaration graph."""
    path = tmp_path / "owner.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted unnamed pointer report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.replace("QObject* = nullptr", "QObject** = nullptr").encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert member(tmp_path)["parameter_types"] == ["QObject*"]
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
