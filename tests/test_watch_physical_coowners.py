"""INC-QML-44: physical co-owner invalidation through real watch publication."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
import graphify.extract as extraction
import graphify.qt_analysis_state as state
import graphify.qt_incremental as policy
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
import graphify.watch_coowners as coowners
from tests.test_qt_final_incremental_parity import normalized, project, unrelated
from tests.test_qt_product_publication import no_scratch, snapshot


SOURCE = b"def helper():\n    return 7\n\ndef caller():\n    return helper()\n"


def owners(tmp_path, request, kind, *, mixed=False):
    """Only an admitted directory alias or real hardlink shares source content."""
    root = tmp_path / "repo"
    (root / "real").mkdir(parents=True)
    if mixed:
        project(root)
    else:
        (root / "keep.py").write_bytes(SOURCE.replace(b"helper", b"independent"))
    target = root / "real/member.py"
    target.write_bytes(SOURCE)
    if kind == "directory":
        request.getfixturevalue("directory_alias")(root / "linked", target.parent)
    else:
        (root / "linked").mkdir()
        os.link(target, root / "linked/member.py")
    alias = root / "linked/member.py"
    assert target.stat().st_ino and target.stat().st_dev
    assert (target.stat().st_dev, target.stat().st_ino) == (alias.stat().st_dev, alias.stat().st_ino)
    return root, target, alias


# Reuse the real link fixture, not its selection or graph behavior.
from tests.test_source_alias_provenance import directory_alias  # noqa: E402,F401


def published(root):
    return load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))


def complete(root, cache):
    paths = extraction.collect_files(root, follow_symlinks=True, root=root)
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return build_from_json(result, root=root)


def cache_bytes(output):
    """Compare actual cache payloads, not only the published graph cohort."""
    return {path.relative_to(output).as_posix(): path.read_bytes()
            for path in (output / "cache").rglob("*") if path.is_file()}


@pytest.mark.parametrize("kind", ["directory", "hardlink"])
@pytest.mark.parametrize("mixed", [False, True])
def test_req_qml011_ac01_ac03_qml020_ac03_one_owner_edit_refreshes_shared_content(
        tmp_path, request, monkeypatch, kind, mixed):
    """One notification retires both old APIs; unrelated/native facts remain stable."""
    root, target, alias = owners(tmp_path, request, kind, mixed=mixed)
    assert _rebuild_code(root, follow_symlinks=True, no_cluster=True, acquire_lock=False)
    before = published(root)
    independent = unrelated(before)
    observed, real_extract = [], extraction.extract

    def inputs(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.relative_to(root).as_posix() for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", inputs)
    target.write_bytes(SOURCE.replace(b"helper", b"updated"))
    assert _rebuild_code(root, changed_paths=[alias], follow_symlinks=True, no_cluster=True, acquire_lock=False)
    actual = published(root)
    assert observed == [{"real/member.py", "linked/member.py"}]
    assert "real_member_helper" not in actual and "linked_member_helper" not in actual
    assert {"real_member_updated", "linked_member_updated"} <= set(actual)
    assert unrelated(actual) == independent
    cold = complete(root, tmp_path / "full-cache")
    assert normalized(actual) == normalized(cold)
    assert normalized(complete(root, tmp_path / "full-cache")) == normalized(cold)
    accepted = snapshot(root / "graphify-out")
    observed.clear()
    assert _rebuild_code(root, changed_paths=[], follow_symlinks=True, no_cluster=True, acquire_lock=False)
    assert not observed and snapshot(root / "graphify-out") == accepted


@pytest.mark.parametrize("kind", ["directory", "hardlink"])
def test_req_qml011_ac03_normal_rename_and_deletion_retire_only_absent_owners(
        tmp_path, request, kind):
    """A normal disappearance before detection is deletion, not an identity failure."""
    root, target, _ = owners(tmp_path, request, kind)
    assert _rebuild_code(root, follow_symlinks=True, no_cluster=True, acquire_lock=False)
    renamed = target.with_name("renamed.py")
    target.rename(renamed)
    assert _rebuild_code(root, changed_paths=[target, renamed], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    actual = published(root)
    assert "real_member" not in actual and "real_renamed" in actual
    assert normalized(actual) == normalized(complete(root, tmp_path / "rename-cache"))
    renamed.unlink()
    assert _rebuild_code(root, changed_paths=[renamed], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    actual = published(root)
    assert "real_renamed" not in actual
    assert ("linked_member" in actual) == (kind == "hardlink")
    assert normalized(actual) == normalized(complete(root, tmp_path / "delete-cache"))


@pytest.mark.parametrize("operation,fault", [("resolve", OSError), ("resolve", RuntimeError),
                                            ("stat", OSError), ("stat", RuntimeError),
                                            ("disappearance", FileNotFoundError)])
def test_req_qml012_ac01_ac02_identity_failure_retains_recovers_and_repeats(
        tmp_path, request, monkeypatch, capsys, operation, fault):
    """A real admitted lookup failure preserves every published product and hides its body."""
    root, target, alias = owners(tmp_path, request, "directory", mixed=True)
    assert _rebuild_code(root, follow_symlinks=True, no_cluster=True, acquire_lock=False)
    output = root / "graphify-out"
    before = snapshot(output)
    cached = cache_bytes(output)
    assert cached
    target.write_bytes(SOURCE.replace(b"helper", b"updated"))
    real_identity = coowners.physical_identity
    raw_body = "private backend response token=must-never-appear"
    observed = []

    def failed_identity(path, anchor):
        if path != alias:
            return real_identity(path, anchor)
        observed.append(path)
        if operation == "disappearance":
            # Actual race after admitted detection, before verified co-ownership.
            target.unlink()
            return real_identity(path, anchor)
        real_operation = getattr(Path, operation)

        def unavailable(source, *args, **kwargs):
            if source == alias:
                raise fault(raw_body)
            return real_operation(source, *args, **kwargs)

        with monkeypatch.context() as lookup:
            lookup.setattr(Path, operation, unavailable)
            return real_identity(path, anchor)

    with monkeypatch.context() as failed:
        failed.setattr(coowners, "physical_identity", failed_identity)
        assert not _rebuild_code(root, changed_paths=[alias], follow_symlinks=True,
                                 no_cluster=True, acquire_lock=False)
    assert observed and snapshot(output) == before
    assert cache_bytes(output) == cached
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "WATCH_SOURCE_IDENTITY_FAILED" in text and 'source="linked/member.py"' in text
    assert raw_body not in text and str(root) not in text.split("Rebuild failed:")[-1]
    no_scratch(output)
    target.write_bytes(SOURCE.replace(b"helper", b"updated"))
    assert _rebuild_code(root, changed_paths=[alias], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    assert normalized(published(root)) == normalized(complete(root, tmp_path / "repair-cache"))
    accepted = snapshot(output)
    assert _rebuild_code(root, changed_paths=[alias], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    assert snapshot(output) == accepted
    no_scratch(output)


@pytest.mark.parametrize("label", ["a\n.py", "a\x7f.py", "a\u2028.py", "x" * 158 + ".py"])
def test_req_qml012_ac04_unsafe_or_long_missing_identity_context_is_empty(tmp_path, label):
    """Rejected lookup context is bounded independently of backend path/error text."""
    with pytest.raises(ValueError) as rejected:
        coowners.physical_identity(tmp_path / label, tmp_path)
    assert str(rejected.value) == ('WATCH_SOURCE_IDENTITY_FAILED: source=""; admitted source '
                                   'identity unavailable; prior products retained; repair and retry')


def test_req_qml011_ac01_selection_cannot_discover_foreign_or_unadmitted_coowners(tmp_path):
    """A supplied change cannot bypass admission; a true foreign corpus path is rejected."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign.py"
    root.mkdir()
    local = root / "local.py"
    local.write_bytes(SOURCE)
    foreign.write_bytes(SOURCE)
    with pytest.raises(ValueError, match="WATCH_SOURCE_IDENTITY_FAILED"):
        coowners.expand_changed_coowners([foreign], [local], root=root)
    with pytest.raises(ValueError, match="WATCH_SOURCE_IDENTITY_FAILED"):
        coowners.expand_changed_coowners([local], [local, foreign], root=root)
    with pytest.raises(ValueError, match="WATCH_SOURCE_IDENTITY_FAILED"):
        coowners.expand_changed_coowners([local], [local, root], root=root)
    assert coowners.expand_changed_coowners([], [foreign], root=root) == []
    assert local.read_bytes() == foreign.read_bytes() == SOURCE


