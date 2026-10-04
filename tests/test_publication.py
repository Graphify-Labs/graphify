"""INC-QML-25: durable stages, rollback authority and truthful cleanup outcomes."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat

import pytest

import graphify.publication as publication
from graphify.paths import os_replace_with_fallback
from graphify.publication import ProductPublication


NAMES = ("graph.json", "manifest.json", ".graphify_root", ".qt_analysis.json")


def seed(root, existing=True):
    root.mkdir(exist_ok=True)
    if existing:
        for name in NAMES:
            (root / name).write_bytes(("OLD:" + name).encode())
    return {name: (root / name).read_bytes() if existing else None for name in NAMES}


def contents(root):
    return {name: (root / name).read_bytes() if (root / name).exists() else None for name in NAMES}


def stages(transaction):
    for name in NAMES:
        transaction.stage(name).write_bytes(("NEW:" + name).encode())


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("phase", ["prepare", "before_replace", "after_replace"])
def test_inc25_actual_disk_rollback_and_retry(tmp_path, existing, phase):
    """A serializer/late replacement failure retains all old or absent products."""
    before = seed(tmp_path, existing)

    def replace(source, destination):
        if destination.name == "manifest.json" and phase == "before_replace":
            raise OSError("replace boundary failed")
        os_replace_with_fallback(source, destination)
        if destination.name == "manifest.json" and phase == "after_replace":
            raise OSError("replace completed before external failure")

    with pytest.raises(OSError):
        with ProductPublication(tmp_path, NAMES, replace=replace) as transaction:
            stages(transaction)
            if phase == "prepare":
                raise OSError("serializer failed")
            transaction.commit()
    assert contents(tmp_path) == before
    assert not list(tmp_path.glob(".gfy-publish-*"))
    with ProductPublication(tmp_path, NAMES) as transaction:
        stages(transaction)
        assert transaction.commit() == NAMES
    after = contents(tmp_path)
    with ProductPublication(tmp_path, NAMES) as transaction:
        stages(transaction)
        assert transaction.commit() == ()
    assert contents(tmp_path) == after
    assert not list(tmp_path.glob(".gfy-publish-*"))


@pytest.mark.parametrize("error", [OSError, MemoryError, ValueError])
def test_inc25_actual_rollback_fault_retains_recovery_copies(tmp_path, monkeypatch, error):
    """A second actual restoration fault is distinct from fully preserved failure."""
    before = seed(tmp_path)

    def fail_second(source, destination):
        if destination.name == "manifest.json":
            raise OSError("publication failure")
        os_replace_with_fallback(source, destination)

    def rollback_fault(*_):
        raise error("restoration failure")

    monkeypatch.setattr(publication, "os_replace_with_fallback", rollback_fault)
    with pytest.raises(OSError, match="GRAPH_PUBLICATION_RECOVERY"):
        with ProductPublication(tmp_path, NAMES, replace=fail_second) as transaction:
            stages(transaction)
            transaction.commit()
    assert (tmp_path / "graph.json").read_bytes() == b"NEW:graph.json"
    retained = list(tmp_path.glob(".gfy-publish-*"))
    assert len(retained) == 1
    assert {name: (retained[0] / "old" / name).read_bytes() for name in NAMES} == before
    # Recovery uses retained authoritative bytes, rather than discarding them
    # or treating the partly published candidate as a successful cohort.
    for name in NAMES:
        os_replace_with_fallback(retained[0] / "old" / name, tmp_path / name)
    assert contents(tmp_path) == before


def test_inc25_real_replace_fallback_failure_restores_cohort(tmp_path, monkeypatch):
    """The shared copy/rename fallback fails late and restores already published siblings."""
    before = seed(tmp_path)
    original_copy = shutil.copy2

    def unavailable(*_):
        raise PermissionError("shared-folder replace unavailable")

    def failed_fallback(source, target, *args, **kwargs):
        start, end = Path(source), Path(target)
        if start.name == "manifest.json" and start.parent.name == "stage" and end.name.startswith(".gfy-replace-"):
            raise OSError("fallback copy failed")
        return original_copy(source, target, *args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(os, "replace", unavailable)
        failure.setattr(shutil, "copy2", failed_fallback)
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_FAILED"):
            with ProductPublication(tmp_path, NAMES) as transaction:
                stages(transaction)
                transaction.commit()
    assert contents(tmp_path) == before
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only attribute")
def test_inc25_unchanged_readonly_products_skip_replacement(tmp_path):
    """Readonly siblings are valid when their exact accepted bytes need no write."""
    seed(tmp_path)
    target = tmp_path / "manifest.json"
    target.chmod(stat.S_IREAD)
    try:
        with ProductPublication(tmp_path, NAMES) as transaction:
            transaction.stage("graph.json").write_bytes(b"NEW")
            transaction.stage("manifest.json")
            assert transaction.commit() == ("graph.json",)
        assert target.read_bytes() == b"OLD:manifest.json"
        assert not target.stat().st_mode & stat.S_IWRITE
        assert not list(tmp_path.glob(".gfy-publish-*"))
    finally:
        target.chmod(stat.S_IWRITE)


@pytest.mark.parametrize("change", ["changed", "appeared", "missing_stage"])
def test_inc25_preparation_cannot_overwrite_unrelated_concurrent_change(tmp_path, change):
    """All originals are validated even when a product has no changed stage."""
    seed(tmp_path, existing=change != "appeared")
    with pytest.raises(OSError, match="GRAPH_PUBLICATION_FAILED"):
        with ProductPublication(tmp_path, NAMES) as transaction:
            stages(transaction)
            if change == "missing_stage":
                transaction.stage("manifest.json").unlink()
            else:
                (tmp_path / "manifest.json").write_bytes(b"FOREIGN")
            transaction.commit()
    if change != "appeared":
        assert (tmp_path / "graph.json").read_bytes() == b"OLD:graph.json"
    else:
        assert not (tmp_path / "graph.json").exists()
    if change != "missing_stage":
        assert (tmp_path / "manifest.json").read_bytes() == b"FOREIGN"
    assert not list(tmp_path.glob(".gfy-publish-*"))


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.parametrize("error", [OSError, MemoryError])
def test_inc25_cleanup_failure_does_not_misreport_cohort_authority(tmp_path, monkeypatch, capsys, committed, error):
    """Only coherent committed products may be reported successful after cleanup faults."""
    before = seed(tmp_path)
    original = ProductPublication._cleanup

    def cleanup_fault(_):
        raise error("owned scratch is locked")

    monkeypatch.setattr(ProductPublication, "_cleanup", cleanup_fault)
    if committed:
        with ProductPublication(tmp_path, NAMES) as transaction:
            stages(transaction)
            transaction.commit()
        assert "GRAPH_PUBLICATION_CLEANUP: committed products retained" in capsys.readouterr().err
        assert contents(tmp_path) != before
    else:
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_CLEANUP: prior products retained"):
            with ProductPublication(tmp_path, NAMES) as transaction:
                stages(transaction)
                raise OSError("serializer failure")
        assert contents(tmp_path) == before
    assert len(list(tmp_path.glob(".gfy-publish-*"))) == 1
    original(transaction)
    assert not list(tmp_path.glob(".gfy-publish-*"))


def test_inc25_symlink_target_write_through_and_duplicate_authority(tmp_path):
    """Caller symlinks retain identity; two product roles cannot share a real target."""
    actual = tmp_path / "actual.json"
    actual.write_bytes(b"OLD")
    output = tmp_path / "out"
    output.mkdir()
    try:
        (output / "graph.json").symlink_to(actual)
        (output / "manifest.json").symlink_to(actual)
    except OSError:
        pytest.skip("Host symlink creation is unavailable")
    with pytest.raises(ValueError, match="share one destination"):
        ProductPublication(output, ("graph.json", "manifest.json"))
    with ProductPublication(output, ("graph.json",)) as transaction:
        transaction.stage("graph.json").write_bytes(b"NEW")
        transaction.commit()
    assert actual.read_bytes() == b"NEW"
    assert (output / "graph.json").is_symlink()
    assert not list(output.glob(".gfy-publish-*"))


@pytest.mark.parametrize("names", [("../outside",), ("graph.json", "graph.json"), (".",), ("",),
                                  ("graph.json:foreign",), ("a" * 129,), (None,)])
def test_inc25_inventory_is_bounded_to_owned_product_names(tmp_path, names):
    """Invalid product roles reject before any scratch or destination writes."""
    with pytest.raises(ValueError, match="GRAPH_PUBLICATION_FAILED"):
        ProductPublication(tmp_path, names)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("phase", ["output_dir", "scratch_dir", "child_dir", "snapshot", "canonical_path"])
def test_inc25_setup_fault_has_safe_code_and_preserves_retry(tmp_path, monkeypatch, phase):
    """External setup/copy rejection never exposes the exception's path or body."""
    before = seed(tmp_path)
    private_marker = "synthetic-sensitive-location"
    error = PermissionError(13, private_marker + "\nserializer body", str(tmp_path / private_marker))
    mkdir, copy = Path.mkdir, shutil.copy2

    def failed_mkdir(path, *args, **kwargs):
        if ((phase == "output_dir" and path == tmp_path)
                or (phase == "child_dir" and path.name == "old"
                    and path.parent.name.startswith(".gfy-publish-"))):
            raise error
        return mkdir(path, *args, **kwargs)

    def failed_copy(source, target, *args, **kwargs):
        if phase == "snapshot" and Path(target).name == "manifest.json":
            raise error
        return copy(source, target, *args, **kwargs)

    def failed_scratch(*args, **kwargs):
        raise error

    with monkeypatch.context() as failure:
        failure.setattr(Path, "mkdir", failed_mkdir)
        failure.setattr(shutil, "copy2", failed_copy)
        if phase == "scratch_dir":
            failure.setattr(publication.tempfile, "mkdtemp", failed_scratch)
        if phase == "canonical_path":
            failure.setattr(publication.os.path, "realpath", failed_scratch)
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_FAILED") as rejected:
            ProductPublication(tmp_path, NAMES)
    assert private_marker not in str(rejected.value)
    assert str(tmp_path) not in str(rejected.value)
    assert rejected.value.__cause__ is error
    assert contents(tmp_path) == before
    assert not list(tmp_path.glob(".gfy-publish-*"))
    with ProductPublication(tmp_path, NAMES) as transaction:
        stages(transaction)
        assert transaction.commit() == NAMES
    assert contents(tmp_path) != before
    assert not list(tmp_path.glob(".gfy-publish-*"))


def test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence(tmp_path, monkeypatch):
    """Failed scaffold cleanup reports its own safe code and keeps accepted bytes."""
    before = seed(tmp_path)
    error = PermissionError(13, "synthetic-sensitive-location", str(tmp_path / "private-fixture"))
    copy, unlink = shutil.copy2, os.unlink

    def reject_copy(source, target, *args, **kwargs):
        if Path(target).parent.name == "old" and Path(target).name == "manifest.json":
            raise error
        return copy(source, target, *args, **kwargs)

    def reject_cleanup(path, *args, **kwargs):
        if Path(path).parent.name == "old" and Path(path).name == "graph.json":
            raise error
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(shutil, "copy2", reject_copy)
        failure.setattr(os, "unlink", reject_cleanup)
        with pytest.raises(OSError, match="GRAPH_PUBLICATION_CLEANUP") as rejected:
            ProductPublication(tmp_path, NAMES)
    assert "synthetic-sensitive-location" not in str(rejected.value)
    assert str(tmp_path) not in str(rejected.value)
    assert contents(tmp_path) == before
    retained = list(tmp_path.glob(".gfy-publish-*"))
    assert len(retained) == 1 and (retained[0] / "old/graph.json").read_bytes() == before["graph.json"]
