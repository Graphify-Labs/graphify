"""INC-QML-96: accepted indexes remain lazy, invocation-local and publication-safe."""
from __future__ import annotations

import pytest

import graphify.extractors.qt_cpp_accepted_index as index_module
from graphify.extract import extract
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.watch import _rebuild_code
from tests.test_qt_cpp_shared_index import project
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def accepted(root):
    root.mkdir(exist_ok=True)
    paths = project(root)
    result = extract(paths, root=root, cache_root=root, parallel=False)
    return paths, result["nodes"], result["edges"]


def test_req_qml022_ac06_index_membership_is_frozen_at_entry_and_new_calls_see_new_cohorts(tmp_path):
    """Snapshot membership cannot absorb overlays; a later direct call/invocation must refresh it."""
    paths, nodes, edges = accepted(tmp_path)
    unit = read_cpp(paths[0], tmp_path)
    mapper = index_module._accepted_cpp_mapper(nodes, edges, root=tmp_path)
    extra = {"id": "later", "label": "later", "source_file": "later.hpp"}
    nodes.append(extra)
    edges.append({"source": "later", "target": "unavailable", "relation": "contains"})
    old = mapper(unit)
    assert "later" not in old.accepted and "unavailable" not in old.parents
    fresh = index_module._accepted_cpp_mapper(nodes, edges, root=tmp_path)(unit)
    direct = map_cpp(unit, nodes, edges, root=tmp_path)
    assert fresh.accepted["later"] is extra and direct.accepted["later"] is extra
    assert fresh.parents["unavailable"] == direct.parents["unavailable"] == {"later"}
    assert old.accepted is not fresh.accepted and fresh.accepted is not direct.accepted


def test_req_qml022_ac06_separate_roots_and_invocations_never_reuse_index_or_unit_state(tmp_path):
    """Equal local IDs in unrelated roots cannot share borrowed nodes, source paths or mutable records."""
    left_paths, left_nodes, left_edges = accepted(tmp_path / "left")
    right_paths, right_nodes, right_edges = accepted(tmp_path / "right")
    left = index_module._accepted_cpp_mapper(left_nodes, left_edges, root=tmp_path / "left")
    right = index_module._accepted_cpp_mapper(right_nodes, right_edges, root=tmp_path / "right")
    first = left(read_cpp(left_paths[0], tmp_path / "left"))
    second = right(read_cpp(right_paths[0], tmp_path / "right"))
    repeat = left(read_cpp(left_paths[0], tmp_path / "left"))
    assert first.accepted is repeat.accepted and first.paths is repeat.paths
    assert first.accepted is not second.accepted and first.paths is not second.paths
    assert first.functions is not repeat.functions and first.classes is not repeat.classes
    for node in right_nodes:
        assert second.accepted[node["id"]] is node
        assert first.accepted[node["id"]] is not node
    repeat.functions.clear()
    assert first.functions


@pytest.mark.parametrize("kind", ["ordinary", "malformed"])
def test_req_qml022_ac06_unmapped_or_rejected_source_never_constructs_index(tmp_path, monkeypatch, kind):
    """Deferred indexing keeps the established source admission/failure ordering."""
    path = tmp_path / ("keep.py" if kind == "ordinary" else "broken.hpp")
    path.write_text("def keep(): return 1" if kind == "ordinary" else "class Broken { Q_OBJECT void bad( };", encoding="utf-8")
    result = {"nodes": [], "edges": []}

    def forbidden(*args, **kwargs):
        raise AssertionError("source rejected before canonical index construction")

    monkeypatch.setattr(index_module, "accepted_cpp_index", forbidden)
    enrich_qt_cpp([path], [result], root=tmp_path, accepted_nodes=[], accepted_edges=[])
    assert not result["nodes"] and not result["edges"]
    assert bool(result.get("qml_failures")) is (kind == "malformed")


def test_req_qml022_ac06_index_containers_are_readonly_without_deepcopying_borrowed_facts(tmp_path):
    """Read-only ownership covers maps/parent sets, preserving original last-ID and object semantics."""
    paths, nodes, edges = accepted(tmp_path)
    duplicate = dict(nodes[0])
    duplicate["source_file"] = "replacement.hpp"
    cohort = [*nodes, duplicate]
    mapping = index_module._accepted_cpp_mapper(cohort, edges, root=tmp_path)(read_cpp(paths[0], tmp_path))
    assert mapping.accepted[duplicate["id"]] is duplicate
    assert mapping.nodes[-1] is duplicate and mapping.paths[id(duplicate)] == "replacement.hpp"
    with pytest.raises(TypeError):
        mapping.accepted["invented"] = duplicate
    with pytest.raises(TypeError):
        mapping.paths[id(duplicate)] = "invented.hpp"
    with pytest.raises(AttributeError):
        next(iter(mapping.parents.values())).add("invented")


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_index_failure_retains_products_and_recovery_matches_full(tmp_path, monkeypatch, operation):
    """A real index-boundary failure cannot publish scratch Qt facts or poison accepted state."""
    paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    path = paths[0]
    path.write_bytes(path.read_bytes().replace(b" void run();", b" void run();\n int added;"))

    def failure(*args, **kwargs):
        raise ValueError("isolated accepted-index backend detail")

    with monkeypatch.context() as scoped:
        scoped.setattr(index_module, "accepted_cpp_index", failure)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                manual_update(tmp_path, monkeypatch)
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert products(tmp_path) == before
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(initial) == unrelated(recovered)
    settled = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == settled
