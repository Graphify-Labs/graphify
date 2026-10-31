"""INC-QML-116: cold parity publication never moves the accepted output cohort."""
from __future__ import annotations

import errno
import json
from pathlib import Path
import subprocess

import pytest

import graphify
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields, project
from tests.test_qt_final_incremental_parity import run


def snapshot(root):
    """Retain source and every accepted file, including caches beyond the four products."""
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def evidence(root, before):
    created = set(root.parent.glob("allocated-member-products-*")) - before
    assert len(created) == 1
    retained, = created
    return retained


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_cold_output_preserves_all_bytes_without_directory_moves(tmp_path, monkeypatch, operation):
    """A real publication succeeds despite unavailable parent directory moves and a CWD import decoy."""
    project(tmp_path)
    # This analyzed Python file must never supply the harness implementation.
    (tmp_path / "graphify.py").write_text('raise RuntimeError("corpus import executed")\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    before = snapshot(tmp_path)
    retained_before = set(tmp_path.parent.glob("allocated-member-products-*"))

    def denied(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "test-owned directory movement unavailable")

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "rename", denied)
        cold = cold_reference(tmp_path, scoped, operation)
    assert full_fields(cold) == full_fields(initial)
    assert snapshot(tmp_path) == before
    retained = evidence(tmp_path, retained_before)
    identity = json.loads((retained / "identity.json").read_text(encoding="utf-8"))
    assert identity["package_file"] == str(Path(graphify.__file__).resolve())
    assert identity["analysis_root"] == str(tmp_path.resolve())
    assert identity["output"] == str((retained / "cold-reference").resolve())
    assert identity["output_existed"] is False
    assert identity["isolated"] is True and identity["operation"] == operation
    log = (retained / "child.log").read_text(encoding="utf-8")
    assert "AST cache: 0/5 files served from cache" in log
    assert (retained / "cold-reference/graph.json").is_file()
    assert not (retained / "accepted").exists()


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_failed_cold_child_retains_accepted_then_repairs_and_repeats(tmp_path, monkeypatch, operation):
    """Actual malformed QML fails the isolated owner; repaired cold runs preserve the accepted cohort."""
    _, qml, _ = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    valid = qml.read_bytes()
    qml.write_bytes(b'import Public.Allocated 1.0\nWidget { property int value: "unterminated\n')
    before = snapshot(tmp_path)
    retained_before = set(tmp_path.parent.glob("allocated-member-products-*"))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        cold_reference(tmp_path, monkeypatch, operation)
    assert failure.value.returncode != 0
    assert snapshot(tmp_path) == before
    retained = evidence(tmp_path, retained_before)
    assert (retained / "identity.json").is_file()
    assert "QML_GRAPH_PRESERVED" in (retained / "child.log").read_text(encoding="utf-8")
    qml.write_bytes(valid)
    repaired = snapshot(tmp_path)
    for _ in range(2):
        retained_before = set(tmp_path.parent.glob("allocated-member-products-*"))
        assert full_fields(cold_reference(tmp_path, monkeypatch, operation)) == full_fields(initial)
        assert snapshot(tmp_path) == repaired
        repeat_evidence = evidence(tmp_path, retained_before)
        repeat_identity = json.loads((repeat_evidence / "identity.json").read_text(encoding="utf-8"))
        assert repeat_identity["output_existed"] is False
        assert "AST cache: 0/4 files served from cache" in (repeat_evidence / "child.log").read_text(encoding="utf-8")
