"""INC-QML-71: class fields survive update, removal and failed publication."""
from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, published, run, unrelated


def project(root):
    path = root / "Holder.cs"
    path.write_text("class Holder { public int count; public void Run() {} }\n", encoding="utf-8")
    (root / "keep.py").write_text("def retained(): return 1\n", encoding="utf-8")
    return path


def field_nodes(graph):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("metadata", {}).get("csharp_member", {}).get("kind") == "field"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_field_changes_remove_stale_ids_and_match_clean_extraction(tmp_path, monkeypatch, operation):
    """Real manual/watch paths preserve unrelated source and clean/full parity."""
    path = project(tmp_path)
    first = run(tmp_path, monkeypatch, operation)
    fields = field_nodes(first)
    assert {n["label"] for n in fields.values()} == {"count"}
    retained = unrelated(first)
    path.write_bytes(path.read_bytes().replace(b"count", b"total"))
    changed = run(tmp_path, monkeypatch, operation, [path])
    assert {n["label"] for n in field_nodes(changed).values()} == {"total"}
    assert not fields.keys() & changed.nodes.keys()
    assert unrelated(changed) == retained
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".fresh"))
    accepted = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [path])) == normalized(changed)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == accepted


def test_failed_graph_replacement_preserves_field_publication_then_recovers(tmp_path, monkeypatch):
    """A real OS write failure cannot advertise new members in an old graph."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    prior = {name: (out / name).read_bytes() for name in ("graph.json", "manifest.json")}
    path.write_bytes(path.read_bytes().replace(b"count", b"total"))
    replace = os.replace

    def reject(source, destination):
        if Path(destination).name == "graph.json":
            # Permission errors have an intentional Windows copy fallback.
            # An I/O error exercises a real unrecoverable publication failure.
            raise OSError(errno.EIO, "simulated graph replacement failure")
        return replace(source, destination)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", reject)
        for _ in range(2):
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
            assert {name: (out / name).read_bytes() for name in prior} == prior
            assert {n["label"] for n in field_nodes(published(tmp_path)).values()} == {"count"}
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert {n["label"] for n in field_nodes(published(tmp_path)).values()} == {"total"}
    assert normalized(published(tmp_path)) == normalized(clean(tmp_path, tmp_path / ".fresh"))
