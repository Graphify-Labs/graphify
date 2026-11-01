"""INC-QML-104: real metadata-only publication retains accepted state on failure."""
import pytest

from graphify.extractors.qml_ast import QmlInputError
from graphify.watch import _rebuild_code
from tests.qml_types_legacy_helpers import constants, graph_payload, module
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_qt_final_incremental_parity import manual_update, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def project(root):
    path = root / "plugins.qmltypes"
    path.write_bytes(module().encode())
    (root / "keep.py").write_bytes(b"def helper(): return 1\n\ndef retained(): return helper()\n")
    return path


def rejected(root, monkeypatch, operation, path):
    if operation == "manual":
        with pytest.raises(SystemExit) as error:
            manual_update(root, monkeypatch)
        assert error.value.code == 1
    else:
        assert not _rebuild_code(root, changed_paths=[path], no_cluster=True, acquire_lock=False)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_legacy_metadata_updates_retire_flags_and_keep_full_parity(tmp_path, monkeypatch, operation):
    """Value changes retain identities; removal retires the old fact without touching unrelated code."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    (original, fact), = constants(graph_payload(initial))
    assert fact["value"] is True
    path.write_bytes(module(value="false").encode())
    changed = run(tmp_path, monkeypatch, operation, [path])
    (updated, metadata), = constants(graph_payload(changed))
    assert updated["id"] == original["id"] and metadata["value"] is False
    assert full_fields(changed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    path.write_bytes(module(value="false").replace("isConstant: false;", "").encode())
    removed = run(tmp_path, monkeypatch, operation, [path])
    assert not constants(graph_payload(removed)) and original["id"] not in removed
    assert full_fields(removed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(removed)
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("failure", ["invalid", "replace", "parser_unavailable"])
def test_req_qml022_ac06_legacy_metadata_rejection_retains_and_retries(tmp_path, monkeypatch, capsys, operation, failure):
    """Typed rejection, actual graph EIO and transient parser loss preserve all accepted products."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    valid = module(value="false").encode()
    path.write_bytes(module(value='"bad"').encode() if failure == "invalid" else valid)
    unchanged = path.read_bytes(), path.stat().st_mtime_ns
    if failure == "replace":
        with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
            for _ in range(2):
                rejected(tmp_path, monkeypatch, operation, path)
                assert products(tmp_path) == accepted
            assert fault.qualified and fault.hits >= 2
    elif failure == "parser_unavailable":
        def unavailable():
            raise QmlInputError("QML_PARSER_MISSING", "test-owned unavailable parser")

        with monkeypatch.context() as patch:
            patch.setattr("graphify.extractors.qml_types.load_parser", unavailable)
            for _ in range(2):
                rejected(tmp_path, monkeypatch, operation, path)
                assert products(tmp_path) == accepted
    else:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
    assert (path.read_bytes(), path.stat().st_mtime_ns) == unchanged
    captured = capsys.readouterr()
    expected = "GRAPH_PUBLICATION_FAILED" if failure == "replace" else "QML_GRAPH_PRESERVED"
    assert expected in captured.out + captured.err
    if failure == "invalid":
        path.write_bytes(valid)
    # For parser/EIO failures, source bytes and mtime stay unchanged on retry;
    # neither a failed syntax fragment nor a successful Qt stamp may hide it.
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert constants(graph_payload(recovered))[0][1]["value"] is False
    if failure != "invalid":
        assert (path.read_bytes(), path.stat().st_mtime_ns) == unchanged
    assert unrelated(initial) == unrelated(recovered)
    assert full_fields(recovered) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable
    assert not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))
