"""INC127: anchored import cohorts and delayed caller-frame adoption stay coherent."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors import cpp_type_references
from tests.source_relationship_projection_helpers import arcs, readback, storage


def frame(profile, directed, shared):
    """Accepted normalization and a rejected peer expose actual in-place adoption."""
    raw = storage({"nodes": [
        {"id": "source", "label": "source", "type": "file", "_origin": "ast",
         "source_file": "src/source.py"},
        {"id": "target", "label": "target", "type": "function", "_origin": "ast",
         "source_file": "src/target.py"},
        {"id": "json_field", "label": "format", "type": "field", "_origin": "ast",
         "source_file": "config.json"}], "edges": [
        {"source": "source", "target": "target", "relation": "references",
         "confidence": "EXTRACTED", "confidence_score": 0.37, "weight": "0.5",
         "source_file": "src\\source.py", "source_location": "L2",
         "target_file": "transient.py", "local_alias": "transient",
         "also_seen": [{"context": "secondary", "confidence": "EXTRACTED",
                        "confidence_score": 0.11, "source_file": "src\\source.py",
                        "source_location": "L3"}]},
        {"source": "source", "target": "json_field", "relation": "calls",
         "confidence": "INFERRED", "source_file": "src/source.py"}]}, profile)
    raw["links"] = raw["edges"] if shared else deepcopy(raw["edges"])
    raw["directed"] = directed
    if profile:
        # This persisted source transport takes the actual copied-adapter path.
        raw["multigraph"] = True
    return raw


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("reverse", [False, True], ids=["anchor-first", "dependent-first"])
def test_req_qml010_ac02_anchored_external_import_chain_is_input_order_independent(tmp_path, profile, directed, reverse):
    """The old builder accepted this chain; cohort pre-seeding cannot lose its second import."""
    links = [{"source": source, "target": target, "relation": "imports", "confidence": "EXTRACTED"}
             for source, target in (("anchor", "external_a"), ("external_a", "external_b"))]
    if reverse:
        links.reverse()
    raw = storage({"nodes": [{"id": "anchor", "label": "anchor", "type": "file",
                               "source_file": "anchor.py", "_origin": "ast"}], "edges": links}, profile)
    graph = build_from_json(raw, directed=directed)
    expected = {("anchor", "external_a"), ("external_a", "external_b")}
    assert arcs(graph, "imports") == expected
    assert graph.nodes["external_a"]["external"] is True
    assert graph.nodes["external_b"]["external"] is True
    output = tmp_path / "chain.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    assert arcs(readback(output)[0], "imports") == expected
    rebuilt = build_from_json(deepcopy(raw), directed=directed)
    assert arcs(rebuilt, "imports") == expected


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("shared", [False, True], ids=["equal-copies", "same-list"])
def test_req_qml010_ac02_held_alias_lists_and_dictionaries_adopt_one_accepted_frame(tmp_path, profile, directed, shared):
    """Adapter copies do not strand retained aliases or replace their original record objects."""
    raw = frame(profile, directed, shared)
    left, right = raw["edges"], raw["links"]
    first, second, rejected = left[0], right[0], left[1]
    rejected_before = deepcopy(rejected)
    graph = build_from_json(raw, directed=directed)
    assert raw["edges"] is left and raw["links"] is left
    assert left[0] is first and right[0] is second
    assert left == right and len(left) == len(right) == 1
    assert rejected == rejected_before
    for accepted in (first, second):
        assert accepted["weight"] == 0.5 and accepted["confidence_score"] == 0.37
        assert accepted["source_file"] == "src/source.py" and "metadata" not in accepted
        assert "target_file" not in accepted and "local_alias" not in accepted
        if profile:
            peer = accepted["also_seen"][0]
            assert peer["confidence_score"] == 0.11 and "metadata" not in peer
            assert peer["source_file"] == "src/source.py"
    output = tmp_path / "held.json"
    for supplied in (left, right):
        assert to_json(graph, {}, str(output), force=True, original_links=supplied)
        loaded, _ = readback(output)
        assert arcs(loaded, "references") == {("source", "target")} and not arcs(loaded, "calls")


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("shared", [False, True], ids=["equal-copies", "same-list"])
def test_req_qml018_ac04_final_validation_failure_precedes_frame_adoption(tmp_path, monkeypatch, profile, directed, shared):
    """A real final validator runs before its injected failure; borrowed edge state is retained."""
    raw = frame(profile, directed, shared)
    left, right = raw["edges"], raw["links"]
    first, second = left[0], right[0]
    before = deepcopy((left, right))
    actual, reached = cpp_type_references.validate_type_reference_graph, []

    def fail_after_validation(graph):
        actual(graph)
        assert arcs(graph, "references") == {("source", "target")} and not arcs(graph, "calls")
        reached.append(True)
        raise ValueError("injected final accepted-frame validation failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(cpp_type_references, "validate_type_reference_graph", fail_after_validation)
        with pytest.raises(ValueError, match="injected final accepted-frame validation"):
            build_from_json(raw, directed=directed)
    # Nodes and earlier legacy normalizer repairs retain their established owner;
    # this assertion concerns only the new delayed link/list adoption boundary.
    assert reached == [True] and (left, right) == before
    assert raw["edges"] is left and raw["links"] is right
    assert left[0] is first and right[0] is second
    recovered = build_from_json(raw, directed=directed)
    assert raw["edges"] is raw["links"] is left and len(left) == len(right) == 1
    output = tmp_path / "recovered.json"
    assert to_json(recovered, {}, str(output), original_links=right)
    assert arcs(readback(output)[0], "references") == {("source", "target")}


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("kind", ["cycle", "dangling-source", "call-only"], ids=["unanchored-cycle", "missing-source", "call-only"])
def test_req_qml010_ac03_unanchored_cohorts_cannot_grant_external_targets(tmp_path, profile, directed, kind):
    """No source anchor means no external target authority, even for a complete cycle."""
    links = [{"source": "anchor", "target": "external_a", "relation": "calls", "confidence": "EXTRACTED"}]
    if kind == "cycle":
        links += [{"source": source, "target": target, "relation": "imports", "confidence": "EXTRACTED"}
                  for source, target in (("external_a", "external_b"), ("external_b", "external_a"))]
    elif kind == "dangling-source":
        links.append({"source": "missing", "target": "external_a", "relation": "imports", "confidence": "EXTRACTED"})
    raw = storage({"nodes": [{"id": "anchor", "label": "anchor", "type": "file",
                               "source_file": "anchor.py", "_origin": "ast"}], "edges": links}, profile)
    graph = build_from_json(raw, directed=directed)
    assert set(graph) == {"anchor"} and graph.number_of_edges() == 0
    output = tmp_path / "unanchored.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    loaded, _ = readback(output)
    assert set(loaded) == {"anchor"} and loaded.number_of_edges() == 0
