"""INC-QML-84: source-local callables retain ownership and calls through persistence."""
from __future__ import annotations

import json
import errno
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from tests.test_csharp_lexical_calls import local_functions
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, published, run, unrelated
from tests.test_qt_semantic_correction_updates import products


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_local_containment_and_call_remain_distinct_after_build_reload(tmp_path, directed):
    """One endpoint pair has two real source relationships; assembly/export must retain both."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void Local(){} Local();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    original = {edge["relation"] for edge in result["edges"] if edge["source"] == caller and edge["target"] == local["id"]}
    assert original == {"contains", "calls"}
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "published.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text()))
    relations = {data["relation"] for source, target, data in restored.edges(data=True)
                 if {source, target} == {caller, local["id"]}}
    assert relations == {"contains", "calls"}


def fixture(root):
    path = root / "Data.cs"
    path.write_text("namespace App{partial class Holder{void Use(){void Local(int value){} Local(1);}}}")
    (root / "Other.cs").write_text("namespace App{partial class Holder{int value;void Outsider(){Local(1);}}}")
    (root / "keep.py").write_text("def helper():return 1\n\ndef retained():return helper()\n")
    return path


def locals_in(graph):
    return {identity: data for identity, data in graph.nodes(data=True)
            if data.get("metadata", {}).get("csharp_local_function")}


def test_req_qml022_ac06_local_facts_and_calls_match_cold_warm_cached_extraction(tmp_path):
    """A cached producer retains actual local IDs and no borrowed global-name visibility."""
    fixture(tmp_path)
    paths = [tmp_path / "Data.cs", tmp_path / "Other.cs"]
    cold = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm
    (local,) = local_functions(warm)
    callers = {node["id"]: node["label"] for node in warm["nodes"]}
    assert {callers[edge["source"]] for edge in warm["edges"]
            if edge["target"] == local["id"] and edge["relation"] == "calls"} == {".Use()"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_local_edits_retire_stale_source_ids_and_match_full_scan(tmp_path, monkeypatch, operation):
    """The actual C# cohort update preserves partial owners and unrelated-language graph facts."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    old_ids = set(locals_in(initial))
    assert len(old_ids) == 1
    path.write_text("namespace App{partial class Holder{void Use(){void Renamed(int other){} Renamed(2);}}}")
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert old_ids.isdisjoint(updated) and len(locals_in(updated)) == 1
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(initial) == unrelated(updated)
    durable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == durable


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_local_write_failure_preserves_accepted_graph_then_recovers(tmp_path, monkeypatch, operation):
    """Failure at the real replacement boundary cannot publish half of a scope/owner change."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    path.write_text("namespace App{partial class Holder{void Use(){void Renamed(){} Renamed();}}}")
    actual = os.replace

    def reject(source, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated C# local-source publication failure")
        return actual(source, target)

    with monkeypatch.context() as scope:
        scope.setattr(os, "replace", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert products(tmp_path) == before
    assert locals_in(published(tmp_path)) == locals_in(initial)
    recovered = run(tmp_path, monkeypatch, operation, [path])
    assert {data["label"] for data in locals_in(recovered).values()} == {"Renamed()"}
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_deleted_local_owner_removes_all_stale_facts_and_settles(tmp_path, monkeypatch, operation):
    """Deleting the actual source owner must retire locals and their parallel relations together."""
    path = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    old_ids = set(locals_in(initial))
    assert len(old_ids) == 1
    path.unlink()
    updated = run(tmp_path, monkeypatch, operation, [path])
    assert not locals_in(updated) and old_ids.isdisjoint(updated)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".deleted"))
    assert unrelated(initial) == unrelated(updated)
    durable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == durable
