"""INC-QML-109: lexical class edits retire persisted calls and recover after EIO."""
from __future__ import annotations

import errno

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from tests.cpp_nested_helpers import nested_source, produce, source_call_edges
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def calls(graph):
    # Legacy generic undirected publication does not promise call direction;
    # source identity and the complete source fact distinguish this endpoint.
    targets = {identity for identity, data in graph.nodes(data=True)
               if data.get("source_file") == "nested.cpp" and data.get("metadata", {}).get("cpp_function")}
    return [data for source, target, data in graph.edges(data=True)
            if data.get("relation") == "calls"
            and (source in targets or target in targets)]


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_nested_direct_export_failure_preserves_then_replaces_accepted_calls(tmp_path, monkeypatch, force):
    """Real direct graph replacement failure retains bytes; recovery publishes the changed lookup."""
    initial = produce(tmp_path, nested_source())
    assert len(source_call_edges(initial)) == 1
    output = tmp_path / "direct.json"
    assert to_json(build_from_json(initial, root=tmp_path), {}, str(output), force=True)
    accepted = output.read_bytes()
    current = produce(tmp_path, nested_source(shadow="static void (*helper)();"))
    assert not source_call_edges(current)
    graph = build_from_json(current, root=tmp_path)
    with publication_fault(output, "replace", monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(graph, {}, str(output), force=force)
            assert failure.value.errno == errno.EIO and output.read_bytes() == accepted
        assert fault.hits >= 2
    assert to_json(graph, {}, str(output), force=force)
    updated = output.read_bytes()
    assert updated != accepted
    assert to_json(graph, {}, str(output), force=force) and output.read_bytes() == updated


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_nested_parent_edit_retains_on_failure_then_retires_and_recovers(tmp_path, monkeypatch, operation):
    """Actual cache/update owners replay parent changes and preserve every source/evidence attribute."""
    path = tmp_path / "nested.cpp"
    initial_raw = nested_source(namespace="Public")
    path.write_bytes(initial_raw)
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert len(calls(initial)) == 1
    accepted = products(tmp_path)
    shadowed_raw = nested_source(namespace="Public", shadow="static void (*helper)();")
    path.write_bytes(shadowed_raw)
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    shadowed = run(tmp_path, monkeypatch, operation, [path])
    assert not calls(shadowed) and path.read_bytes() == shadowed_raw
    assert full_fields(shadowed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(shadowed) == unrelated(initial)
    path.write_bytes(initial_raw)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert len(calls(recovered)) == 1 and path.read_bytes() == initial_raw
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    before = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == before
