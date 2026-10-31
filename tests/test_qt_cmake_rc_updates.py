"""INC-QML-53: RC compile dependencies preserve guarded update and recovery contracts."""
from __future__ import annotations

import pytest

from graphify.extract import collect_files
from graphify.qt_analysis_state import QT_STATE_FILE, inspect_qt_analysis, read_qt_fingerprint
from graphify.watch import _rebuild_code
from tests.test_qt_cmake_mutation_updates import compare_clean, fixture, normalized, published
from tests.test_qt_cmake_rc_dependencies import RC_PREFIX


def project(root):
    """Extend the public module fixture without adding dependency-file admission."""
    build = fixture(root)
    build.write_bytes(RC_PREFIX.encode() + build.read_bytes())
    (root / "icon_1.ico").write_bytes(b"first opaque icon")
    (root / "icon_2.ico").write_bytes(b"second opaque icon")
    return build


def test_req_qml011_ac02_rc_dependency_only_changes_match_full_and_repeat(tmp_path):
    """Retargeting ignored build prerequisites cannot alter runtime facts or admit files."""
    build = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    baseline = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    build.write_bytes(build.read_bytes().replace(b"icon_1.ico", b"icon_2.ico"))
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)
    out = tmp_path / "graphify-out"
    stamp = (out / QT_STATE_FILE).read_bytes()
    dependency = tmp_path / "icon_2.ico"
    dependency.write_bytes(b"changed opaque icon")
    assert _rebuild_code(tmp_path, changed_paths=[dependency], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    assert (out / QT_STATE_FILE).read_bytes() == stamp
    assert _rebuild_code(tmp_path, changed_paths=[dependency], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)


@pytest.mark.parametrize("change", ["scope", "mixed_sources", "dynamic_source", "arity", "unknown", "runtime"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml012_ac02_rc_rejection_preserves_products_and_recovers(tmp_path, change, force):
    """Failed RC exemption cannot replace accepted graph/manifest/report/policy state.

    Repeat the rejection, repair the same metadata, then prove warm/repeated and
    full accepted-corpus parity without deleting or weakening retained products.
    """
    build = project(tmp_path)
    accepted = build.read_bytes()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    baseline = normalized(published(tmp_path))
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted public report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    replacements = {
        "scope": (b"app.rc PROPERTIES", b"app.rc DIRECTORY other PROPERTIES"),
        "mixed_sources": (b"app.rc PROPERTIES", b"app.rc backend.h PROPERTIES"),
        "dynamic_source": (b"app.rc PROPERTIES", b"${rc_source} PROPERTIES"),
        "arity": (b'OBJECT_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/icon_1.ico"', b"OBJECT_DEPENDS"),
        "unknown": (b"OBJECT_DEPENDS", b"UNKNOWN_PROPERTY"),
        "runtime": (b"OBJECT_DEPENDS", b"QT_RESOURCE_ALIAS"),
    }
    before, after = replacements[change]
    assert before in accepted
    build.write_bytes(accepted.replace(before, after, 1))
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    build.write_bytes(accepted)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == baseline
    compare_clean(tmp_path)


@pytest.mark.parametrize("prior_policy", [23, 24, 25])
def test_req_qml011_ac04_prior_policy_refresh_rejection_retains_products_then_commits26(tmp_path, monkeypatch, prior_policy):
    """A pending policy upgrade cannot advance state before accepted publication.

    Normal rebuilds write prior-policy products for common supported input. A
    rejected RC mutation must retain that whole cohort even under force; repair
    then publishes current-policy facts/stamp and agrees with a clean rebuild.
    """
    import graphify.qt_incremental as policy

    build = fixture(tmp_path)
    original = build.read_bytes()
    out = tmp_path / "graphify-out"
    with monkeypatch.context() as historical:
        historical.setattr(policy, "QT_POLICY_VERSION", prior_policy)
        assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
        assert not inspect_qt_analysis(tmp_path, out, collect_files(tmp_path, root=tmp_path)).changed
    (out / "report.md").write_bytes(b"Previously accepted public report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    assert inspect_qt_analysis(tmp_path, out, collect_files(tmp_path, root=tmp_path)).changed
    rejected = RC_PREFIX.replace("OBJECT_DEPENDS", "UNKNOWN_PROPERTY")
    build.write_bytes(rejected.encode() + original)
    assert not _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False, force=True)
    assert {name: (out / name).read_bytes() for name in names} == prior
    assert inspect_qt_analysis(tmp_path, out, collect_files(tmp_path, root=tmp_path)).changed
    build.write_bytes(RC_PREFIX.encode() + original)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert policy.QT_POLICY_VERSION == 26
    current = inspect_qt_analysis(tmp_path, out, collect_files(tmp_path, root=tmp_path))
    assert not current.changed and read_qt_fingerprint(out) == current.fingerprint
    assert (out / QT_STATE_FILE).read_bytes() != prior[QT_STATE_FILE]
    accepted = normalized(published(tmp_path))
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == accepted
    compare_clean(tmp_path)
