"""INC-QML-54: pending-label deletion shares guarded product publication."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest

import graphify.publication as publication
from graphify.publication import ProductPublication


NAMES = ("graph.json", ".graphify_labels.pending.json", "manifest.json")


def seed(root):
    """Give each inventoried product distinct durable bytes before mutation."""
    root.mkdir(exist_ok=True)
    for name in NAMES:
        (root / name).write_bytes(("original " + name).encode())
    return snapshot(root)


def snapshot(root):
    return {name: (root / name).read_bytes() if (root / name).exists() else None for name in NAMES}


@pytest.mark.parametrize("present", [False, True])
def test_req_qml011_ac04_inventory_deletion_commits_once_and_repeats(tmp_path, present):
    """Scheduling is inert; existing, absent and repeated removals are safe."""
    before = seed(tmp_path)
    pending = tmp_path / NAMES[1]
    if not present:
        pending.unlink()
        before[NAMES[1]] = None
    for attempt in range(2):
        with ProductPublication(tmp_path, NAMES) as transaction:
            transaction.delete(NAMES[1])
            transaction.delete(NAMES[1])
            assert snapshot(tmp_path) == before
            changed = transaction.commit()
        assert changed == ((NAMES[1],) if present and attempt == 0 else ())
        assert not pending.exists()
        before[NAMES[1]] = None
    assert not list(tmp_path.glob(".gfy-publish-*"))


@pytest.mark.parametrize("name", ["../outside", "undeclared.json", "", None, []])
def test_req_qml012_ac04_deletion_rejects_undeclared_or_unsafe_names(tmp_path, name):
    """An operation cannot expand the validated inventory or mutate another path."""
    before = seed(tmp_path)
    with ProductPublication(tmp_path, NAMES) as transaction:
        with pytest.raises(ValueError, match="unknown product"):
            transaction.delete(name)
    assert snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".gfy-publish-*"))


@pytest.mark.parametrize("delete_first", [False, True])
def test_req_qml012_ac04_conflicting_stage_and_delete_are_rejected(tmp_path, delete_first):
    """One product cannot acquire two contradictory publication owners."""
    before = seed(tmp_path)
    with ProductPublication(tmp_path, NAMES) as transaction:
        if delete_first:
            transaction.delete(NAMES[1])
            with pytest.raises(ValueError, match="conflicting product operations"):
                transaction.stage(NAMES[1])
        else:
            transaction.stage(NAMES[1])
            with pytest.raises(ValueError, match="conflicting product operations"):
                transaction.delete(NAMES[1])
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("fault", ["after_delete", "later_replace"])
def test_req_qml012_ac02_real_deletion_or_later_failure_restores_then_retries(tmp_path, monkeypatch, fault):
    """Actual unlink and graph replacement must both roll back after a late fault."""
    before = seed(tmp_path)
    original_unlink = Path.unlink
    original_replace = publication.os_replace_with_fallback
    removed = []

    def unlink_then_fail(path, *args, **kwargs):
        result = original_unlink(path, *args, **kwargs)
        if path == tmp_path / NAMES[1]:
            removed.append(path)
            if fault == "after_delete":
                raise OSError("public failure after completed unlink")
        return result

    def replace_late(source, target):
        if fault == "later_replace" and target.name == NAMES[2]:
            assert removed and not (tmp_path / NAMES[1]).exists()
            raise OSError("public later product failure")
        return original_replace(source, target)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", unlink_then_fail)
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_FAILED"):
            with ProductPublication(tmp_path, NAMES, replace=replace_late) as transaction:
                transaction.stage(NAMES[0]).write_bytes(b"new graph")
                transaction.delete(NAMES[1])
                transaction.stage(NAMES[2]).write_bytes(b"new manifest")
                transaction.commit()
    assert removed and snapshot(tmp_path) == before
    assert not list(tmp_path.glob(".gfy-publish-*"))
    with ProductPublication(tmp_path, NAMES) as transaction:
        transaction.stage(NAMES[0]).write_bytes(b"new graph")
        transaction.delete(NAMES[1])
        transaction.stage(NAMES[2]).write_bytes(b"new manifest")
        transaction.commit()
    assert snapshot(tmp_path) == {NAMES[0]: b"new graph", NAMES[1]: None, NAMES[2]: b"new manifest"}


def test_req_qml012_ac04_failed_deleted_product_restore_keeps_recovery_copy(tmp_path, monkeypatch):
    """A second real boundary failure retains the deleted product's old bytes."""
    before = seed(tmp_path)
    original_replace = publication.os_replace_with_fallback

    def fail_restore(source, target):
        if source.parent.name == "restore" and target.name == NAMES[1]:
            raise OSError("public restore failure")
        return original_replace(source, target)

    def fail_manifest(source, target):
        if target.name == NAMES[2]:
            raise OSError("public later product failure")
        return original_replace(source, target)

    with monkeypatch.context() as failure:
        failure.setattr(publication, "os_replace_with_fallback", fail_restore)
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_RECOVERY"):
            with ProductPublication(tmp_path, NAMES, replace=fail_manifest) as transaction:
                transaction.delete(NAMES[1])
                transaction.stage(NAMES[2]).write_bytes(b"new manifest")
                transaction.commit()
    recovery = list(tmp_path.glob(".gfy-publish-*/old/" + NAMES[1]))
    assert len(recovery) == 1 and recovery[0].read_bytes() == before[NAMES[1]]
    assert not (tmp_path / NAMES[1]).exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only deletion boundary")