def test_req_qml011_ac01_missing_inode_identity_uses_contained_path_without_false_joins(
        tmp_path, request, monkeypatch):
    """A filesystem without usable inode IDs still proves only resolved-path aliases."""
    root, target, alias = owners(tmp_path, request, "directory")
    separate = root / "separate.py"
    separate.write_bytes(SOURCE)
    original_stat = Path.stat

    def unidentified(path, *args, **kwargs):
        value = list(original_stat(path, *args, **kwargs))
        value[1] = value[2] = 0
        return os.stat_result(value)

    monkeypatch.setattr(Path, "stat", unidentified)
    assert coowners.expand_changed_coowners([alias], [target, alias, separate], root=root) == [alias, target]


def test_req_qml012_ac04_context_quotes_delimiters_and_preserves_160_character_boundary(tmp_path):
    """Unavailable path labels remain one bounded quoted field, never backend instructions."""
    for label in ('a"; delimiter.py', "x" * 157 + ".py"):
        with pytest.raises(ValueError) as rejected:
            coowners.physical_identity(tmp_path / label, tmp_path)
        text = str(rejected.value)
        assert f"source={json.dumps(label, ensure_ascii=True)};" in text
        assert len(label) <= coowners.SOURCE_CONTEXT_LIMIT and "\n" not in text
        assert str(tmp_path) not in text


