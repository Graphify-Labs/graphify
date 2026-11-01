"""INC-QML-89 typed storage retains source facts without changing legacy graphs."""
from __future__ import annotations

import copy

import networkx as nx
import pytest

from graphify.build import build, build_from_json, prefix_graph_for_global
from graphify.extract import extract
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph, storage_key


def fixture(tmp_path):
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void Local(){} Local();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    local = next(node["id"] for node in result["nodes"] if "csharp_local_function" in node.get("metadata", {}))
    owner = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    return result, owner, local


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml022_ac06_typed_source_preserves_relations_directions_and_rekeys(tmp_path, directed):
    """Real extraction gains a reverse arc; build, prefix and reload retain all three facts."""
    result, owner, local = fixture(tmp_path)
    result["edges"].append({"source": local, "target": owner, "relation": "calls", "confidence": "EXTRACTED"})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    assert is_source_graph(graph)
    expected = {(owner, local, "contains"), (owner, local, "calls"), (local, owner, "calls")}
    assert {(d["_src"], d["_tgt"], d["relation"]) for u, v, d in graph.edges(data=True)
            if {u, v} == {owner, local}} == expected
    prefixed = prefix_graph_for_global(graph, "sample")
    assert is_source_graph(prefixed)
    for _, _, key, data in prefixed.edges(keys=True, data=True):
        assert key == storage_key(data["_src"], data["_tgt"], data["relation"])
    output = tmp_path / "graph.json"
    assert to_json(prefixed, {}, str(output), force=True)
    loaded = load_node_link_graph(output)
    assert is_source_graph(loaded) and loaded.number_of_edges() == graph.number_of_edges()


def test_req_qml022_ac06_legacy_graph_projection_unchanged(tmp_path):
    """A lookalike label without the typed producer contract cannot select a new graph class."""
    for directed, graph_type in [(False, nx.Graph), (True, nx.DiGraph)]:
        graph = build_from_json({"nodes": [{"id": "local", "label": "Local()"}], "edges": []}, directed=directed)
        assert type(graph) is graph_type and FIELD not in graph.graph


@pytest.mark.parametrize("damage", ["span", "signature", "callable", "name", "scope", "flag", "role_list", "role_dict", "class", "null"])
def test_req_qml022_ac06_malformed_typed_source_contract_rejects_before_projection(tmp_path, damage):
    """A valid peer cannot hide a promised malformed transport behind simple projection."""
    result, _, local = fixture(tmp_path)
    node = next(node for node in result["nodes"] if node["id"] == local)
    fact = node["metadata"]["csharp_local_function"]
    if damage == "span":
        fact["span"]["start_byte"] = True
    elif damage == "signature":
        fact["signature"] = "not-a-digest"
    elif damage == "callable":
        node["_callable"] = False
    elif damage == "name":
        fact["raw_name_b64"] = "%%%"
    elif damage == "scope":
        fact["scope_span"]["end_byte"] = fact["span"]["start_byte"]
    elif damage.startswith("role_"):
        fact["role"] = [] if damage == "role_list" else {}
    elif damage == "class":
        node["_callable_class"] = True
    elif damage == "null":
        node["metadata"]["csharp_local_function"] = None
    else:
        fact["partial"] = "false"
    before = copy.deepcopy(result)
    with pytest.raises(ValueError, match="local-function"):
        build_from_json(result, root=tmp_path)
    assert result == before


def test_req_qml022_ac06_same_relation_strongest_evidence_survives_without_loser_fields(tmp_path):
    """Parallel storage retains existing confidence precedence and evidence cleanup."""
    result, owner, local = fixture(tmp_path)
    result["edges"] = [{"source": owner, "target": local, "relation": "calls", "confidence": "INFERRED",
                        "confidence_score": .9, "source_location": "L1"},
                       {"source": owner, "target": local, "relation": "calls", "confidence": "EXTRACTED"}]
    graph = build_from_json(result, root=tmp_path)
    assert graph.number_of_edges() == 1
    data = next(iter(graph.edges(data=True)))[2]
    assert data["confidence"] == "EXTRACTED" and "confidence_score" not in data and "source_location" not in data


@pytest.mark.parametrize("dedup", [False, True])
def test_req_qml022_ac06_multiline_same_named_locals_retain_separate_lexical_owners(tmp_path, dedup):
    """Actual multiline producer locations and repeated names retain both scoped declarations."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder {\n void First(){\n void Local(){\n }\n Local();}\n void Second(){\n void Local(){\n }\n Local();}\n}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build([result], root=tmp_path, dedup=dedup)
    locals_ = {identity for identity, data in graph.nodes(data=True) if "csharp_local_function" in data.get("metadata", {})}
    assert len(locals_) == 2
    for local in locals_:
        owners = {data["_src"] for _, _, data in graph.edges(data=True) if data["_tgt"] == local and data["relation"] == "contains"}
        callers = {data["_src"] for _, _, data in graph.edges(data=True) if data["_tgt"] == local and data["relation"] == "calls"}
        assert len(owners) == 1 and callers == owners