def test_req_qml018_ac06_readonly_deletion_preserves_products_then_retries(tmp_path):
    """A protected pending sidecar rejects before any sibling replacement starts."""
    before = seed(tmp_path)
    pending = tmp_path / NAMES[1]
    pending.chmod(stat.S_IREAD)
    try:
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_FAILED"):
            with ProductPublication(tmp_path, NAMES) as transaction:
                transaction.stage(NAMES[0]).write_bytes(b"new graph")
                transaction.delete(NAMES[1])
                transaction.commit()
        assert snapshot(tmp_path) == before
        assert not pending.stat().st_mode & stat.S_IWRITE
        assert not list(tmp_path.glob(".gfy-publish-*"))
    finally:
        pending.chmod(stat.S_IWRITE)
    with ProductPublication(tmp_path, NAMES) as transaction:
        transaction.stage(NAMES[0]).write_bytes(b"new graph")
        transaction.delete(NAMES[1])
        transaction.commit()
    assert not pending.exists() and (tmp_path / NAMES[0]).read_bytes() == b"new graph"


def test_req_qml018_ac06_pending_label_promotion_rolls_back_with_watcher_products(tmp_path, monkeypatch):
    """A late manifest failure restores the real removed fallback sidecar cohort."""
    import graphify.cluster
    import graphify.watch as watch

    source = tmp_path / "adapter.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    assert watch._rebuild_code(tmp_path)
    out = tmp_path / "graphify-out"
    pending = out / NAMES[1]
    names = json.loads(pending.read_text(encoding="utf-8"))
    assert names
    (out / ".graphify_labels.json").write_text(json.dumps(names), encoding="utf-8")
    names_all = (*NAMES, ".graphify_labels.json", ".graphify_labels.json.sig",
                 ".graphify_root", ".qt_analysis.json", "GRAPH_REPORT.md")
    before = {name: (out / name).read_bytes() for name in names_all}
    cid = int(next(iter(names)))
    monkeypatch.setattr(graphify.cluster, "cluster", lambda graph: {cid: list(graph.nodes)})
    source.write_text("def alpha():\n    return 1\n\ndef beta():\n    return 2\n", encoding="utf-8")
    original_replace = watch.os_replace_with_fallback
    removed = []

    def fail_manifest(source, target):
        if target.name == "manifest.json":
            removed.append(not pending.exists())
            raise OSError("public label publication failure")
        return original_replace(source, target)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", fail_manifest)
        assert not watch._rebuild_code(tmp_path)
    assert removed == [True]
    assert {name: (out / name).read_bytes() for name in names_all} == before
    assert watch._rebuild_code(tmp_path)
    assert not pending.exists()
    accepted = {name: (out / name).read_bytes() for name in names_all if name != NAMES[1]}
    assert watch._rebuild_code(tmp_path)
    assert accepted == {name: (out / name).read_bytes() for name in accepted}
    assert not pending.exists()
