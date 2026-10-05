"""INC-QML-30: affected traversal preserves accepted serialized edge direction."""
from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qml_facts import qml_metadata
from graphify.qt_affected import owned_ancestors
from graphify.serve import _query_graph_text
import graphify.__main__ as mainmod
from tests.qt_adoption_fixture import sources
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("expression", ["factory->makeBackend()", "backend"])
@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("reverse_insertion", [False, True])
def test_native_provider_affected_uses_accepted_serialized_direction(tmp_path, monkeypatch, capsys,
                                                                    expression, directed, reverse_insertion):
    """The real source access remains an incoming dependency of its native endpoint after JSON reload."""
    result = analysis(tmp_path, sources(tmp_path, expression))
    if reverse_insertion:
        result["nodes"] = list(reversed(result["nodes"]))
        result["edges"] = list(reversed(result["edges"]))
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    access = next(node for node in sites(result, "context_access")
                  if qt_metadata(node)["endpoint_proof"]["kind"] == "function")
    target = qt_metadata(access)["endpoint_proof"]["canonical_target_id"]
    assert reloaded.has_edge(access["id"], target)
    if not directed:
        metadata = reloaded.edges[access["id"], target]
        assert metadata["_src"] == access["id"] and metadata["_tgt"] == target
    hits = {hit.node_id: hit for hit in affected_nodes(reloaded, target, depth=3)}
    assert access["id"] in hits
    assert hits[access["id"]].via_file == "Main.qml"
    assert hits[access["id"]].via_location == access["source_location"]
    assert "refresh" in _query_graph_text(reloaded, "refresh", token_budget=1500)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", target, "--graph", str(path), "--depth", "3"])
    mainmod.main()
    out = capsys.readouterr().out
    assert reloaded.nodes[access["id"]]["label"] in out
    assert f"Main.qml:{access['source_location']}" in out


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("reverse_insertion", [False, True])
def test_logical_member_seed_finds_caller_without_reporting_seeded_method(directed, reverse_insertion):
    """Physical iteration order cannot reverse either the root's member seed or incoming caller."""
    graph = nx.DiGraph() if directed else nx.Graph()
    order = ["class", "method", "caller"]
    graph.add_nodes_from(reversed(order) if reverse_insertion else order)
    graph.add_edge("class", "method", relation="method", _src="class", _tgt="method")
    graph.add_edge("caller", "method", relation="calls", _src="caller", _tgt="method",
                   source_file="consumer.py", source_location="L17")
    hits = affected_nodes(graph, "class", depth=1)
    assert [(hit.node_id, hit.depth, hit.via_relation, hit.via_file, hit.via_location) for hit in hits] == [
        ("caller", 1, "calls", "consumer.py", "L17")]
    assert not affected_nodes(graph, "class", relations=["references"], depth=2)


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("direction", [
    {"_src": "caller"}, {"_tgt": "target"}, {"_src": "foreign", "_tgt": "target"},
    {"_src": "caller", "_tgt": "foreign"}, {"_src": None, "_tgt": "target"},
    {"_src": ["caller"], "_tgt": "target"}, {"_src": "caller", "_tgt": {"id": "target"}},
])
def test_corrupt_direction_cannot_fall_back_to_physical_incoming(directed, direction):
    """Partial, foreign or malformed transport rejects its edge rather than becoming legacy direction."""
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(["caller", "target", "foreign"])
    graph.add_edge("caller", "target", relation="references", **direction)
    assert not affected_nodes(graph, "target", depth=1)


