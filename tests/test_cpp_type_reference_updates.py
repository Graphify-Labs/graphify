"""INC-QML-114: scoped type restrictions survive refresh and real write failure."""
from __future__ import annotations

from copy import deepcopy
import errno

import pytest

import graphify.cache as cache
from graphify.extract import extract, extract_cpp
from graphify.graph_direction import logical_endpoints
from tests.cpp_type_reference_helpers import source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def field(graph):
    owners = {identity for identity, node in graph.nodes(data=True)
              if node.get("label") == "Holder" and node.get("source_file") == "types.cpp"}
    found = []
    for left, right, edge in graph.edges(data=True):
        pair = logical_endpoints(left, right, edge, directed=graph.is_directed())
        if pair and pair[0] in owners and edge.get("relation") == "references":
            found.append((edge, graph.nodes[pair[1]]))
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("kind", ["class", "alias"])
def test_req_qml014_ac03_ac06_scoped_rejection_refresh_retarget_and_write_recovery(tmp_path, monkeypatch, operation, kind):
    """Actual QML/metadata-only refresh retains source policy; C++ edits retire it only after publication."""
    path, qml, cmake = tmp_path / "types.cpp", tmp_path / "Main.qml", tmp_path / "CMakeLists.txt"
    path.write_bytes(source(kind))
    qml.write_bytes(b"import QtQuick\nItem {}\n")
    cmake.write_bytes(b"qt_add_qml_module(app URI Public.Context VERSION 1.0 QML_FILES Main.qml SOURCES types.cpp)\n")
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    edge, target = field(initial)
    assert not target["source_file"] and edge["cpp_type_reference_version"] == 1
    proof = deepcopy(edge["metadata"]["cpp_type_reference"])
    cpp = path.read_bytes(), path.stat().st_mtime_ns
    qml.write_bytes(b"import QtQuick\nItem {property int revision:1}\n")
    qml_only = run(tmp_path, monkeypatch, operation, [qml])
    assert field(qml_only)[0]["metadata"]["cpp_type_reference"] == proof
    assert full_fields(qml_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    cmake.write_bytes(cmake.read_bytes().replace(b"VERSION 1.0", b"VERSION 1.1"))
    metadata_only = run(tmp_path, monkeypatch, operation, [cmake])
    assert field(metadata_only)[0]["metadata"]["cpp_type_reference"] == proof
    assert full_fields(metadata_only) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == cpp
    accepted = products(tmp_path)
    path.write_bytes(source(kind, qualified=True))
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    repaired = run(tmp_path, monkeypatch, operation, [path])
    resolved, actual = field(repaired)
    assert actual["source_file"] == "types.cpp" and "cpp_type_reference_version" not in resolved
    assert full_fields(repaired) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(initial) == unrelated(repaired)
    path.write_bytes(source(kind))
    rejected_again = run(tmp_path, monkeypatch, operation, [path])
    assert not field(rejected_again)[1]["source_file"] and field(rejected_again)[0]["cpp_type_reference_version"] == 1
    before = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == before


def test_req_qml014_ac03_actual_successful_schema36_cannot_replay_without_rejection(tmp_path, monkeypatch):
    """The preceding successful cache lacks a promise; the current39 key must force re-extraction."""
    path = tmp_path / "types.cpp"
    path.write_bytes(source())
    prior = extract_cpp(path)
    for edge in prior["edges"]:
        edge.pop("cpp_type_reference_version", None)
        if isinstance(edge.get("metadata"), dict):
            edge["metadata"].pop("cpp_type_reference", None)
    with monkeypatch.context() as previous:
        previous.setattr(cache, "_AST_CACHE_SCHEMA", 36)
        cache.save_cached(path, prior, tmp_path, cache_root=tmp_path)
        assert list(cache.cache_dir(tmp_path).glob("*.json"))
    assert cache._AST_CACHE_SCHEMA == 40 and cache.load_cached(path, tmp_path, cache_root=tmp_path) is None
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm
    marked = [edge for edge in cold["edges"] if edge.get("cpp_type_reference_version") == 1]
    assert len(marked) == 1 and marked[0]["metadata"]["cpp_type_reference"]["resolution"] == "unavailable"
