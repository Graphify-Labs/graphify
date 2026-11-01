"""INC-QML-68: external setup source changes retain transaction/cache boundaries."""
from __future__ import annotations

import pytest

from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.qt_external_singleton_helpers import HEADER, LOAD, SETUP, sources
from tests.qt_publication_faults import publication_fault
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published


def _project(root):
    for name, source in sources().items():
        (root / name).write_bytes(source.encode())
    return root / "main.cpp"


def _bindings(root):
    graph = published(root)
    return [edge for _, _, edge in graph.edges(data=True)
            if edge.get("context", "").startswith("qt_external_singleton_")]


def test_req_qml022_ac06_external_setup_cold_warm_source_header_edits_match_clean(tmp_path):
    """C++-only and header-only changes retire stale relationships in unchanged consumers."""
    path = _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert len(_bindings(tmp_path)) == 3
    baseline = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    original = path.read_bytes()
    path.write_bytes(original.replace(b'"State"', b'"Missing"'))
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not _bindings(tmp_path)
    compare_clean(tmp_path)
    path.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(_bindings(tmp_path)) == 3
    header = tmp_path / "backend.hpp"
    header.write_bytes(HEADER.replace("QML_SINGLETON", "").encode())
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert not _bindings(tmp_path)
    compare_clean(tmp_path)
    header.write_bytes(HEADER.encode())
    assert _rebuild_code(tmp_path, changed_paths=[header], no_cluster=True, acquire_lock=False)
    assert len(_bindings(tmp_path)) == 3
    compare_clean(tmp_path)


@pytest.mark.parametrize("failure", ["syntax", "readonly", "replace"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_external_setup_failure_retains_products_and_recovers(tmp_path, monkeypatch, capsys, failure, force):
    """Actual rejected parsing/replacement preserves products, then repair/repeat commits."""
    path = _project(tmp_path)
    original = path.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted external-singleton report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    graph_path = out / "graph.json"
    if failure == "syntax":
        path.write_bytes(b"void boot() { QQmlApplicationEngine engine; engine.setExternalSingletonInstance(")
    else:
        path.write_bytes(original.replace(b'"State"', b'"Missing"'))

    def rejected_attempts():
        for _ in range(2):
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True,
                                     acquire_lock=False, force=force)
            assert {name: (out / name).read_bytes() for name in names} == prior
            expected = "QML_GRAPH_PRESERVED" if failure == "syntax" else "GRAPH_PUBLICATION_FAILED"
            assert expected in capsys.readouterr().out

    if failure == "syntax":
        rejected_attempts()
    else:
        with publication_fault(graph_path, failure, monkeypatch) as fault:
            assert fault.qualified
            rejected_attempts()
            if failure == "replace":
                assert fault.hits >= 2
    path.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(_bindings(tmp_path)) == 3
    compare_clean(tmp_path)
    accepted = graph_path.read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert graph_path.read_bytes() == accepted


@pytest.mark.parametrize("effect", ["conditional_reset", "helper", "noexcept"])
def test_req_qml022_ac06_external_interference_removes_stale_edges_and_matches_full(tmp_path, effect):
    """Previously accepted source edges retire when a new source effect invalidates ordering."""
    path = _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    assert len(_bindings(tmp_path)) == 3
    source = path.read_text()
    if effect == "conditional_reset":
        source = source.replace("void boot()", "void boot(bool ready)").replace(LOAD, "if(ready) { engine.clearSingletons(); } " + LOAD)
    elif effect == "helper":
        source = "void mutate(QQmlApplicationEngine&);\n" + source.replace(LOAD, "mutate(engine); " + LOAD)
    else:
        source = source.replace(SETUP, "bool ok = noexcept(" + SETUP[:-1] + ");")
    path.write_bytes(source.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert not _bindings(tmp_path)
    compare_clean(tmp_path)
    accepted = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == accepted