def test_directed_direction_must_agree_with_physical_endpoints():
    """A directed edge cannot claim the opposite orientation and silently change its dependency."""
    graph = nx.DiGraph()
    graph.add_edge("caller", "target", relation="calls", _src="target", _tgt="caller")
    assert not affected_nodes(graph, "target", depth=1)


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("reverse_insertion", [False, True])
def test_legacy_edges_without_direction_keep_existing_traversal(directed, reverse_insertion):
    """An unmarked generic graph retains its historical raw endpoint interpretation."""
    graph = nx.DiGraph() if directed else nx.Graph()
    order = ["caller", "target"]
    graph.add_nodes_from(reversed(order) if reverse_insertion else order)
    graph.add_edge("caller", "target", relation="calls")
    expected_source, expected_target = ("target", "caller") if reverse_insertion and not directed else ("caller", "target")
    assert [hit.node_id for hit in affected_nodes(graph, expected_target, depth=1)] == [expected_source]
    assert not affected_nodes(graph, expected_source, depth=1)


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("role", ["method", "contains"])
def test_partial_member_direction_cannot_seed_reverse_traversal(directed, role):
    """A root member edge with one missing marker cannot silently seed a caller's dependency."""
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_edge("class", "member", relation=role, _src="class")
    graph.add_edge("caller", "member", relation="calls", _src="caller", _tgt="member")
    assert not affected_nodes(graph, "class", depth=2)


@pytest.mark.parametrize("directed,corruption", [(False, "partial_source"), (False, "partial_target"),
    (False, "foreign"), (True, "partial_source"), (True, "partial_target"), (True, "foreign"),
    (True, "reversed_directed")])
def test_qt_owner_promotion_rejects_partial_or_foreign_direction(tmp_path, directed, corruption):
    """An accepted real QML read cannot promote a forged owner from damaged contains direction."""
    result = analysis(tmp_path, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }"})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    access = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    owners = list(owned_ancestors(graph, access["id"]))
    assert owners
    owner, data = owners[0]
    target = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "property"
                  and qml_metadata(node).get("raw_name") == "input")
    assert owner in {hit.node_id for hit in affected_nodes(graph, target, depth=1)}
    assert data["_src"] == owner and data["_tgt"] == access["id"]
    if corruption == "partial_source":
        data.pop("_src")
    elif corruption == "partial_target":
        data.pop("_tgt")
    elif corruption == "foreign":
        graph.add_node("foreign", label="Foreign", source_file=access["source_file"])
        data["_src"] = "foreign"
    else:
        data["_src"], data["_tgt"] = data["_tgt"], data["_src"]
    assert not list(owned_ancestors(graph, access["id"]))
    hits = {hit.node_id for hit in affected_nodes(graph, target, depth=1)}
    assert access["id"] in hits and owner not in hits and "foreign" not in hits


@pytest.mark.parametrize("directed", [False, True])
def test_logical_direction_depth_cycles_and_repeated_query_preserve_graph(directed):
    """Bounded reverse traversal ignores outgoing dependencies and terminates cycles without changing data."""
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(["seed", "second", "first"])
    for source, target in (("first", "seed"), ("second", "first"), ("seed", "second")):
        graph.add_edge(source, target, relation="references", _src=source, _tgt=target)
    before = nx.node_link_data(graph, edges="links")
    assert not affected_nodes(graph, "seed", depth=0)
    assert [(hit.node_id, hit.depth) for hit in affected_nodes(graph, "seed", depth=1)] == [("first", 1)]
    expected = [("first", 1), ("second", 2)]
    assert [(hit.node_id, hit.depth) for hit in affected_nodes(graph, "seed", depth=8)] == expected
    assert [(hit.node_id, hit.depth) for hit in affected_nodes(graph, "seed", depth=8)] == expected
    assert nx.node_link_data(graph, edges="links") == before


@pytest.mark.parametrize("directed", [False, True])
def test_parallel_edges_keep_valid_filtered_mechanism_after_invalid_direction(directed):
    """A rejected parallel edge cannot hide another accepted mechanism between the same endpoints."""
    graph = nx.MultiDiGraph() if directed else nx.MultiGraph()
    graph.add_nodes_from(["target", "caller"])
    graph.add_edge("caller", "target", relation="calls", _src="foreign", _tgt="target")
    graph.add_edge("caller", "target", relation="references", _src="caller", _tgt="target",
                   source_file="client.py", source_location="L27")
    hits = affected_nodes(graph, "target", relations=["references"], depth=1)
    assert [(hit.node_id, hit.via_relation, hit.via_location) for hit in hits] == [("caller", "references", "L27")]
    assert not affected_nodes(graph, "target", relations=["calls"], depth=1)


