"""INC118: source-only helper calls survive cache, real writes and incremental refresh."""
from __future__ import annotations

import errno

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_anonymous_helper_calls import helper_calls, produce, source
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def calls(graph):
    targets = {identity for identity, data in graph.nodes(data=True)
               if data.get("source_file") == "panel.cpp" and data.get("metadata", {}).get("cpp_function")}
    return [data for left, right, data in graph.edges(data=True)
            if data.get("relation") == "calls" and (left in targets or right in targets)]


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_anonymous_direct_failed_replace_retains_and_recovers(tmp_path, monkeypatch, force):
    """Real serializer replacement failure retains the accepted helper edge until recovery."""
    initial = produce(tmp_path, source().encode(), "direct")
    assert len(helper_calls(initial)) == 1
    path = tmp_path / "accepted.json"
    assert to_json(build_from_json(initial, root=tmp_path), {}, str(path), force=True)
    before = path.read_bytes()
    current = produce(tmp_path, source("shadow").encode(), "direct")
    assert not helper_calls(current)
    graph = build_from_json(current, root=tmp_path)
    with publication_fault(path, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(graph, {}, str(path), force=force)
            assert failure.value.errno == errno.EIO and path.read_bytes() == before
        assert fault.hits >= 2
    assert to_json(graph, {}, str(path), force=force)
    accepted = path.read_bytes()
    assert accepted != before
    assert to_json(graph, {}, str(path), force=force) and path.read_bytes() == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_anonymous_source_qml_metadata_updates_replay_and_retain_on_failure(tmp_path, monkeypatch, operation):
    """Each real update owner preserves original proof and removes stale edges only after commit."""
    path = tmp_path / "panel.cpp"
    raw = source("named").encode()
    path.write_bytes(raw)
    qml = tmp_path / "Main.qml"
    qml.write_bytes(b"import QtQuick\nItem {property int value: 1}\n")
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_bytes(b"qt_add_qml_module(app URI Public.Helpers VERSION 1.0 QML_FILES Main.qml SOURCES panel.cpp)\n")
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    for changed, old, new in [(qml, b"value: 1", b"value: 2"), (cmake, b"VERSION 1.0", b"VERSION 1.1")]:
        changed.write_bytes(changed.read_bytes().replace(old, new))
        current = run(tmp_path, monkeypatch, operation, [changed])
        assert len(calls(current)) == 1 and path.read_bytes() == raw
        assert full_fields(current) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    before = products(tmp_path)
    path.write_bytes(source("shadow").encode())
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == before
        assert fault.hits >= 2
    shadowed = run(tmp_path, monkeypatch, operation, [path])
    assert not calls(shadowed)
    path.write_bytes(raw)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert len(calls(recovered)) == 1 and unrelated(recovered) == unrelated(initial)
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    before = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == before
