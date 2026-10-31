"""INC-QML-73: source-owned free functions survive real durable update boundaries."""
from __future__ import annotations

import base64
import errno
import json
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.cpp_functions import free_definition_fact
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import clean, manual_update, normalized, published, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def fixture(root):
    """The same basename in two namespaces must remain separate after every reload."""
    source = root / "api.cpp"
    source.write_text("namespace First{int work(int value){return value;}}"
                      "namespace Second{int work(int value){return value;}}")
    caller = root / "caller.cpp"
    caller.write_text("namespace First{int caller(){return work(1);}}")
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n")
    return source, caller


def names(graph):
    values = {}
    for identity, data in graph.nodes(data=True):
        node = {**data, "id": identity}
        if free_definition_fact(node):
            values[identity] = base64.b64decode(node["metadata"]["cpp_function"]["qualified_name_b64"]).decode()
    return values


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_source_facts_and_targets_survive_cold_warm_export_reload(tmp_path, directed):
    """Real cache reuse and both export profiles preserve scope, source spans and role IDs."""
    paths = fixture(tmp_path)
    cold = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extract(list(paths), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm
    graph = build_from_json(warm, root=tmp_path, directed=directed)
    output = tmp_path / "published.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text()))
    assert set(names(restored).values()) == {"First::work", "Second::work", "First::caller"}
    by_id = names(restored)
    for source, target, data in restored.edges(data=True):
        if data.get("relation") == "calls":
            endpoints = (source, target) if directed else (data.get("_src", source), data.get("_tgt", target))
            assert {by_id.get(identity) for identity in endpoints} == {"First::caller", "First::work"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_changed_namespace_and_removed_body_match_full_scan(tmp_path, monkeypatch, operation):
    """Real updates retire obsolete salted IDs and cross-file edges without losing unrelated facts."""
    source, caller = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    old = set(names(initial))
    source.write_text("namespace Third{int work(int value){return value;}}")
    caller.write_text("namespace Third{int caller(){return work(1);}}")
    updated = run(tmp_path, monkeypatch, operation, [source, caller])
    assert set(names(updated).values()) == {"Third::work", "Third::caller"}
    assert old.isdisjoint(updated)
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert unrelated(updated) == unrelated(initial)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(updated)
    assert products(tmp_path) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_free_function_write_failure_preserves_prior_graph_and_recovers(tmp_path, monkeypatch, operation):
    """A real replacement failure cannot publish source facts without their matching graph/cache state."""
    source, _ = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    before = products(tmp_path)
    source.write_text("namespace Third{int work(int value){return value;}}")
    actual = os.replace

    def reject(source_path, target):
        if Path(target).resolve() == (tmp_path / "graphify-out/graph.json").resolve():
            raise OSError(errno.EIO, "isolated free-function publication failure")
        return actual(source_path, target)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", reject)
        if operation == "manual":
            with pytest.raises(SystemExit) as failure:
                manual_update(tmp_path, monkeypatch)
            assert failure.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert products(tmp_path) == before
    assert names(published(tmp_path)) == names(initial)
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert set(names(recovered).values()) == {"Third::work", "First::caller"}
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
