"""INC-QML-110: lost predecessor facts and class-domain edits require real refresh."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify import cache
from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_class_proof import class_fact
from tests.cpp_class_case_helpers import classes, source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def test_req_qml022_ac06_predecessor35_missing_class_facts_cannot_replay(tmp_path, monkeypatch):
    """A successful old cache omission cannot be repaired from its absent declarations.

    Actual producer nodes carry the recorded predecessor's missing-class-fact
    shape. Epoch retirement, rather than a label-based repair, must reparse the
    unchanged source and recover both complete original declarations.
    """
    path = tmp_path / "unit.cpp"
    path.write_bytes(source())
    prior = deepcopy(extract_cpp(path))
    for node in prior["nodes"]:
        node.get("metadata", {}).pop("cpp_class", None)
    assert not classes(prior) and prior["nodes"]
    assert cache._AST_CACHE_SCHEMA > 35
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 35)
        cache.save_cached(path, prior, tmp_path, cache_root=tmp_path)
        loaded = cache.load_cached(path, tmp_path, cache_root=tmp_path)
        assert loaded is not None and not classes(loaded)
    assert cache.load_cached(path, tmp_path, cache_root=tmp_path) is None
    state = path.read_bytes(), path.stat().st_mtime_ns
    cold = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and set(classes(cold)) == {"Box", "box"}
    assert (path.read_bytes(), path.stat().st_mtime_ns) == state


def graph_classes(graph):
    return {node["label"]: identity for identity, node in graph.nodes(data=True) if class_fact(node)}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_class_collision_addition_retains_on_eio_then_retires_and_restores_ids(tmp_path, monkeypatch, operation):
    """The real update owner atomically replaces a legacy domain and restores it after removal."""
    path = tmp_path / "unit.cpp"
    original = b"void helper(){}\nstruct Box{int field;void run(){helper();}};\n"
    path.write_bytes(original)
    (tmp_path / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    monkeypatch.chdir(tmp_path)
    first = run(tmp_path, monkeypatch, operation)
    old = graph_classes(first)["Box"]
    accepted = products(tmp_path)
    path.write_bytes(original + b"struct box{int field;void run(){helper();}};\n")
    state = path.read_bytes(), path.stat().st_mtime_ns
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, path)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    changed = run(tmp_path, monkeypatch, operation, [path])
    assert old not in changed and set(graph_classes(changed)) == {"Box", "box"}
    assert len(set(graph_classes(changed).values())) == 2
    assert (path.read_bytes(), path.stat().st_mtime_ns) == state
    assert full_fields(changed) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    assert unrelated(first) == unrelated(changed)
    collision_ids = set(graph_classes(changed).values())
    path.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [path])
    assert graph_classes(restored) == {"Box": old} and collision_ids.isdisjoint(restored)
    assert full_fields(restored) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [path])
    assert products(tmp_path) == stable
