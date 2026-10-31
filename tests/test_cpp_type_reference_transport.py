"""INC-QML-114: a raw alias or graph flag cannot erase a scoped restriction."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_type_reference_helpers import produce, source, unavailable


def payload(root):
    result = produce(root, source(), "direct")
    return {"nodes": result["nodes"], "edges": result["edges"], "links": deepcopy(result["edges"]),
            "directed": False, "multigraph": False}


def consume(value, boundary, *, directed=False):
    return build_from_json(value, directed=directed) if boundary == "build" else load_node_link_graph(value)


@pytest.mark.parametrize("boundary", ["build", "load"])
@pytest.mark.parametrize("field", ["directed", "multigraph"])
@pytest.mark.parametrize("bad", ["false", 1, 0, None, [], {}], ids=["string", "one", "zero", "null", "list", "dict"])
def test_req_qml014_ac03_typed_mode_flags_reject_before_input_mutation(tmp_path, boundary, field, bad):
    """Actual source promises require strict boolean mode flags, including unused ones."""
    value = payload(tmp_path)
    value[field] = bad
    before = deepcopy(value)
    with pytest.raises(ValueError, match="^CPP_REFERENCE_CONTEXT_INVALID:"):
        consume(value, boundary)
    assert value == before


@pytest.mark.parametrize("boundary", ["build", "load"])
@pytest.mark.parametrize("changed", ["edges", "links"])
@pytest.mark.parametrize("mismatch", ["promise_removed", "order", "evidence", "scalar_type", "multiplicity"])
def test_req_qml014_ac03_dual_alias_conflicts_cannot_select_an_unrestricted_view(tmp_path, boundary, changed, mismatch):
    """Each alias can be valid alone while disagreeing about source policy or evidence."""
    value = payload(tmp_path)
    links = value[changed]
    edge = unavailable({"edges": links})[0]
    if mismatch == "promise_removed":
        edge.pop("cpp_type_reference_version")
        edge["metadata"].pop("cpp_type_reference")
    elif mismatch == "order":
        links.reverse()
    elif mismatch == "evidence":
        edge["weight"] = 2.0
    elif mismatch == "scalar_type":
        edge["weight"] = True
    else:
        links.append(deepcopy(edge))
    before = deepcopy(value)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        consume(value, boundary)
    assert value == before


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("existing_profile,multigraph", [(False, False), (False, True), (True, True)])
def test_req_qml014_ac03_valid_dual_aliases_repeat_build_export_reload_in_one_source_frame(tmp_path, directed, existing_profile, multigraph):
    """Both accepted aliases follow existing root normalization, without stale absolute copies."""
    value = payload(tmp_path)
    value.update(directed=directed, multigraph=multigraph)
    if existing_profile:
        value["graph"] = {"graphify_source_relationships": {"contract_version": 1}}
    for iteration in range(3):
        graph = build_from_json(value, root=tmp_path, directed=directed)
        assert value["edges"] == value["links"]
        output = tmp_path / f"accepted-{iteration}.json"
        assert to_json(graph, {}, str(output), force=True, original_links=value["edges"])
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert len([edge for _, _, edge in restored.edges(data=True) if "cpp_type_reference_version" in edge]) == 1
        assert all(edge["source_file"] == "types.cpp" for edge in unavailable({"edges": value["links"]}))


@pytest.mark.parametrize("boundary", ["build", "load"])
def test_req_qml014_ac03_missing_flags_keep_existing_typed_defaults(tmp_path, boundary):
    """Absence has its existing default; it cannot be conflated with an explicit null flag."""
    value = payload(tmp_path)
    value.pop("directed")
    value.pop("multigraph")
    graph = consume(value, boundary)
    assert len([edge for _, _, edge in graph.edges(data=True) if "cpp_type_reference_version" in edge]) == 1


@pytest.mark.parametrize("bad", [None, 1, "false"])
def test_req_qml014_ac03_selected_build_mode_is_strict_for_promised_inputs(tmp_path, bad):
    """A consumer argument cannot bypass the same typed flag contract."""
    value = payload(tmp_path)
    before = deepcopy(value)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        consume(value, "build", directed=bad)
    assert value == before


@pytest.mark.parametrize("existing_profile", [False, True])
def test_req_qml014_ac03_dual_alias_owner_retains_actual_numeric_legacy_peer(tmp_path, existing_profile):
    """Existing numeric-ID coercion applies to one accepted list owner, including its untyped peer."""
    value = payload(tmp_path)
    if existing_profile:
        value.update(graph={"graphify_source_relationships": {"contract_version": 1}}, multigraph=True)
    target = value["nodes"][0]["id"]
    value["nodes"].append({"id": 7, "label": "Legacy", "file_type": "concept",
                           "source_file": "legacy.md", "source_location": "L1"})
    peer = {"source": 7, "target": target, "relation": "mentions", "confidence": "EXTRACTED",
            "source_file": "legacy.md", "source_location": "L1"}
    value["edges"].append(peer)
    value["links"].append(deepcopy(peer))
    for _ in range(3):
        graph = build_from_json(value, root=tmp_path)
        assert "7" in graph and value["edges"] == value["links"]
        assert value["edges"] is value["links"]
        assert next(edge for edge in value["links"] if edge["relation"] == "mentions")["source"] == "7"


def test_req_qml014_ac03_unpromised_legacy_modes_and_aliases_keep_existing_compatibility():
    """The new preflight cannot become a generic graph-format restriction."""
    from graphify.extractors.cpp_type_references import validate_type_reference_transport
    value = {"nodes": [{"id": "legacy", "label": "Legacy"}], "edges": [], "links": [],
             "directed": "false", "multigraph": None}
    before = deepcopy(value)
    assert validate_type_reference_transport(value, directed=json.loads("null")) is False
    assert value == before
    graph = load_node_link_graph(value)
    assert graph.is_directed() and not graph.is_multigraph()


@pytest.mark.parametrize("boundary", ["build", "load"])
def test_req_qml014_ac03_promised_scalar_edge_collection_is_not_legacy_absence(tmp_path, boundary):
    """A real promised record in place of a collection must fail before generic iteration/adoption."""
    value = payload(tmp_path)
    value["links"] = unavailable({"edges": value.pop("edges")})[0]
    before = deepcopy(value)
    with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
        consume(value, boundary)
    assert value == before
