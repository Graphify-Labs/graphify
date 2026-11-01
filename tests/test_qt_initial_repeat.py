"""INC-QML-32: first raw publication remains byte- and mtime-stable on a repeat."""
from __future__ import annotations

import copy
import json
import os

import pytest

import graphify.__main__ as entrypoint
import graphify.watch as watch
from graphify.paths import load_node_link_graph
from tests.qt_combined_adoption_fixture import corpus
from tests.test_qt_combined_adoption import accepted


RUN_FIELDS = ("diagnostics", "failed_sources", "qml_failures", "qt_failures", "hyperedges")


def update(root, monkeypatch, operation, changes=None):
    """Exercise the ordinary raw CLI/watch publication without prewarming extraction."""
    if operation == "manual":
        monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
        monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
        monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", str(root), "--no-cluster"])
        entrypoint.main()
        return True
    return watch._rebuild_code(root, changed_paths=changes, no_cluster=True)


def pin_graph_mtime(path):
    # An explicit old timestamp detects even a same-content replacement on
    # filesystems whose normal timestamp precision hides fast repeat writes.
    before = path.stat()
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns - 10_000_000_000))
    return path.read_bytes(), path.stat().st_mtime_ns


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("build_system", ["cmake", "qmake"])
@pytest.mark.parametrize("scope", ["whole", "subfolder"])
def test_cold_combined_no_cluster_repeat_keeps_bytes_mtime_and_changed_source(tmp_path, monkeypatch,
                                                                          operation, build_system, scope):
    """The first real Qt publication must survive an unchanged run, while a genuine edit is published."""
    app = corpus(tmp_path, build_system)
    root = tmp_path if scope == "whole" else app
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["app/imports"]' if scope == "whole" else '["imports"]')
    assert update(root, monkeypatch, operation)
    path = root / "graphify-out/graph.json"
    accepted(load_node_link_graph(path))
    original, timestamp = pin_graph_mtime(path)
    assert update(root, monkeypatch, operation)
    assert path.read_bytes() == original and path.stat().st_mtime_ns == timestamp
    # Repeated success must never mask a real native/QML source fact change.
    source = app / "Main.qml"
    source.write_bytes(source.read_bytes().replace(b"handleReady", b"received"))
    assert update(root, monkeypatch, operation, [source])
    assert path.read_bytes() != original and path.stat().st_mtime_ns != timestamp
    accepted(load_node_link_graph(path))
    edited, timestamp = pin_graph_mtime(path)
    assert update(root, monkeypatch, operation)
    assert path.read_bytes() == edited and path.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_cold_generic_no_cluster_repeat_does_not_rewrite_first_graph(tmp_path, monkeypatch, operation):
    """Unrelated Python keeps the same first-publication promise through both production drivers."""
    (tmp_path / "keep.py").write_bytes(b"def helper(): return 7\n\ndef retained(): return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    assert update(tmp_path, monkeypatch, operation)
    path = tmp_path / "graphify-out/graph.json"
    original, timestamp = pin_graph_mtime(path)
    assert update(tmp_path, monkeypatch, operation)
    assert path.read_bytes() == original and path.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize("field", RUN_FIELDS)
def test_known_absent_and_empty_run_lists_compare_equal_without_mutation(field):
    """Only explicitly owned empty-list omissions are representation-equivalent."""
    raw = {"nodes": [{"id": "kept", "metadata": {"source_proof": {"span": [1, 9]}}}], "links": []}
    populated = {**raw, field: [], "extracted_sources": ["first.cpp"], "built_at_commit": "first"}
    before = copy.deepcopy(populated)
    assert watch._canonical_graph_for_compare(raw) == watch._canonical_graph_for_compare(populated)
    assert populated == before


@pytest.mark.parametrize("field", RUN_FIELDS)
@pytest.mark.parametrize("value", [[{"code": "QT_DECLARATION_CONFLICT", "line": 1}], None, {}, "", 0])
def test_nonempty_or_wrong_type_run_lists_remain_observable(field, value):
    """Meaningful diagnostics, failures, hyperedges and malformed transport are never stripped."""
    raw = {"nodes": [], "links": []}
    populated = {**raw, field: value}
    assert watch._canonical_graph_for_compare(raw) != watch._canonical_graph_for_compare(populated)


@pytest.mark.parametrize("change", ["unknown", "node_proof", "edge_proof", "native_identity"])
def test_unknown_metadata_and_source_facts_still_compare_different(change):
    """The comparison cannot blanket-strip graph metadata or any native/source relationship proof."""
    raw: dict = {"nodes": [{"id": "kept", "metadata": {"source_proof": {"span": [1, 9]}}}],
           "links": [{"source": "kept", "target": "other", "metadata": {"native_endpoint": "actual"}}]}
    edited = copy.deepcopy(raw)
    if change == "unknown":
        edited["extension_policy"] = {"revision": 2}
    elif change == "node_proof":
        edited["nodes"][0]["metadata"]["source_proof"]["span"] = [2, 9]
    elif change == "edge_proof":
        edited["links"][0]["metadata"]["native_endpoint"] = "different"
    else:
        edited["links"][0]["target"] = "different"
    assert watch._canonical_graph_for_compare(raw) != watch._canonical_graph_for_compare(edited)


def test_topology_comparison_keeps_existing_stage_metadata_contract():
    """The clustered topology shortcut is deliberately outside this normalization owner."""
    raw = {"nodes": [], "links": []}
    populated = {**raw, "diagnostics": [], "hyperedges": [], "extracted_sources": ["first.cpp"]}
    assert watch._canonical_topology_for_compare(raw) != watch._canonical_topology_for_compare(populated)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_real_raw_publication_failure_retains_prior_then_recovers(tmp_path, monkeypatch, operation):
    """Normalization retains the existing failed replacement and recovery behavior for genuine edits."""
    source = tmp_path / "keep.py"
    source.write_bytes(b"def original(): return 7\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    assert update(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    path = output / "graph.json"
    original, timestamp = pin_graph_mtime(path)
    prior = {name: (output / name).read_bytes() for name in ("manifest.json", ".qt_analysis.json", ".graphify_root")}
    source.write_bytes(b"def renamed(): return 9\n")
    replace = watch.os_replace_with_fallback

    def reject_graph(staged, destination, **kwargs):
        if os.fspath(destination).endswith("graph.json"):
            raise OSError("simulated graph replacement failure")
        return replace(staged, destination, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(watch, "os_replace_with_fallback", reject_graph)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                update(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not update(tmp_path, monkeypatch, operation, [source])
    assert path.read_bytes() == original and path.stat().st_mtime_ns == timestamp
    assert all((output / name).read_bytes() == content for name, content in prior.items())
    assert not list(output.glob(".gfy-publish-*"))
    assert update(tmp_path, monkeypatch, operation, [source])
    assert path.read_bytes() != original
    assert any(node.get("label") == "renamed()" for node in json.loads(path.read_bytes())["nodes"])
