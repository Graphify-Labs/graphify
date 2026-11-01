"""INC-QML-86: optional source arity survives cache and retained graph updates."""
from __future__ import annotations

import pytest

from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, published

SOURCE = '''#include <QObject>
template<class T>struct Box{};
class Marker:public QObject{Q_OBJECT};
void f(Box<int> value={}){}
void run(){f();}
'''


def target(root):
    return next((identity, node) for identity, node in published(root).nodes(data=True)
                if node.get("label") == "f()" and node.get("metadata", {}).get("cpp_function"))


def calls(root, identity):
    return [edge for _, _, edge in published(root).edges(data=True)
            if edge.get("relation") == "calls" and edge.get("_tgt") == identity]


def test_req_qml022_ac06_empty_default_cold_warm_required_transition_matches_clean(tmp_path):
    """Required/optional source edits replace stale call authority, never a default guess."""
    path = tmp_path / "defaults.cpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    identity, node = target(tmp_path)
    original = node["metadata"]["cpp_function"]
    assert original["min_args"] == 0 and calls(tmp_path, identity)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert target(tmp_path)[1]["metadata"]["cpp_function"] == original
    path.write_bytes(SOURCE.replace("value={}", "value").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    identity, node = target(tmp_path)
    assert node["metadata"]["cpp_function"]["min_args"] == 1
    assert node["metadata"]["cpp_function"]["erased_default_parameters"] == []
    assert not calls(tmp_path, identity)
    compare_clean(tmp_path)
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert target(tmp_path)[1]["metadata"]["cpp_function"]["min_args"] == 0
    assert calls(tmp_path, target(tmp_path)[0])
    compare_clean(tmp_path)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_invalid_empty_default_owner_retains_graph_then_recovers(tmp_path, force):
    """An invalid containing declaration cannot be laundered into optional call authority."""
    path = tmp_path / "defaults.cpp"
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted optional-arity report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.replace("void f(Box<int> value={}){}", "void f(Box<int> value={}) @;").encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert calls(tmp_path, target(tmp_path)[0])
    compare_clean(tmp_path)
    accepted = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == accepted
