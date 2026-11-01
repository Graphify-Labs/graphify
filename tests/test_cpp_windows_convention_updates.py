"""INC-QML-92: source convention views survive real cache/update/publication paths."""
from __future__ import annotations

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def _source(name="callback"):
    return ('#include <QObject>\n#include <qt_windows.h>\n'
            'class Anchor:public QObject{Q_OBJECT};\n'
            f'BOOL CALLBACK {name}(int value){{return value;}}\n'
            f'void invoke(){{{name}(1);}}\n').encode()


def _functions(graph, name):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("label") == name + "()" and data.get("metadata", {}).get("cpp_function")}


def test_req_qml022_ac06_convention_source_proof_matches_cache_and_export_reload(tmp_path):
    """Durable source proof refers to original bytes, never an SDK expansion or copied AST view."""
    path = tmp_path / "callbacks.cpp"
    source = _source()
    path.write_bytes(source)
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and not cold.get("qt_failures")
    graph = build_from_json(cold, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = load_node_link_graph(output)
    (callback,) = _functions(reloaded, "callback").values()
    span = callback["metadata"]["cpp_function"]["span"]
    assert source[span["start_byte"]:span["end_byte"]] == b"BOOL CALLBACK callback(int value){return value;}"
    assert callback["metadata"]["cpp_function"]["min_args"] == 1


def test_req_qml022_ac06_convention_source_edit_removes_stale_callable_and_matches_full(tmp_path):
    """A real watch update replaces names/calls, preserves unrelated facts, and is idempotent."""
    path = tmp_path / "callbacks.cpp"
    path.write_bytes(_source())
    (tmp_path / "keep.py").write_text("def retained():return 1\n")
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    initial = published(tmp_path)
    old = set(_functions(initial, "callback"))
    python_nodes = {identity: data for identity, data in initial.nodes(data=True) if data.get("source_file") == "keep.py"}
    path.write_bytes(_source("replacement"))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    changed = published(tmp_path)
    assert old.isdisjoint(changed) and len(_functions(changed, "replacement")) == 1
    assert {identity: data for identity, data in changed.nodes(data=True) if data.get("source_file") == "keep.py"} == python_nodes
    compare_clean(tmp_path)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == normalized(changed)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_rejected_convention_repair_retains_products_and_recovers(tmp_path, force):
    """Removing SDK authority rejects source before graph/manifest/report/Qt-state replacement."""
    path = tmp_path / "callbacks.cpp"
    original = _source()
    path.write_bytes(original)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    output = tmp_path / "graphify-out"
    (output / "report.md").write_bytes(b"Previously accepted convention source report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (output / name).read_bytes() for name in names}
    path.write_bytes(original.replace(b"#include <qt_windows.h>", b"#include <unproven_windows.h>"))
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (output / name).read_bytes() for name in names} == prior
    path.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(_functions(published(tmp_path), "callback")) == 1
    compare_clean(tmp_path)
    accepted = (output / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (output / "graph.json").read_bytes() == accepted
