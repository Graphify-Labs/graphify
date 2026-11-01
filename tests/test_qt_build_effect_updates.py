"""INC-QML-95: finite negative effects preserve real update and publication gates."""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.test_qt_build_source_effects import SAFE, fixture
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def setup(root):
    """The finite executable loop is accepted by the existing separate CMake parser profile."""
    paths = fixture(root, SAFE[3])
    (root / "keep.py").write_text("def helper():return 1\n\ndef retained():return helper()\n")
    return paths


def data_names(graph):
    return {qt_metadata(node)["raw_name"] for _, node in graph.nodes(data=True)
            if qt_metadata(node).get("kind") == "test_data"}


def edit(path):
    path.write_bytes(path.read_bytes().replace(b"int,value", b"int,fresh").replace(b"(value,1)", b"(fresh,1)"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_finite_effect_cpp_edit_matches_full_and_settles(tmp_path, monkeypatch, operation):
    """An independently accepted positive metadata shape exercises actual cold/warm/update publication."""
    paths = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert data_names(initial) == {"value"}
    edit(paths[0])
    updated = run(tmp_path, monkeypatch, operation, [paths[0]])
    assert data_names(updated) == {"fresh"}
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(initial) == unrelated(updated)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_finite_effect_write_failure_retains_then_recovers(tmp_path, monkeypatch, operation):
    """A real graph replacement error cannot commit source interpretation or accepted analysis state early."""
    paths = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    edit(paths[0])
    replace = os.replace

    def reject(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated finite build-effect publication failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[paths[0]], no_cluster=True)
    assert products(tmp_path) == before and data_names(initial) == {"value"}
    recovered = run(tmp_path, monkeypatch, operation, [paths[0]])
    assert data_names(recovered) == {"fresh"}
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))


def test_req_qml022_ac06_source_append_retains_separate_cli_metadata_rejection(tmp_path, monkeypatch):
    """A source-context success cannot silently clear the older unsupported QML CMake contract."""
    paths = fixture(tmp_path, "")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, "manual")
    before = products(tmp_path)
    original = paths[2].read_bytes()
    paths[2].write_bytes(original + SAFE[0].encode())
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(row.get("source_file") == "tests/check.cpp" for row in result.get("qml_failures", []))
    assert any(row.get("source_file") == "tests/CMakeLists.txt" for row in result.get("qml_failures", []))
    with pytest.raises(SystemExit) as failure:
        manual_update(tmp_path, monkeypatch)
    assert failure.value.code == 1 and products(tmp_path) == before
    paths[2].write_bytes(original)
    recovered = run(tmp_path, monkeypatch, "manual")
    assert normalized(recovered) == normalized(initial)


def test_req_qml022_ac06_finite_effect_direct_graph_export_failure_retention_and_recovery(tmp_path, monkeypatch):
    """Direct accepted facts retain source witnesses through export/reload; failure preserves the prior file."""
    paths = setup(tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result.get("qml_failures")
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    before = output.read_bytes()
    edit(paths[0])
    changed = build_from_json(extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False), root=tmp_path, directed=True)
    replace = os.replace

    def reject(source, target):
        if Path(target).resolve() == output.resolve():
            raise OSError(errno.EIO, "isolated finite build-effect export failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", reject)
        with pytest.raises(OSError, match="finite build-effect"):
            to_json(changed, {}, str(output), force=True)
    assert output.read_bytes() == before
    assert to_json(changed, {}, str(output), force=True)
    loaded = load_node_link_graph(output)
    assert data_names(loaded) == {"fresh"}
    assert all(qt_metadata(node).get("build_include_witnesses") for _, node in loaded.nodes(data=True)
               if qt_metadata(node).get("kind") == "test_data")


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_metadata_effect_domain_replays_and_retires_stale_authority(tmp_path, monkeypatch, operation):
    """Only metadata changes: a fresh finite proof publishes, overlapping ownership rejects, then recovery settles."""
    paths = setup(tmp_path)
    (tmp_path / "tests/tst_check.cpp").write_bytes(b"void check_variant(){}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    original = paths[2].read_bytes()
    good = original.replace(b"IN ITEMS Alpha Beta", b"IN ITEMS view edit")
    paths[2].write_bytes(good)
    updated = run(tmp_path, monkeypatch, operation, [paths[2]])
    ids = lambda graph: {identity for identity, node in graph.nodes(data=True)
                         if qt_metadata(node).get("kind") == "test_data"}
    assert ids(updated) == ids(initial)
    witnesses = [w for _, node in updated.nodes(data=True) if qt_metadata(node).get("kind") == "test_data"
                 for w in qt_metadata(node)["build_include_witnesses"]]
    assert witnesses and {w["build_sha256"] for w in witnesses} == {hashlib.sha256(good).hexdigest()}
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".metadata-cold"))
    accepted = products(tmp_path)
    paths[2].write_bytes(good.replace(b"IN ITEMS view edit", b"IN ITEMS Check").replace(b"Tool${kind}", b"${kind}"))
    if operation == "manual":
        with pytest.raises(SystemExit) as failure:
            manual_update(tmp_path, monkeypatch)
        assert failure.value.code == 1
    else:
        assert not _rebuild_code(tmp_path, changed_paths=[paths[2]], no_cluster=True)
    assert products(tmp_path) == accepted
    paths[2].write_bytes(good)
    recovered = run(tmp_path, monkeypatch, operation, [paths[2]])
    assert normalized(recovered) == normalized(updated)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == before
