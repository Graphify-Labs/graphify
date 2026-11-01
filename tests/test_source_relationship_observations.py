"""INC117: one logical source arc retains all complete source observations."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.build import add_source_relationship, build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.paths import load_node_link_graph
from graphify.source_relationships import is_source_graph, storage_key
from tests.source_observation_helpers import canonical, observations, produce, reference


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("preserved", [False, True])
def test_req_qml022_ac06_complete_source_observations_survive_roundtrip(tmp_path, directed, mode, preserved):
    """Actual generic/field evidence survives build, original-view export, reload and rebuild."""
    raw = produce(tmp_path, mode=mode)
    graph = build_from_json(raw, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    links = raw["edges"] if preserved else None
    assert to_json(graph, {}, str(output), original_links=links)
    loaded = load_node_link_graph(output)
    rebuilt = build_from_json(json.loads(output.read_text()), root=tmp_path, directed=directed)
    for current in (graph, loaded, rebuilt):
        assert is_source_graph(current)
        evidence = observations(reference(current))
        assert {entry.get("context") for entry in evidence} == {"field", "generic_arg"}
        assert {entry["source_location"] for entry in evidence} == {"L3", "L4"}
        assert all(entry["metadata"] == {"ref_token": "Token"} for entry in evidence)
        assert all(not (set(entry) & {"source", "target", "relation", "key", "_src", "_tgt", "also_seen"})
                   for entry in reference(current).get("also_seen", []))
        for left, right, key, data in current.edges(keys=True, data=True):
            assert key == storage_key(data.get("_src", left), data.get("_tgt", right), data["relation"])
    accepted = output.read_bytes()
    assert to_json(loaded, {}, str(output), force=True)
    assert output.read_bytes() == accepted


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_identical_evidence_deduplicates_without_losing_distinct_metadata(tmp_path, directed):
    """Exact repeated copies collapse as evidence while original metadata and contexts remain distinct."""
    raw = produce(tmp_path)
    extra = next(edge for edge in raw["edges"] if edge.get("context") == "generic_arg")
    raw["edges"].append(deepcopy(extra))
    different = deepcopy(extra)
    different["metadata"]["independent"] = {"roles": ["parameter"], "span": [1, 2]}
    raw["edges"].append(different)
    graph = build_from_json(raw, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    loaded = load_node_link_graph(output)
    evidence = observations(reference(loaded))
    assert len(evidence) == 3
    assert len({canonical({key: value for key, value in entry.items()
                           if key not in {"_src", "_tgt", "relation"}}) for entry in evidence}) == 3
    assert any(entry.get("metadata", {}).get("independent") == {"roles": ["parameter"], "span": [1, 2]}
               for entry in evidence)
    different["metadata"]["independent"]["roles"].clear()
    assert any(entry.get("metadata", {}).get("independent", {}).get("roles") == ["parameter"]
               for entry in evidence)


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_legacy_original_parallel_evidence_remains_supported(tmp_path, directed):
    """Without typed source activation, the established legacy original-view behavior remains."""
    raw = produce(tmp_path, local=False)
    graph = build_from_json(raw, root=tmp_path, directed=directed)
    assert not graph.is_multigraph()
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    assert load_node_link_graph(output).number_of_edges() == len(raw["edges"])


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_actual_opposite_and_different_relations_keep_distinct_keys(tmp_path, directed):
    """Real reciprocal fields and inheritance retain independent directed relationship identities."""
    path = tmp_path / "Data.cs"
    path.write_bytes(b"class Token {Panel back;}\nclass Panel:Token {Token value;"
                     b"void Use(){void Nested(){}Nested();}}\n")
    raw = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(raw, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), original_links=raw["edges"])
    loaded = load_node_link_graph(output)
    assert is_source_graph(loaded)
    names = {node["label"]: identity for identity, node in loaded.nodes(data=True)}
    panel, token = names["Panel"], names["Token"]
    arcs = {(edge.get("_src", left), edge.get("_tgt", right), edge["relation"])
            for left, right, edge in loaded.edges(data=True) if {left, right} == {panel, token}}
    assert arcs == {(panel, token, "inherits"), (panel, token, "references"), (token, panel, "references")}
    keys = [key for left, right, key in loaded.edges(keys=True) if {left, right} == {panel, token}]
    assert len(keys) == len(set(keys)) == 3


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_execution_aggregate_keeps_original_type_only_evidence(tmp_path, reverse, directed):
    """Existing runtime-import precedence clears only aggregate authority, retaining original records."""
    graph = build_from_json(produce(tmp_path), root=tmp_path, directed=directed)
    assert is_source_graph(graph)
    graph.add_nodes_from(("importer", "module"))
    typed = {"relation": "imports", "confidence": "EXTRACTED", "context": "guarded",
             "source_file": "Data.cs", "source_location": "L1", "type_only": True,
             "metadata": {"written": "guarded source"}}
    runtime = {"relation": "imports", "confidence": "EXTRACTED", "context": "runtime",
               "source_file": "Data.cs", "source_location": "L2", "metadata": {"written": "runtime source"}}
    order = (runtime, typed) if reverse else (typed, runtime)
    before = deepcopy(order)
    for row in order:
        add_source_relationship(graph, "importer", "module", row)
    key = storage_key("importer", "module", "imports")
    edge = graph.edges["importer", "module", key]
    assert not edge.get("type_only")
    assert any(row.get("type_only") is True and row.get("metadata") == typed["metadata"] for row in observations(edge))
    assert any(row.get("context") == "runtime" and not row.get("type_only") for row in observations(edge))
    accepted = canonical(edge)
    for row in order:
        add_source_relationship(graph, "importer", "module", row)
    assert canonical(edge) == accepted and order == before
