"""INC-QML-88: changing the parse role keeps original source and durable state."""
from __future__ import annotations

import os
import stat

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.qt_cpp_test_helpers import collect
from tests.qt_analysis_helpers import sites
from tests.test_qt_cmake_mutation_updates import compare_clean, normalized, published

BRACED = """#include <QtTest>
void run(bool ready){QQmlApplicationEngine engine;
 if(ready){QFETCH(QQmlApplicationEngine,engine);}
 engine.load("Main.qml");
}
"""
IMPLICIT = BRACED.replace("{QFETCH(QQmlApplicationEngine,engine);}", "QFETCH(QQmlApplicationEngine,engine);")


def project(root):
    path = root / "checks.cpp"
    path.write_bytes(BRACED.encode())
    (root / "retained.py").write_text("\n".join(f"def retained_{i}(): return {i}" for i in range(40)), encoding="utf-8")
    return path


def columns(root):
    return {identity: qt_metadata(node) for identity, node in published(root).nodes(data=True)
            if qt_metadata(node).get("kind") == "test_data"}


def test_req_qml022_ac06_direct_implicit_column_uses_actual_canonical_owner(tmp_path):
    """Direct overlay facts borrow accepted source owners unchanged and expose no declaration type."""
    result = collect(tmp_path, {"checks.cpp": IMPLICIT})
    found, = sites(result, "test_data")
    owner = next(n for n in result["nodes"] if n["id"] == qt_metadata(found)["owner_id"])
    assert owner.get("_callable") and owner["label"] == "run()"
    assert qt_metadata(found)["parsed_role"] == "opaque_statement"


@pytest.mark.parametrize("same_offsets", [False, True])
def test_req_qml022_ac06_braced_implicit_transition_retires_role_matches_full_and_recovers(tmp_path, same_offsets):
    """Both changed-ID and same-ID role edits replace old metadata and preserve later outer references."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    original, before = columns(tmp_path), normalized(published(tmp_path))
    assert len(original) == 1 and all(md.get("parsed_role") != "opaque_statement" for md in original.values())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    changed = (BRACED.replace("{QFETCH(QQmlApplicationEngine,engine);}", " QFETCH(QQmlApplicationEngine,engine); ")
               if same_offsets else IMPLICIT)
    path.write_bytes(changed.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    current, = columns(tmp_path).values()
    assert current["parsed_role"] == "opaque_statement"
    if same_offsets:
        assert set(original) == set(columns(tmp_path))
    else:
        assert not set(original) & set(published(tmp_path))
    assert len([n for _, n in published(tmp_path).nodes(data=True) if qt_metadata(n).get("kind") == "qml_load"]) == 1
    compare_clean(tmp_path)
    path.write_bytes(BRACED.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert columns(tmp_path) == original
    compare_clean(tmp_path)
    saved = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == saved


@pytest.mark.parametrize("force", [False, True])
def test_req_qml022_ac06_invalid_implicit_role_retains_products_then_recovery(tmp_path, force):
    """The new inert view cannot hide an initializer misuse from guarded publication."""
    path = project(tmp_path)
    path.write_bytes(IMPLICIT.encode())
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted implicit source-column report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(IMPLICIT.replace("if(ready)QFETCH(QQmlApplicationEngine,engine);",
                                     "for(QFETCH(QQmlApplicationEngine,engine);;){}").encode())
    for _ in range(2):
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False, force=force)
        assert {name: (out / name).read_bytes() for name in names} == prior
    path.write_bytes(IMPLICIT.encode())
    assert _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True, acquire_lock=False)
    assert len(columns(tmp_path)) == 1
    compare_clean(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only replacement boundary")
def test_req_qml022_ac06_implicit_role_write_failure_retains_and_retries(tmp_path):
    """Real output failure cannot partially persist changed source roles or their scopes."""
    path = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    (out / "report.md").write_bytes(b"Previously accepted declaration-column report\n")
    names = ("graph.json", "manifest.json", "report.md", QT_STATE_FILE)
    prior = {name: (out / name).read_bytes() for name in names}
    path.write_bytes(IMPLICIT.encode())
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