@pytest.mark.parametrize("directed", [False, True])
def test_boolean_marker_cannot_coerce_integer_endpoint_identity(directed):
    """Serialized bool is not the accepted integer endpoint even though Python equality equates them."""
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_edge(1, "target", relation="references", _src=True, _tgt="target")
    assert not affected_nodes(graph, "target", depth=1)


@pytest.mark.parametrize("markers", [{"_src": "source"}, {"_tgt": "target"},
    {"_src": "foreign", "_tgt": "target"}, {"_src": None, "_tgt": "target"},
    {"_src": ["source"], "_tgt": "target"}])
def test_typed_reload_preserves_corrupt_dependency_direction_for_rejection(tmp_path, markers):
    """Actual JSON reload must not replace damaged explicit markers with a trusted serialized pair."""
    result = analysis(tmp_path, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }"})
    graph = build_from_json(result, root=tmp_path)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    source = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    target = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "property"
                  and qml_metadata(node).get("raw_name") == "input")
    original = json.loads(path.read_text(encoding="utf-8"))
    # The real writer omits its internal markers. Untouched serialized producer
    # endpoints remain the normal positive control before damaging this edge.
    assert source in {hit.node_id for hit in affected_nodes(load_node_link_graph(path), target, depth=1)}
    link = next(link for link in original["links"] if link["source"] == source and link["target"] == target)
    link.update({key: source if value == "source" else target if value == "target" else value
                 for key, value in markers.items()})
    path.write_text(json.dumps(original), encoding="utf-8")
    reloaded = load_node_link_graph(path)
    assert source not in {hit.node_id for hit in affected_nodes(reloaded, target, depth=1)}


@pytest.mark.parametrize("markers", [{"_src": "source"}, {"_tgt": "target"},
                                    {"_src": "foreign", "_tgt": "target"}])
def test_typed_reload_preserves_corrupt_owner_direction_for_rejection(tmp_path, markers):
    """A persisted real contains edge cannot acquire source ownership by overwriting partial/foreign markers."""
    result = analysis(tmp_path, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }"})
    graph = build_from_json(result, root=tmp_path)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    child = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    owner = list(owned_ancestors(graph, child))[0][0]
    original = json.loads(path.read_text(encoding="utf-8"))
    assert list(owned_ancestors(load_node_link_graph(path), child))
    link = next(link for link in original["links"] if link["source"] == owner and link["target"] == child)
    link.update({key: owner if value == "source" else child if value == "target" else value
                 for key, value in markers.items()})
    # Give the forged endpoint an otherwise plausible same-file node, making
    # endpoint-pair validation the actual protection rather than missing-node luck.
    original["nodes"].append({"id": "foreign", "label": "Foreign", "source_file": "Main.qml"})
    path.write_text(json.dumps(original), encoding="utf-8")
    assert not list(owned_ancestors(load_node_link_graph(path), child))


@pytest.mark.parametrize("reversed_pair", [False, True])
def test_typed_reload_preserves_valid_complete_explicit_pair(tmp_path, reversed_pair):
    """A valid complete pair retains its declared orientation instead of being silently replaced on reload."""
    result = analysis(tmp_path, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }"})
    graph = build_from_json(result, root=tmp_path)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    source = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "read")
    target = next(node["id"] for node in result["nodes"] if qml_metadata(node).get("kind") == "property"
                  and qml_metadata(node).get("raw_name") == "input")
    data = json.loads(path.read_text(encoding="utf-8"))
    link = next(link for link in data["links"] if link["source"] == source and link["target"] == target)
    expected = (target, source) if reversed_pair else (source, target)
    link["_src"], link["_tgt"] = expected
    path.write_text(json.dumps(data), encoding="utf-8")
    reloaded = load_node_link_graph(path)
    attributes = reloaded.edges[source, target]
    assert (attributes["_src"], attributes["_tgt"]) == expected
    assert (source in {hit.node_id for hit in affected_nodes(reloaded, target, depth=1)}) is not reversed_pair
