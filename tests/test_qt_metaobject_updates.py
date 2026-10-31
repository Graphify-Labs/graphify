"""REQ-QML-022-AC06: real source-only authority removal, retention and recovery."""
from __future__ import annotations

import json
import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qml_persistence_helpers import protected_snapshot
from tests.qt_metaobject_helpers import member_edges, sources
from tests.test_qml_types_qt612_updates import run_update
from tests.test_qt_final_incremental_parity import clean, normalized, published


def project(root):
    """A neutral unrelated cohort keeps the graph shrink threshold outside this contract."""
    for name, source in sources().items():
        (root / name).write_bytes(source.encode())
    (root / "keep.py").write_text("\n".join(f"def retained_{i}(): return {i}" for i in range(40)), encoding="utf-8")
    return root / "backend.hpp"


def payload(root):
    return json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))


def test_req_qml022_ac06_source_marker_removal_retires_edges_matches_fresh_and_recovers(tmp_path, monkeypatch):
    """Removing only Q_OBJECT preserves provider/class facts while durable own-member edges disappear."""
    path = project(tmp_path)
    original = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    initial = published(tmp_path)
    assert len(member_edges(payload(tmp_path))) == 3
    initial_marker = {n["id"] for n in payload(tmp_path)["nodes"] if qt_metadata(n).get("kind") == "metaobject"}
    assert len(initial_marker) == 1
    path.write_bytes(original.replace(b"Q_OBJECT", b"        "))
    assert run_update(tmp_path, monkeypatch) == 0
    removed = published(tmp_path)
    assert not member_edges(payload(tmp_path))
    assert initial_marker.isdisjoint(removed.nodes)
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".cold"))
    settled = protected_snapshot(tmp_path / "graphify-out")
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == settled
    path.write_bytes(original)
    assert run_update(tmp_path, monkeypatch) == 0
    assert len(member_edges(payload(tmp_path))) == 3
    assert normalized(published(tmp_path)) == normalized(initial)


@pytest.mark.parametrize("rejection", ["override", "marker_limit"])
def test_req_qml022_ac06_rejected_marker_override_preserves_publication_then_recovers(tmp_path, monkeypatch, capsys, rejection):
    """Rejected overrides/count limits cannot replace the accepted graph/manifest/state cohort."""
    path = project(tmp_path)
    original = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    accepted = protected_snapshot(tmp_path / "graphify-out")
    invalid = b"#define Q_OBJECT\n" + original if rejection == "override" else original.replace(
        b"Q_OBJECT", b" ".join([b"Q_OBJECT"] * 51))
    path.write_bytes(invalid)
    for _ in range(2):
        assert run_update(tmp_path, monkeypatch) == 1
        assert protected_snapshot(tmp_path / "graphify-out") == accepted
    assert "QML_GRAPH_PRESERVED" in capsys.readouterr().out
    path.write_bytes(original.replace(b"Q_OBJECT", b"        "))
    assert run_update(tmp_path, monkeypatch) == 0
    assert not member_edges(payload(tmp_path))
    settled = protected_snapshot(tmp_path / "graphify-out")
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == settled


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only output replacement boundary")
def test_req_qml022_ac06_valid_marker_removal_write_failure_retains_and_retries(tmp_path, monkeypatch):
    """A real filesystem failure cannot partially publish removal of previously accepted own-member edges."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    output = tmp_path / "graphify-out"
    accepted = protected_snapshot(output)
    path.write_bytes(path.read_bytes().replace(b"Q_OBJECT", b"        "))
    graph = output / "graph.json"
    graph.chmod(stat.S_IREAD)
    try:
        assert run_update(tmp_path, monkeypatch) == 1
        assert protected_snapshot(output) == accepted
        assert not list(output.glob(".gfy-*.tmp"))
    finally:
        graph.chmod(stat.S_IWRITE)
    assert run_update(tmp_path, monkeypatch) == 0
    assert not member_edges(payload(tmp_path))
    settled = protected_snapshot(output)
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(output) == settled
