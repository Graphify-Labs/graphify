"""INC117: actual raw manual/watch publication retains observation cohorts."""
from __future__ import annotations

import json

import pytest

from graphify import cache
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph
from graphify.watch import _extractor_epoch, _rebuild_code
from tests.qt_publication_faults import publication_fault
from tests.source_observation_helpers import observations, produce, reference
from tests.test_qt_final_incremental_parity import manual_update, run
from tests.test_qt_semantic_correction_updates import products


def contexts(graph):
    return {(entry.get("context"), entry.get("source_location"), entry.get("metadata", {}).get("ref_token"))
            for entry in observations(reference(graph))}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_raw_updates_keep_observations_after_last_local_removal(tmp_path, monkeypatch, operation):
    """Accepted source storage survives activation removal, exact cold-context rebuild and repeat."""
    produce(tmp_path)
    source = tmp_path / "Data.cs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert contexts(initial) == {("field", "L4", "Token"), ("generic_arg", "L3", "Token")}
    old = {identity for identity, node in initial.nodes(data=True) if "csharp_local_function" in node.get("metadata", {})}
    assert old
    source.write_bytes(source.read_bytes().replace(b"void Nested() {} Nested();", b""))
    changed = run(tmp_path, monkeypatch, operation, [source])
    assert not set(changed) & old and is_source_graph(changed)
    assert contexts(changed) == contexts(initial)
    # This full comparison uses the accepted storage profile, not a claim that a
    # first-ever unmarked legacy analysis opts into the new source profile.
    fresh = extract([source], root=tmp_path, cache_root=tmp_path / ".cold-cache", parallel=False)
    fresh["graph"] = {FIELD: {"contract_version": 1}}
    cold = build_from_json(fresh, root=tmp_path)
    output = tmp_path / "graphify-out/cold-view.json"
    assert to_json(cold, {}, str(output))
    assert contexts(load_node_link_graph(output)) == contexts(changed)
    accepted = products(tmp_path)
    repeated = run(tmp_path, monkeypatch, operation, [])
    assert contexts(repeated) == contexts(changed) and products(tmp_path) == accepted


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml014_ac04_raw_observation_failure_retains_products_and_recovers(tmp_path, monkeypatch, operation):
    """A real publication fault retains every accepted product, then recovery restores both contexts."""
    produce(tmp_path)
    source = tmp_path / "Data.cs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    before = source.read_bytes()
    source.write_bytes(before.replace(b"Token value;", b"Token renamed;"))
    with publication_fault(tmp_path / "graphify-out/graph.json", "replace", monkeypatch) as fault:
        if operation == "manual":
            with pytest.raises(SystemExit):
                manual_update(tmp_path, monkeypatch)
        else:
            assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True) is False
    assert fault.hits and products(tmp_path) == accepted
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert contexts(recovered) == contexts(initial)
    stable = products(tmp_path)
    assert contexts(run(tmp_path, monkeypatch, operation, [])) == contexts(recovered)
    assert products(tmp_path) == stable and not list((tmp_path / "graphify-out").glob(".gfy-*.tmp"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_unchanged_old_epoch_observation_loss_refreshes_and_recovers(tmp_path, monkeypatch, operation):
    """A valid old37 graph/state cannot retain its lost field observation without a source edit."""
    produce(tmp_path)
    source = tmp_path / "Data.cs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    run(tmp_path, monkeypatch, operation)
    graph_path = tmp_path / "graphify-out/graph.json"
    state_path = tmp_path / "graphify-out/.graphify_build_state.json"
    data = json.loads(graph_path.read_text())
    for edge in data.get("links", data.get("edges", [])):
        if edge.get("relation") == "references":
            edge.pop("also_seen", None)
            edge.update(context="generic_arg", source_location="L3")
    graph_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    previous = json.loads(state_path.read_text())
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 37)
        previous["epoch"] = _extractor_epoch()
    previous.update(graph_mtime_ns=graph_path.stat().st_mtime_ns, graph_size=graph_path.stat().st_size)
    state_path.write_text(json.dumps(previous), encoding="utf-8")
    before = products(tmp_path)
    source_before = source.read_bytes(), source.stat().st_mtime_ns
    with publication_fault(graph_path, "replace", monkeypatch) as fault:
        if operation == "manual":
            with pytest.raises(SystemExit):
                manual_update(tmp_path, monkeypatch)
        else:
            # A full watcher rescan checks the epoch. An explicit empty event
            # set means no tracked changes and intentionally skips extraction.
            assert _rebuild_code(tmp_path, no_cluster=True) is False
    assert fault.hits and products(tmp_path) == before
    repaired = run(tmp_path, monkeypatch, operation)
    assert contexts(repaired) == {("field", "L4", "Token"), ("generic_arg", "L3", "Token")}
    assert json.loads(state_path.read_text())["epoch"] == _extractor_epoch()
    assert (source.read_bytes(), source.stat().st_mtime_ns) == source_before
    accepted = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == accepted
