"""INC-QML-90: real source-member updates retain graph and cache transactions."""
from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, normalized, published, run, unrelated


def project(root):
    path = root / "Holder.cs"
    path.write_text("class Holder{public int this[int key]=>0; public int Count{get;set;} void Run(){}}", encoding="utf-8")
    (root / "keep.py").write_text("def retained(): return 1\n", encoding="utf-8")
    return path


def members(graph):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("metadata", {}).get("csharp_member", {}).get("kind") == "indexer"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_signature_change_removes_old_member_matches_full_and_preserves_unrelated(tmp_path, monkeypatch, operation):
    """Actual command/watch flows replace role IDs only when the source signature changes."""
    path = project(tmp_path)
    first = run(tmp_path, monkeypatch, operation)
    original = members(first)
    assert len(original) == 1
    retained = unrelated(first)
    path.write_bytes(path.read_bytes().replace(b"this[int key]", b"this[string key]"))
    changed = run(tmp_path, monkeypatch, operation, [path])
    assert len(members(changed)) == 1 and not original.keys() & changed.nodes.keys()
    assert unrelated(changed) == retained
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".fresh"))
    saved = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [path])) == normalized(changed)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == saved


def test_req_qml022_ac06_same_signature_replaces_source_metadata_without_reallocating_id(tmp_path):
    """Parameter/default/body/return edits update exact provenance under the same source signature ID."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original = members(published(tmp_path))
    path.write_text("class Holder{public string this[int renamed=2]=>null; public int Count{get;set;} void Run(){}}", encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    updated = members(published(tmp_path))
    assert updated.keys() == original.keys()
    member, = updated.values()
    md = member["metadata"]["csharp_member"]
    assert md["parameters"][0]["name"] == "renamed" and md["declared_type"] == "string"
    assert md["parameters"][0]["default_span"]
    assert normalized(published(tmp_path)) == normalized(clean(tmp_path, tmp_path / ".fresh"))
    path.write_text("class Holder{public int this[int key]=>0; public int Count{get;set;} void Run(){}}", encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert members(published(tmp_path)) == original


def test_req_qml022_ac06_failed_publication_preserves_indexer_then_recovers(tmp_path, monkeypatch):
    """The actual replacement boundary fails after changed source analysis; prior products survive retry."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted source indexer report\n")
    names = ("graph.json", "manifest.json", "report.md")
    prior = {name: (out / name).read_bytes() for name in names}
    original = members(published(tmp_path))
    path.write_bytes(path.read_bytes().replace(b"this[int key]", b"this[string key]"))
    replace = os.replace

    def fail_graph(source, destination):
        # Only the external write operation is faulted. The real analysis,
        # retention and recovery paths execute unchanged; Windows copy fallback
        # cannot turn an EIO failure into a successful replacement.
        if Path(destination).name == "graph.json":
            raise OSError(errno.EIO, "source-member graph replacement fault")
        return replace(source, destination)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", fail_graph)
        for _ in range(2):
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
            assert {name: (out / name).read_bytes() for name in names} == prior
            assert members(published(tmp_path)) == original
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(members(published(tmp_path))) == 1 and not original.keys() & published(tmp_path).nodes.keys()
    assert normalized(published(tmp_path)) == normalized(clean(tmp_path, tmp_path / ".fresh"))
    saved = (out / "graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (out / "graph.json").read_bytes() == saved
