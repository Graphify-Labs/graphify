"""INC130: merged explicit wire intent stays distinct from raw autoactivation."""
from __future__ import annotations

from copy import deepcopy

import pytest

from graphify.build import build, build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph
from tests.cpp_type_reference_helpers import produce, source, unavailable
from tests.source_relationship_projection_helpers import arcs, readback
from tests.test_source_relationship_legacy_metadata import typed


def wire():
    """An ordinary persisted chunk owns a profile without needing typed facts."""
    return {"nodes": [{"id": "plain", "label": "Plain", "type": "function",
                       "file_type": "code", "source_file": "plain.py",
                       "source_location": "L1", "_origin": "ast"}], "edges": [],
            "graph": {FIELD: {"contract_version": 1}}}


@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("dedup", [False, True], ids=["raw-merge", "dedup"])
@pytest.mark.parametrize("wire_first", [False, True], ids=["raw-first", "wire-first"])
def test_req_qml010_ac02_mixed_profile_keeps_explicit_cohort_and_raw_facts(
    tmp_path, directed, dedup, wire_first,
):
    """Real typed facts and an explicit peer survive either merge order and PATH reload."""
    raw, persisted = typed(tmp_path, directed), wire()
    identities = {node["id"] for node in raw["nodes"]} | {"plain"}
    local_ids = {node["id"] for node in raw["nodes"]
                 if "csharp_local_function" in node.get("metadata", {})}
    chunks = [persisted, raw] if wire_first else [raw, persisted]
    graph = build(chunks, directed=directed, root=tmp_path, dedup=dedup)
    assert is_source_graph(graph) and graph.is_directed() is directed
    assert set(graph) == identities and len(local_ids) == 2
    assert "graph" not in raw and persisted["graph"] == {FIELD: {"contract_version": 1}}
    for identity in local_ids:
        assert {edge["relation"] for _, _, edge in graph.edges(data=True)
                if edge["_tgt"] == identity} == {"contains", "calls"}
    # An explicitly selected merged frame remains canonical even for borrowed
    # raw records; this is not a new per-chunk input-immutability promise.
    assert all("_src" in edge and "_tgt" in edge for edge in raw["edges"])
    output = tmp_path / "mixed.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = readback(output)[0]
    assert set(reloaded) == identities and is_source_graph(reloaded)
    assert reloaded.is_directed() is directed
    for relation in {edge["relation"] for _, _, edge in graph.edges(data=True)}:
        assert arcs(reloaded, relation) == arcs(graph, relation)
    # The explicit profile remains authoritative after the last typed fact is
    # removed; an otherwise identical ordinary chunk retains legacy storage.
    assert is_source_graph(build([wire()], directed=directed, root=tmp_path, dedup=dedup))
    ordinary = wire()
    ordinary.pop("graph")
    assert not is_source_graph(build([ordinary], directed=directed, root=tmp_path, dedup=dedup))


@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("dedup", [False, True], ids=["raw-merge", "dedup"])
@pytest.mark.parametrize("wire_first", [False, True], ids=["raw-first", "wire-first"])
def test_req_qml022_ac06_raw_peer_cannot_mask_invalid_explicit_profile(
    tmp_path, directed, dedup, wire_first,
):
    """Either order rejects a boolean contract before input mutation or publication."""
    raw, persisted = typed(tmp_path, directed), wire()
    output = tmp_path / "retained.json"
    graph = build([deepcopy(raw), deepcopy(persisted)], directed=directed, root=tmp_path, dedup=dedup)
    assert to_json(graph, {}, str(output), force=True)
    accepted = output.read_bytes()
    persisted["graph"][FIELD]["contract_version"] = True
    chunks = [persisted, raw] if wire_first else [raw, persisted]
    before = deepcopy(chunks)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        build(chunks, directed=directed, root=tmp_path, dedup=dedup)
    assert chunks == before and output.read_bytes() == accepted


@pytest.mark.parametrize("aliases", [("from",), ("to",), ("from", "to")],
                         ids=["from", "to", "both"])
@pytest.mark.parametrize("carrier", ["raw", "marker", "wire"])
@pytest.mark.parametrize("boundary", ["direct", "combined"])
def test_req_qml010_ac03_cpp_physical_aliases_follow_owning_transport(tmp_path, aliases, carrier, boundary):
    """Present aliases follow physical raw slots or the adapter's canonical wire slots."""
    raw = produce(tmp_path, source(), "direct")
    edge = unavailable(raw)[0]
    logical = edge["source"], edge["target"]
    physical = tuple(reversed(logical))
    edge.update(source=physical[0], target=physical[1], _src=logical[0], _tgt=logical[1])
    for name in aliases:
        edge[name] = physical[0 if name == "from" else 1]
    if carrier != "raw":
        raw["graph"] = {FIELD: {"contract_version": 1}}
    if carrier == "wire":
        raw["multigraph"] = True
    # The direct persisted adapter needs an actual transport carrier. The
    # combined builder constructs a raw frame even from a persisted input chunk.
    adapted = carrier == "wire" and boundary == "direct"
    graph = (build_from_json(raw, root=tmp_path, dedup=False) if boundary == "direct"
             else build([raw], root=tmp_path, dedup=False))
    expected = logical if adapted else physical
    assert (edge["source"], edge["target"], edge["_src"], edge["_tgt"]) == (*expected, *logical)
    for name in aliases:
        assert edge[name] == expected[0 if name == "from" else 1]
    output = tmp_path / "aliases.json"
    assert to_json(graph, {}, str(output), force=True, original_links=raw["edges"])
    assert logical in arcs(readback(output)[0], "references")
    if not adapted:
        with pytest.raises(ValueError, match="CPP_REFERENCE_CONTEXT_INVALID"):
            load_node_link_graph({"nodes": raw["nodes"], "links": raw["edges"],
                                  "directed": True, "multigraph": False})
