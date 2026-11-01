"""INC117: every selected source transport validates its complete parent cohort."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.cpp_type_references import is_type_reference_unavailable
from graphify.source_relationships import is_source_graph
from tests.cpp_type_reference_helpers import produce as cpp_produce, source as cpp_source, unavailable
from tests.source_observation_helpers import produce, reference, state


@pytest.mark.parametrize("damage", ["missing", "blank", "list", "source_bool", "target_bool", "source_list", "partial", "foreign"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml014_ac04_source_override_parent_shape_rejects_before_write(tmp_path, damage, force):
    """Malformed parent arcs cannot be published as a successful but unloadable source graph."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    graph.add_node(1, label="numeric control")
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    links = [{**deepcopy(edge), "source": left, "target": right} for left, right, edge in graph.edges(data=True)]
    edge = next(item for item in links if item.get("context") == "field")
    if damage == "missing":
        edge.pop("relation")
    elif damage in {"blank", "list"}:
        edge["relation"] = " " if damage == "blank" else []
    elif damage == "source_bool":
        edge.update(source=True, _src=True)
    elif damage == "target_bool":
        edge.update(target=True, _tgt=True)
    elif damage == "source_list":
        edge["source"] = []
    elif damage == "partial":
        edge.pop("_src")
    else:
        edge["_src"] = "foreign"
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph), deepcopy(links)
    assert to_json(graph, {}, str(output), force=force, original_links=links) is False
    assert (state(graph), links) == before and output.read_bytes() == accepted


@pytest.mark.parametrize("relation", [None, " ", []])
def test_req_qml014_ac04_graph_derived_parent_relation_is_validated(tmp_path, relation):
    """Graph-derived output has the same parent contract as a supplied original view."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    reference(graph)["relation"] = relation
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph)
    assert to_json(graph, {}, str(output), force=True) is False
    assert state(graph) == before and output.read_bytes() == accepted


@pytest.mark.parametrize("damage", ["unused_record", "directed", "multigraph", "bool_int_alias"])
def test_req_qml014_ac04_autoactivated_source_checks_unused_aliases_and_modes(tmp_path, damage):
    """Actual local-source activation validates both raw aliases before normalization can hide one."""
    raw = produce(tmp_path)
    raw["links"] = deepcopy(raw["edges"])
    if damage == "unused_record":
        raw["links"][0]["also_seen"] = [{"source": "foreign"}]
    elif damage == "bool_int_alias":
        raw["edges"][0]["observation_flag"] = 1
        raw["links"][0]["observation_flag"] = True
    else:
        raw[damage] = "false"
    before = deepcopy(raw)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        build_from_json(raw, root=tmp_path)
    assert raw == before


def test_req_qml014_ac04_secondary_cpp_promise_without_source_carrier_rejects(tmp_path):
    """Unsupported secondary promises cannot be stripped by the ordinary legacy evidence fold."""
    raw = cpp_produce(tmp_path, cpp_source(), "direct")
    edge = unavailable(raw)[0]
    secondary = {key: deepcopy(value) for key, value in edge.items()
                 if key not in {"source", "target", "relation", "_src", "_tgt", "key"}}
    for key in ("metadata", "cpp_type_reference_version"):
        edge.pop(key)
    edge["also_seen"] = [secondary]
    before = deepcopy(raw)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        build_from_json(raw, root=tmp_path)
    assert raw == before


def test_req_qml014_ac04_invalid_graph_duplicate_arc_rejects_without_loader_repair(tmp_path):
    """An explicitly marked v1 Graph cannot publish competing keys for one logical arc."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    edge = reference(graph)
    graph.add_edge(edge["_src"], edge["_tgt"], key="competing", **deepcopy(edge))
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph)
    assert to_json(graph, {}, str(output), force=True) is False
    assert state(graph) == before and output.read_bytes() == accepted


@pytest.mark.parametrize("force", [False, True])
def test_req_qml014_ac04_legacy_cpp_override_cannot_move_known_promise_to_unsupported_secondary(tmp_path, force):
    """An original-view rewrite cannot produce a carrier that the strict loader must reject."""
    raw = cpp_produce(tmp_path, cpp_source(), "direct")
    graph = build_from_json(raw, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    links = deepcopy(raw["edges"])
    edge = unavailable({"edges": links})[0]
    record = {key: deepcopy(value) for key, value in edge.items()
              if key not in {"source", "target", "relation", "_src", "_tgt", "key", "also_seen"}}
    edge.pop("metadata")
    edge.pop("cpp_type_reference_version")
    edge["also_seen"] = [record]
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph), deepcopy(links)
    assert to_json(graph, {}, str(output), force=force, original_links=links) is False
    assert (state(graph), links) == before and output.read_bytes() == accepted


def test_req_qml014_ac04_legacy_cpp_primary_keeps_unpromised_history_compatibility(tmp_path):
    """A primary promise keeps the existing non-source four-field history without format promotion."""
    raw = cpp_produce(tmp_path, cpp_source(), "direct")
    edge = unavailable(raw)[0]
    edge["also_seen"] = [None, {"confidence": "INFERRED", "source_file": "types.cpp", "source_location": "L1",
                                "context": "legacy-only", "metadata": {"unrelated": True}}]
    graph = build_from_json(raw, root=tmp_path)
    assert not is_source_graph(graph)
    current = next(data for _, _, data in graph.edges(data=True) if is_type_reference_unavailable(data))
    assert current["also_seen"] == [{"confidence": "INFERRED", "source_file": "types.cpp", "source_location": "L1"}]
