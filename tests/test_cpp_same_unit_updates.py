"""INC-QML-106: canonical source members survive real refresh and failed publication."""
from __future__ import annotations

import pytest

from graphify.extractors.cpp_member_identity import member_fact
from graphify.source_relationships import logical_endpoints
from graphify.watch import _rebuild_code
from tests.cpp_same_unit_helpers import project
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_qt_final_incremental_parity import manual_update, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def endpoint(graph):
    calls = [(*logical_endpoints(graph, a, b, data), data) for a, b, data in graph.edges(data=True)
             if data.get("context") == "qml_js_call"]
    if calls:
        assert len(calls) == 1
        assert member_fact(graph.nodes[calls[0][1]])["role"] == "declaration"
    return calls[0][1] if calls else None


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_same_unit_source_qml_metadata_updates_retire_and_retarget(tmp_path, monkeypatch, operation):
    """Independent source/module/QML edits remove stale bindings, then exact cold output agrees."""
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    old = endpoint(initial)
    assert old
    source.write_bytes(source.read_bytes().replace(b"run()", b"advance()"))
    renamed = run(tmp_path, monkeypatch, operation, [source])
    assert old not in renamed and endpoint(renamed) is None
    qml = tmp_path / "Main.qml"
    qml.write_bytes(qml.read_bytes().replace(b"run()", b"advance()"))
    repaired = run(tmp_path, monkeypatch, operation, [qml])
    new = endpoint(repaired)
    assert new and new != old
    assert full_fields(repaired) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    metadata = tmp_path / "CMakeLists.txt"
    metadata.write_bytes(metadata.read_bytes().replace(b"Public.SameUnit", b"Public.Retargeted"))
    unavailable = run(tmp_path, monkeypatch, operation, [metadata])
    assert endpoint(unavailable) is None and member_fact(unavailable.nodes[new])
    qml.write_bytes(qml.read_bytes().replace(b"Public.SameUnit", b"Public.Retargeted"))
    rebound = run(tmp_path, monkeypatch, operation, [qml])
    assert endpoint(rebound) == new
    assert unrelated(initial) == unrelated(rebound)
    assert full_fields(rebound) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [source, qml, metadata])
    assert products(tmp_path) == accepted


def rejected(root, monkeypatch, operation, source):
    if operation == "manual":
        with pytest.raises(SystemExit) as error:
            manual_update(root, monkeypatch)
        assert error.value.code == 1
    else:
        assert not _rebuild_code(root, changed_paths=[source], no_cluster=True, acquire_lock=False)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "replace"])
def test_req_qml022_ac06_same_unit_member_failure_retains_then_recovers(tmp_path, monkeypatch, capsys, operation, failure):
    """Actual parser rejection/EIO retains accepted products before unchanged valid-source retry."""
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    expected = endpoint(initial)
    assert expected
    accepted = products(tmp_path)
    valid = source.read_bytes().replace(b"void run();", b"void run();\nint added;")
    source.write_bytes(valid[:-2] if failure == "syntax" else valid)
    unchanged = source.read_bytes(), source.stat().st_mtime_ns
    if failure == "replace":
        with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
            for _ in range(2):
                rejected(tmp_path, monkeypatch, operation, source)
                assert products(tmp_path) == accepted
            assert fault.hits >= 2
    else:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, source)
            assert products(tmp_path) == accepted
    captured = capsys.readouterr()
    assert ("GRAPH_PUBLICATION_FAILED" if failure == "replace" else "QML_GRAPH_PRESERVED") in captured.out + captured.err
    if failure == "syntax":
        source.write_bytes(valid)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert endpoint(repaired) == expected and "definition_span" in repaired.nodes[expected]
    if failure == "replace":
        assert (source.read_bytes(), source.stat().st_mtime_ns) == unchanged
    assert unrelated(initial) == unrelated(repaired)
    assert full_fields(repaired) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [source])
    assert products(tmp_path) == stable and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))
