"""REQ-QML-022-AC03/06: inclusion syntax edits keep durable authority current."""
from __future__ import annotations

import json
import os
import stat

import pytest

from tests.qml_persistence_helpers import protected_snapshot
from tests.qt_metaobject_helpers import member_edges
from tests.test_qml_types_qt612_updates import run_update
from tests.test_qt_final_incremental_parity import clean, normalized, published
from tests.test_qt_metaobject_updates import project


def guarded(source):
    """Wrap unchanged declaration bytes in the accepted literal whole-file profile."""
    return b"#ifndef BACKEND_HPP\n#define BACKEND_HPP\n" + source + b"#endif\n"


def payload(root):
    return json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_guard_only_edit_retires_feature_uncertainty_and_matches_fresh(tmp_path, monkeypatch, operation):
    """Changing only the condition updates actual native edges through either public driver."""
    from graphify.watch import _rebuild_code

    path = project(tmp_path)
    original = path.read_bytes()
    path.write_bytes(guarded(original).replace(b"#ifndef BACKEND_HPP", b"#ifdef BACKEND_HPP"))
    monkeypatch.chdir(tmp_path)

    def update():
        if operation == "manual":
            assert run_update(tmp_path, monkeypatch) == 0
        else:
            assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)

    update()
    assert not member_edges(payload(tmp_path))
    path.write_bytes(guarded(original))
    update()
    assert len(member_edges(payload(tmp_path))) == 3
    assert normalized(published(tmp_path)) == normalized(clean(tmp_path, tmp_path / ".cold"))
    settled = protected_snapshot(tmp_path / "graphify-out")
    update()
    assert protected_snapshot(tmp_path / "graphify-out") == settled
    path.write_bytes(guarded(original).replace(b"#define BACKEND_HPP", b"#define DIFFERENT_HPP"))
    update()
    assert not member_edges(payload(tmp_path))
    assert normalized(published(tmp_path)) == normalized(clean(tmp_path, tmp_path / ".cold2"))


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only output replacement boundary")
def test_guard_only_authority_change_write_failure_retains_and_recovers(tmp_path, monkeypatch):
    """Failed publication cannot expose a new guard interpretation before replacement succeeds."""
    path = project(tmp_path)
    original = path.read_bytes()
    path.write_bytes(guarded(original).replace(b"#ifndef BACKEND_HPP", b"#ifdef BACKEND_HPP"))
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    output = tmp_path / "graphify-out"
    accepted = protected_snapshot(output)
    assert not member_edges(payload(tmp_path))
    path.write_bytes(guarded(original))
    graph = output / "graph.json"
    graph.chmod(stat.S_IREAD)
    try:
        assert run_update(tmp_path, monkeypatch) == 1
        assert protected_snapshot(output) == accepted
        assert not list(output.glob(".gfy-*.tmp"))
    finally:
        graph.chmod(stat.S_IWRITE)
    assert run_update(tmp_path, monkeypatch) == 0
    assert len(member_edges(payload(tmp_path))) == 3
    settled = protected_snapshot(output)
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(output) == settled
