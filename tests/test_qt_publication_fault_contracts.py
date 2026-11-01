"""INC-QML-102: actual platform denial, scoped EIO, and POSIX overwrite controls."""
from __future__ import annotations

import errno
import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import write_text_atomic
from graphify.watch import _rebuild_code
from tests.qt_external_singleton_helpers import sources
from tests.qt_publication_faults import publication_fault
from tests.test_qt_cmake_mutation_updates import published
from tests.test_qt_test_updates import SOURCE


def test_req_qml022_ac06_graph_replace_eio_delegates_and_restores_after_exception(tmp_path, monkeypatch):
    """Only the graph target fails; real unrelated replacement and later retry succeed."""
    graph, stage = tmp_path / "graph.json", tmp_path / "candidate.json"
    graph.write_bytes(b"accepted")
    stage.write_bytes(b"candidate")
    original_replace = os.replace
    with pytest.raises(RuntimeError, match="test-owned failure after observations"):
        with publication_fault(graph, "replace", monkeypatch) as fault:
            unrelated, moved = tmp_path / "source.txt", tmp_path / "moved.txt"
            unrelated.write_bytes(b"delegated")
            os.replace(unrelated, moved)
            assert moved.read_bytes() == b"delegated" and not unrelated.exists()
            for _ in range(2):
                with pytest.raises(OSError) as failure:
                    os.replace(stage, graph)
                assert failure.value.errno == errno.EIO
                assert graph.read_bytes() == b"accepted" and stage.read_bytes() == b"candidate"
            assert fault.qualified and fault.hits == 2
            raise RuntimeError("test-owned failure after observations")
    assert os.replace is original_replace
    os.replace(stage, graph)
    assert graph.read_bytes() == b"candidate" and not stage.exists()


def test_req_qml022_ac06_readonly_fault_qualifies_actual_denial_and_restores_modes(tmp_path, monkeypatch):
    """The real atomic writer fails under qualified native permissions, then recovers."""
    graph = tmp_path / "graph.json"
    graph.write_bytes(b"accepted")
    modes = graph.stat().st_mode, tmp_path.stat().st_mode
    with publication_fault(graph, "readonly", monkeypatch) as fault:
        assert fault.qualified
        with pytest.raises(PermissionError):
            write_text_atomic(graph, "candidate")
        assert graph.read_bytes() == b"accepted"
    assert (graph.stat().st_mode, tmp_path.stat().st_mode) == modes
    assert set(tmp_path.iterdir()) == {graph}
    write_text_atomic(graph, "candidate")
    assert graph.read_bytes() == b"candidate"


@pytest.mark.skipif(os.name == "nt", reason="POSIX writable-parent overwrite control")
def test_req_qml022_ac06_posix_readonly_file_alone_allows_real_atomic_replace(tmp_path):
    """File-only mode cannot stand in for a directory publication-denial fixture."""
    graph = tmp_path / "graph.json"
    graph.write_bytes(b"accepted")
    original, parent_mode = graph.stat().st_mode, tmp_path.stat().st_mode
    graph.chmod(stat.S_IREAD)
    try:
        write_text_atomic(graph, "candidate")
        assert graph.read_bytes() == b"candidate"
        assert tmp_path.stat().st_mode == parent_mode
        assert set(tmp_path.iterdir()) == {graph}
    finally:
        graph.chmod(original)


@pytest.mark.skipif(os.name == "nt", reason="POSIX writable-parent publication control")
@pytest.mark.parametrize("mechanism", ["external_singleton", "qt_test"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_posix_readonly_file_pipeline_accepts_valid_update(tmp_path, mechanism, force):
    """Both exact failed hosted mechanisms publish under file-only POSIX readonly mode."""
    if mechanism == "external_singleton":
        for name, source in sources().items():
            (tmp_path / name).write_bytes(source.encode())
        source = tmp_path / "main.cpp"
        original = source.read_bytes()
        changed = original.replace(b'"State"', b'"Missing"')
    else:
        source = tmp_path / "checks.hpp"
        original = SOURCE.encode()
        source.write_bytes(original)
        changed = original.replace(b"state", b"value")
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = tmp_path / "graphify-out/graph.json"
    accepted, mode = graph.read_bytes(), graph.stat().st_mode
    directory_mode = graph.parent.stat().st_mode
    source.write_bytes(changed)
    graph.chmod(stat.S_IREAD)
    try:
        assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True,
                             acquire_lock=False, force=force)
        assert graph.read_bytes() != accepted and graph.parent.stat().st_mode == directory_mode
        result = published(tmp_path)
        if mechanism == "external_singleton":
            assert not any(data.get("context", "").startswith("qt_external_singleton_")
                           for _, _, data in result.edges(data=True))
        else:
            assert len([node for _, node in result.nodes(data=True)
                        if qt_metadata(node).get("kind") in {"test_data", "test_assertion"}]) == 2
    finally:
        graph.chmod(mode)
    source.write_bytes(original)
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    restored = graph.read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert graph.read_bytes() == restored
