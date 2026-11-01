"""INC-QML-72: member-pointer metadata survives real cache/update transactions."""
from __future__ import annotations

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

SOURCE = '''class Owner : public QObject { Q_OBJECT public: int value; };
class Holder : public QObject { Q_OBJECT public:
 int Owner::*memberPointer;
 void (Owner::*memberFunction)(int) const;
};
'''


def _fields(graph):
    return {node["label"]: (nid, node["metadata"]["cpp_declarator"])
            for nid, node in graph.nodes(data=True)
            if node.get("metadata", {}).get("cpp_declarator", {}).get("member_pointer")}


def test_req_qml022_ac06_member_pointer_cold_warm_incremental_cleanup_matches_full(tmp_path):
    """Source-only qualification survives cache, and removed declarations leave no stale facts."""
    path = tmp_path / "members.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    fields = _fields(graph)
    assert set(fields) == {"memberPointer", "memberFunction"}
    assert fields["memberPointer"][1]["member_pointer"]["owner_spelling"] == "Owner"
    before = normalized(graph)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    assert _fields(published(tmp_path)) == fields
    path.write_bytes(SOURCE.replace(" int Owner::*memberPointer;\n", "").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    assert set(_fields(graph)) == {"memberFunction"}
    assert fields["memberPointer"][0] not in graph
    compare_clean(tmp_path)
    clean = extract(collect_files(tmp_path, root=tmp_path), root=tmp_path,
                    cache_root=tmp_path / "pointer-clean-cache", parallel=False)
    assert _fields(graph) == _fields(build_from_json(clean, root=tmp_path))


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_member_pointer_rejection_retains_products_then_repairs(tmp_path, force):
    """Malformed pointer source cannot replace the last accepted graph/cache checkpoint."""
    path = tmp_path / "members.hpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted member-pointer report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.replace("void (Owner::*memberFunction)(int) const;", "void (Owner::*memberFunction)(int;").encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True,
                                 acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert set(_fields(published(tmp_path))) == {"memberPointer", "memberFunction"}
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