def test_req_qml011_ac03_ac04_qml020_ac03_policy20_refresh_retains_repairs_and_repeats(
        tmp_path, request, monkeypatch, capsys):
    """An unchanged prior Qt cohort refreshes both owners; stamp failure cannot publish it."""
    root, _, _ = owners(tmp_path, request, "hardlink", mixed=True)
    with monkeypatch.context() as prior:
        prior.setattr(policy, "QT_POLICY_VERSION", 20)
        assert _rebuild_code(root, follow_symlinks=True, no_cluster=True, acquire_lock=False)
    output = root / "graphify-out"
    before, initial = snapshot(output), normalized(published(root))
    fingerprint = state.read_qt_fingerprint(output)
    observed, real_extract = [], extraction.extract

    def inputs(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.relative_to(root).as_posix() for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", inputs)
    staged, real_commit = [], state.commit_qt_analysis

    def stage_then_fail(*args, **kwargs):
        real_commit(*args, **kwargs)
        staged.append(True)
        raise OSError("public co-owner policy upgrade publication failure")

    with monkeypatch.context() as failed:
        failed.setattr(state, "commit_qt_analysis", stage_then_fail)
        assert not _rebuild_code(root, changed_paths=[], follow_symlinks=True,
                                 no_cluster=True, acquire_lock=False)
    assert staged == [True] and snapshot(output) == before
    assert state.read_qt_fingerprint(output) == fingerprint
    assert "GRAPH_PUBLICATION_FAILED" in capsys.readouterr().out
    required = {"real/member.py", "linked/member.py", "Main.qml", "backend.h", "loader.cpp"}
    assert observed and required <= set.union(*observed)
    no_scratch(output)
    observed.clear()
    assert _rebuild_code(root, changed_paths=[], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    assert normalized(published(root)) == initial
    assert state.read_qt_fingerprint(output) != fingerprint
    assert observed and required <= set.union(*observed)
    assert normalized(published(root)) == normalized(complete(root, tmp_path / "upgrade-cache"))
    accepted = snapshot(output)
    observed.clear()
    assert _rebuild_code(root, changed_paths=[], follow_symlinks=True,
                         no_cluster=True, acquire_lock=False)
    assert not any(observed) and snapshot(output) == accepted
    no_scratch(output)
