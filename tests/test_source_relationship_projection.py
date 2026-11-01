"""INC127: builder acceptance and extra raw evidence share one coherent caller frame."""
from __future__ import annotations

from copy import deepcopy
import errno
import json
import os
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.ids import normalize_id
from tests.source_relationship_projection_helpers import (
    arcs, calls, imports, observations, readback, state, storage,
)


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_accepted_normalized_import_survives_original_view(tmp_path, profile, directed):
    """A real parser import with documented casing drift cannot disappear on export."""
    root = tmp_path / "corpus"
    raw, edge, target = imports(root, profile)
    edge["target"] = target.upper()
    assert edge["target"] != target and normalize_id(edge["target"]) == normalize_id(target)
    graph = build_from_json(raw, root=root, directed=directed)
    accepted = arcs(graph, "imports")
    assert len(accepted) == 1 and next(iter(accepted))[1] == target
    baseline = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(baseline))
    assert arcs(readback(baseline)[0], "imports") == accepted

    output = tmp_path / "original.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    loaded, _ = readback(output)
    assert arcs(loaded, "imports") == accepted
    # The caller's adopted projection remains usable for rebuild and repeat export.
    rebuilt = build_from_json(deepcopy(raw), root=root, directed=directed)
    assert arcs(rebuilt, "imports") == accepted
    assert to_json(rebuilt, {}, str(output), force=True, original_links=raw["edges"])
    assert arcs(readback(output)[0], "imports") == accepted


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac03_rejected_cross_family_call_cannot_return(tmp_path, profile, directed):
    """False Python-to-JSON inference stays rejected while a real Python call survives."""
    raw = storage({"nodes": [
        {"id": "caller", "label": "invoke", "type": "function", "source_file": "caller.py"},
        {"id": "json_format", "label": "format", "type": "field", "source_file": "config.json"},
        {"id": "python_helper", "label": "helper", "type": "function", "source_file": "helper.py"}],
        "edges": [{"source": "caller", "target": target, "relation": "calls", "context": "call",
                   "confidence": "INFERRED", "source_file": "caller.py", "source_location": "L1"}
                  for target in ("json_format", "python_helper")]}, profile)
    graph = build_from_json(raw, directed=directed)
    accepted = {("caller", "python_helper")}
    assert arcs(graph, "calls") == accepted
    output = tmp_path / "calls.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    loaded, _ = readback(output)
    assert arcs(loaded, "calls") == accepted
    rebuilt = build_from_json(deepcopy(raw), directed=directed)
    assert to_json(rebuilt, {}, str(output), force=True, original_links=raw["edges"])
    assert arcs(readback(output)[0], "calls") == accepted


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml010_ac02_import_cohort_admits_extracted_call_independent_of_order(tmp_path, profile, directed):
    """Only a valid import cohort may supply the external stub for an extracted call."""
    absent, _ = calls(profile)
    rejected = build_from_json(absent, directed=directed)
    assert "signal" not in rejected and not arcs(rejected, "calls")
    no_import = tmp_path / "no-import.json"
    assert to_json(rejected, {}, str(no_import), original_links=absent["edges"])
    assert not arcs(readback(no_import)[0], "calls")
    # Import-first is the existing positive control; caller-first exposes the defect.
    for import_first in (True, False):
        raw, caller = calls(profile, imported=True, import_first=import_first)
        graph = build_from_json(raw, directed=directed)
        expected = {(caller, "signal")}
        assert "signal" in graph and graph.nodes["signal"].get("external") is True
        assert arcs(graph, "calls") == expected
        output = tmp_path / f"imported-{import_first}.json"
        assert to_json(graph, {}, str(output), original_links=raw["edges"])
        assert arcs(readback(output)[0], "calls") == expected


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml018_ac04_extra_original_parallel_observations_remain_independent(tmp_path, profile, directed):
    """#3999's alternate raw view keeps extra observations and their own metadata/score."""
    root = tmp_path / "corpus"
    raw, edge, _ = imports(root, profile)
    edge["confidence_score"] = 0.73
    edge.pop("metadata", None)
    graph = build_from_json(raw, root=root, directed=directed)
    extra = {**deepcopy(edge), "context": "independent-import", "confidence_score": 0.42,
             "metadata": {"observation": "extra"}}
    reference = {**deepcopy(edge), "relation": "references", "context": "independent-reference",
                 "confidence_score": 0.21, "metadata": {"observation": "reference"}}
    supplied = [*deepcopy(raw["edges"]), extra, reference]
    before = deepcopy(supplied)
    output = tmp_path / "parallel.json"
    assert to_json(graph, {}, str(output), original_links=supplied)
    loaded, payload = readback(output)
    assert supplied == before
    assert arcs(loaded, "imports") == arcs(graph, "imports")
    records = [record for _, record in observations(payload)]
    for context, score, marker in (("independent-import", 0.42, "extra"),
                                    ("independent-reference", 0.21, "reference")):
        observed = [record for record in records if record.get("context") == context]
        assert len(observed) == 1
        assert observed[0]["confidence_score"] == score
        assert observed[0]["metadata"] == {"observation": marker}
    primary = [record for record in records if record.get("confidence_score") == 0.73]
    assert len(primary) == 1 and "metadata" not in primary[0]
    accepted = output.read_bytes()
    assert to_json(loaded, {}, str(output), force=True)
    if profile:
        assert output.read_bytes() == accepted
    else:
        # Legacy adoption may add storage keys/metadata, which are not source
        # evidence. Every original link attribute must still survive unchanged.
        repeated = readback(output)[1]
        def evidence(view):
            return sorted(json.dumps({k: v for k, v in link.items() if k != "key"}, sort_keys=True)
                          for link in view["links"])
        assert evidence(repeated) == evidence(payload)


@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml018_ac04_manual_legacy_original_view_remains_independent(tmp_path, directed):
    """A manual unpromised graph retains the established explicit-empty-view contract."""
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(("first", "second"))
    graph.add_edge("first", "second", relation="references")
    output = tmp_path / "manual.json"
    assert to_json(graph, {}, str(output), original_links=[])
    loaded, payload = readback(output)
    assert payload["links"] == [] and loaded.number_of_edges() == 0
    assert graph.number_of_edges() == 1


@pytest.mark.parametrize("force", [False, True], ids=["guarded", "forced"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
def test_req_qml018_ac04_original_view_write_failure_retains_and_recovers(tmp_path, monkeypatch, force, directed):
    """Actual replacement failure preserves accepted source state, then retry is idempotent."""
    root = tmp_path / "corpus"
    raw, _, _ = imports(root, True)
    graph = build_from_json(raw, root=root, directed=directed)
    output = tmp_path / "retained.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    accepted = output.read_bytes()
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before, original = state(graph), deepcopy(raw["edges"])
    replace, reached = os.replace, []

    def fail_replace(source, target):
        if Path(str(target).removeprefix("\\\\?\\")) == output:
            reached.append(True)
            raise OSError(errno.EIO, "injected original-view replacement failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail_replace)
        with pytest.raises(OSError, match="injected original-view replacement"):
            to_json(graph, {}, str(output), force=force, original_links=raw["edges"])
    assert reached == [True] and output.read_bytes() == accepted
    assert state(graph) == before and raw["edges"] == original
    assert to_json(graph, {}, str(output), force=force, original_links=raw["edges"])
    loaded, _ = readback(output)
    assert arcs(loaded, "imports") == arcs(graph, "imports")
    recovered = output.read_bytes()
    assert to_json(loaded, {}, str(output), force=True)
    assert output.read_bytes() == recovered
