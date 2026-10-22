"""REQ-QML-018-AC06: real Windows rejection through manual/watch publication."""
from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

import graphify.watch as watch
from graphify.paths import write_text_atomic
from tests.test_qt_final_incremental_parity import clean, normalized, project, run


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")


def durable(root):
    """Only accepted products/cache entries count; candidate scratch is not accepted."""
    output = root / "graphify-out"
    files = [output / name for name in
             ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")]
    files.extend(path for path in (output / "cache").rglob("*") if path.is_file())
    return {path.relative_to(output).as_posix(): path.read_bytes() for path in files}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_readonly_graph_preserves_products_then_retries(tmp_path, monkeypatch, operation):
    """The real OS rejects the candidate after successful source analysis; retry agrees."""
    source = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    accepted = durable(tmp_path)
    source.write_text(source.read_text(encoding="utf-8").replace("adjustment", "offset"),
                      encoding="utf-8", newline="")
    target = tmp_path / "graphify-out/graph.json"
    target.chmod(stat.S_IREAD)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
        assert durable(tmp_path) == accepted
        assert not target.stat().st_mode & stat.S_IWRITE
        assert not list(target.parent.glob(".gfy-*.tmp"))
    finally:
        target.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(repaired) != normalized(initial)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".repaired"))
    current = durable(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(repaired)
    assert durable(tmp_path) == current


@pytest.mark.parametrize("name", ["manifest.json", ".qt_analysis.json", ".graphify_root", "cache/entry.json"])
def test_req_qml018_ac06_individual_readonly_product_writer_preserves_prior(tmp_path, name):
    """Every product's shared writer rejects without changing that accepted destination."""
    target = tmp_path / "graphify-out" / name
    target.parent.mkdir(parents=True)
    target.write_bytes(b"accepted\r\n")
    target.chmod(stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            write_text_atomic(target, "candidate\n")
        assert target.read_bytes() == b"accepted\r\n"
        assert {path for path in target.parent.iterdir()} == {target}
    finally:
        target.chmod(stat.S_IWRITE)
    write_text_atomic(target, "candidate\n")
    assert target.read_text(encoding="utf-8") == "candidate\n"
