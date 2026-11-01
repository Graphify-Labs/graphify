"""INC-QML-87: source-flow admission survives durable updates and rejected writes."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

SOURCE = """#include <QtTest>
void run(bool ready){
 if (ready) QTRY_VERIFY(ready);
#if FEATURE
 QFETCH(int, state);
#endif
}
"""


def project(root):
    """Unrelated declarations keep graph-shrink protection outside statement acceptance."""
    path = root / "checks.cpp"
    path.write_bytes(SOURCE.encode())
    (root / "retained.py").write_text("\n".join(f"def retained_{i}(): return {i}" for i in range(40)), encoding="utf-8")
    return path


def statements(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") in {"test_data", "test_assertion"}}


def test_req_qml022_ac06_control_scope_edits_retire_old_facts_match_full_and_recover(tmp_path):
    """Warm control/preprocessor edits preserve original scope facts and remove stale occurrences."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original, before = statements(tmp_path), normalized(published(tmp_path))
    assert len(original) == 2
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert statements(tmp_path) == original and normalized(published(tmp_path)) == before
    path.write_bytes(SOURCE.replace("if (ready)", "while (ready)").replace("QFETCH(int, state);", "int state;").encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {record["kind"] for record in statements(tmp_path).values()} == {"test_assertion"}
    assert not set(original) & set(published(tmp_path))
    compare_clean(tmp_path)
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert statements(tmp_path) == original
    compare_clean(tmp_path)
    saved = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == saved


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_expression_misuse_retains_products_then_repair_recovers(tmp_path, force):
    """A malformed condition cannot publish a partial Qt overlay through full or incremental refresh."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted source-only statement report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.replace("if (ready) QTRY_VERIFY(ready);", "if(QTRY_VERIFY(ready)) {}").encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(SOURCE.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(statements(tmp_path)) == 2
    compare_clean(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only replacement boundary")
def test_req_qml022_ac06_valid_statement_edit_write_failure_retains_and_retries(tmp_path):
    """Real replacement failure preserves every accepted product before corrected retry/idempotence."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted source-only statement report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(SOURCE.replace("if (ready)", "while (ready)").encode())
    target = out / "graph.json"
    mode = target.stat().st_mode
    os.chmod(target, stat.S_IREAD)
    try:
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
        assert {name: (out / name).read_bytes() for name in names} == prior
        assert not list(out.glob(".gfy-*.tmp"))
    finally:
        os.chmod(target, mode)
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    compare_clean(tmp_path)
    accepted = target.read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert target.read_bytes() == accepted
