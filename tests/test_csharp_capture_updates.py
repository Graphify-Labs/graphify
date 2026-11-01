"""INC-QML-105: capture retarget/removal and failed publication use real owners."""
import pytest

from graphify.watch import _rebuild_code
from tests.csharp_capture_helpers import capture_calls, graph_payload, local, method, source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_qt_final_incremental_parity import manual_update, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def project(root):
    path = root / "Capture.cs"
    path.write_bytes(source("var").encode())
    (root / "keep.py").write_bytes(b"def helper(): return 1\n\ndef retained(): return helper()\n")
    return path


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_capture_updates_retarget_then_remove_stale_edges(tmp_path, monkeypatch, operation):
    """Only the captured declaration changes; the real local caller keeps its identity."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    first = graph_payload(initial)
    caller, original_target = local(first)["id"], method(first, "Worker")["id"]
    assert capture_calls(first)[0]["target"] == original_target
    path.write_bytes(source("var").replace("var worker=new Worker()", "var worker=new Other()").encode())
    changed = run(tmp_path, monkeypatch, operation, [path])
    payload = graph_payload(changed)
    assert local(payload)["id"] == caller
    assert capture_calls(payload)[0]["target"] == method(payload, "Other")["id"]
    assert not any(edge["source"] == caller and edge["target"] == original_target and edge["relation"] == "calls"
                   for edge in payload["edges"])
    assert full_fields(changed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    path.write_bytes(source("var").replace("void Inner()", "static void Inner()").encode())
    removed = run(tmp_path, monkeypatch, operation, [path])
    assert local(graph_payload(removed))["id"] == caller
    assert not capture_calls(graph_payload(removed))
    assert full_fields(removed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(removed)
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_capture_write_failure_retains_and_retries_unchanged_source(tmp_path, monkeypatch, capsys, operation):
    """A real target-write error cannot commit changed receiver edges or analysis state early."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    path.write_bytes(source("typed").replace("Worker worker=new Worker()", "Other worker=new Other()").encode())
    source_state = path.read_bytes(), path.stat().st_mtime_ns
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            if operation == "manual":
                with pytest.raises(SystemExit) as failure:
                    manual_update(tmp_path, monkeypatch)
                assert failure.value.code == 1
            else:
                assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
            assert products(tmp_path) == accepted
        assert fault.qualified and fault.hits >= 2
    captured = capsys.readouterr()
    assert "GRAPH_PUBLICATION_FAILED" in captured.out + captured.err
    recovered = run(tmp_path, monkeypatch, operation, [path])
    payload = graph_payload(recovered)
    assert capture_calls(payload)[0]["target"] == method(payload, "Other")["id"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == source_state
    assert unrelated(initial) == unrelated(recovered)
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable
