"""INC-QML-114: corrupt rejection promises cannot reenable guessed targets."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import _rewire_unique_stub_nodes
from graphify.extractors.cpp_type_references import validate_type_references
from graphify.paths import load_node_link_graph
from tests.cpp_type_reference_helpers import produce, source, unavailable


def damage(result, case):
    """Mutate one real producer promise; all other source/provenance remains exact."""
    edge = unavailable(result)[0]
    fact = edge["metadata"]["cpp_type_reference"]
    target = next(node for node in result["nodes"] if node["id"] == edge["target"])
    if case == "marker_missing":
        edge.pop("cpp_type_reference_version")
    elif case == "metadata_missing":
        edge.pop("metadata")
    elif case == "family_missing":
        edge["metadata"].pop("cpp_type_reference")
    elif case.startswith("edge:"):
        key = case.split(":", 1)[1]
        edge[key] = {"relation": [], "confidence": {}, "source_file": [],
                     "source_location": "L" + "9" * 100,
                     "cpp_type_reference_version": True}[key]
    elif case.startswith("span:"):
        key = case.split(":", 1)[1]
        fact["type_span"][key] = True if key == "start_byte" else -1
    elif case == "span_extra":
        fact["type_span"]["extra"] = 0
    elif case == "foreign_markers":
        edge["_src"], edge["_tgt"] = "foreign", edge["target"]
    elif case == "partial_markers":
        edge["_src"] = edge["source"]
    elif case == "target_sourced":
        target["source_file"], target["source_location"] = "foreign.cpp", "L1"
    elif case == "target_other_literal":
        target["label"] = "Other"
    elif case in {"target_list_label", "target_dict_label"}:
        target["label"] = [] if case == "target_list_label" else {}
    elif case == "foreign_source_file":
        edge["source_file"] = "foreign.cpp"
    elif case == "target_list_id":
        edge["target"] = []
    elif case == "target_missing":
        result["nodes"].remove(target)
    elif case == "target_duplicate":
        result["nodes"].append(deepcopy(target))
    elif case == "source_missing":
        result["nodes"] = [node for node in result["nodes"] if node["id"] != edge["source"]]
    elif case == "family_null":
        edge["metadata"]["cpp_type_reference"] = None
    elif case == "member_missing":
        fact.pop("scope_complete")
    else:
        key, value = {
            "nested_version_bool": ("contract_version", True),
            "resolution_list": ("resolution", []),
            "name_bad_b64": ("raw_name_b64", "!!"),
            "name_oversize": ("raw_name_b64", "A" * 516),
            "name_invalid_utf8": ("raw_name_b64", "/w=="),
            "name_not_identifier": ("raw_name_b64", "IUZvbyE="),
            "name_noncanonical_b64": ("raw_name_b64", "Q291bnR="),
            "scope_null_complete": ("lexical_scope_b64", None),
            "scope_boolean": ("scope_complete", 1),
            "scope_list": ("scope_complete", []),
            "lookup_boolean": ("lookup_complete", 1),
            "lookup_null_complete": ("lookup_b64", None),
            "lookup_bad_b64": ("lookup_b64", "!!"),
            "span_list": ("type_span", []),
        }[case]
        fact[key] = value
    result["edges"] = [other for other in result["edges"] if other is not edge] + [edge]
    return result


CASES = ["marker_missing", "metadata_missing", "family_missing", "family_null", "member_missing",
         "edge:cpp_type_reference_version", "nested_version_bool", "resolution_list", "name_bad_b64",
         "name_oversize", "name_invalid_utf8", "name_not_identifier", "name_noncanonical_b64",
         "scope_null_complete", "scope_boolean", "scope_list", "lookup_boolean",
         "lookup_null_complete", "lookup_bad_b64", "span_list", "span_extra",
         "span:start_byte", "span:end_byte", "span:start_row", "span:end_column", "edge:relation",
         "edge:confidence", "edge:source_file", "edge:source_location", "foreign_markers", "partial_markers",
         "target_sourced", "target_other_literal", "target_list_label", "target_dict_label", "foreign_source_file",
         "target_missing", "target_duplicate", "target_list_id", "source_missing"]


@pytest.mark.parametrize("case", CASES)
def test_req_qml014_ac03_promised_context_is_validated_before_any_rewire(tmp_path, case):
    """A later corrupt peer cannot let an earlier valid unmarked edge mutate first."""
    result = damage(produce(tmp_path, source("class"), "direct"), case)
    before = deepcopy(result)
    for owner in (validate_type_references, _rewire_unique_stub_nodes):
        with pytest.raises(ValueError, match="^CPP_REFERENCE_CONTEXT_INVALID:"):
            owner(result["nodes"], result["edges"])
        assert result == before


@pytest.mark.parametrize("boundary", ["build", "links_load", "edges_load"])
def test_req_qml014_ac03_raw_public_consumers_reject_partial_context_before_adoption(tmp_path, boundary):
    """Actual raw dictionaries fail at their public owner, without repaired metadata."""
    result = produce(tmp_path, source(), "direct")
    result = damage(result, "marker_missing")
    before = deepcopy(result)
    if boundary == "build":
        with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
            build_from_json(result, root=tmp_path)
    else:
        key = "links" if boundary == "links_load" else "edges"
        payload = {"nodes": result["nodes"], key: result["edges"], "directed": False, "multigraph": False}
        with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
            load_node_link_graph(payload)
    assert result == before


@pytest.mark.parametrize("boundary", ["build", "load"])
@pytest.mark.parametrize("corrupted", ["edges", "links"])
def test_req_qml014_ac03_both_raw_edge_aliases_are_validated_even_when_one_is_unused(tmp_path, boundary, corrupted):
    """An ignored alias cannot hide a broken independent promise behind a valid collection."""
    result = produce(tmp_path, source(), "direct")
    payload = {"nodes": result["nodes"], "edges": deepcopy(result["edges"]), "links": deepcopy(result["edges"]),
               "directed": False, "multigraph": False}
    unavailable({"edges": payload[corrupted]})[0].pop("cpp_type_reference_version")
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        build_from_json(payload) if boundary == "build" else load_node_link_graph(payload)
    assert payload == before


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("carrier", ["graph", "original_links"])
def test_req_qml014_ac03_export_context_failure_preserves_real_existing_json(tmp_path, force, carrier):
    """Force and supplied raw links cannot bypass pre-write context integrity."""
    result = produce(tmp_path, source(), "direct")
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True, original_links=result["edges"])
    accepted = output.read_bytes()
    links = None
    if carrier == "graph":
        edge = next(data for _, _, data in graph.edges(data=True) if "cpp_type_reference_version" in data)
        edge.pop("metadata")
    else:
        links = damage(deepcopy(result), "marker_missing")["edges"]
    # Rejection precedes the existing accounting owner as well as disk output;
    # failed publication must not consume the accepted caller's counters/data.
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = deepcopy((graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True)), links))
    assert to_json(graph, {}, str(output), force=force, original_links=links) is False
    assert output.read_bytes() == accepted
    assert (graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True)), links) == before
    assert isinstance(json.loads(accepted), dict)


def test_req_qml014_ac03_legacy_absence_and_valid_reversed_direction_keep_existing_contract(tmp_path):
    """Only typed promises constrain loading; accepted explicit undirected direction remains exact."""
    result = produce(tmp_path, source(), "direct")
    validate_type_references(result["nodes"], result["edges"])
    edge = unavailable(result)[0]
    original = edge["source"], edge["target"]
    edge["_src"], edge["_tgt"] = original
    edge["source"], edge["target"] = reversed(original)
    validate_type_references(result["nodes"], result["edges"])
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        validate_type_references(result["nodes"], result["edges"], directed=True)
    validate_type_references(None, None)
    validate_type_references([], [{"source": "legacy", "target": "unknown"}])
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        validate_type_references(result["nodes"], edge)


@pytest.mark.parametrize("boundary", ["rewire", "build", "load"])
def test_req_qml014_ac03_undirected_reversed_storage_preserves_actual_reference_direction(tmp_path, boundary):
    """Physical undirected storage is not a second source lookup or endpoint authority."""
    result = produce(tmp_path, source(), "direct")
    edge = unavailable(result)[0]
    original = edge["source"], edge["target"]
    edge["_src"], edge["_tgt"] = original
    edge["source"], edge["target"] = reversed(original)
    if boundary == "rewire":
        _rewire_unique_stub_nodes(result["nodes"], result["edges"])
        assert (edge["source"], edge["target"], edge["_src"], edge["_tgt"]) == (*reversed(original), *original)
        validate_type_references(result["nodes"], result["edges"])
        return
    if boundary == "build":
        graph = build_from_json(result, root=tmp_path)
    else:
        graph = load_node_link_graph({"nodes": result["nodes"], "links": result["edges"],
                                      "directed": False, "multigraph": False})
    marked = [data for _, _, data in graph.edges(data=True) if "cpp_type_reference_version" in data]
    assert len(marked) == 1 and (marked[0]["_src"], marked[0]["_tgt"]) == original
    # The same reversed explicit pair contradicts a directed stored arc.
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        load_node_link_graph({"nodes": result["nodes"], "links": result["edges"],
                              "directed": True, "multigraph": False})


@pytest.mark.parametrize("boundary", ["legacy_nondict", "promised_nodes", "incomplete_lookup"])
def test_req_qml014_ac03_legacy_and_promised_collection_boundaries_remain_distinct(tmp_path, boundary):
    """Legacy absence stays compatible; malformed promised collections/payloads fail read-only."""
    if boundary == "legacy_nondict":
        validate_type_references([], [None])
        return
    result = produce(tmp_path, source(), "direct")
    if boundary == "incomplete_lookup":
        fact = unavailable(result)[0]["metadata"]["cpp_type_reference"]
        fact["lookup_complete"] = False
    before = deepcopy(result)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        validate_type_references(None if boundary == "promised_nodes" else result["nodes"], result["edges"])
    assert result == before
