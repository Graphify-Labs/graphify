"""Native cross-project aggregation tests."""

import pytest

from graphify.build import prefix_graph_for_global, prune_repo_from_graph
from graphify.global_graph import aggregate, global_add, global_list, global_remove
from graphify.helix.model import GraphBuildData
from graphify.helix.persistence import load_graph
from tests.native_helpers import make_loaded


def _build(nodes, edges=None):
    return GraphBuildData.from_node_link({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": nodes, "links": edges or [],
    })


def _source(root, name, *, external=False):
    path = root / name / "graphify-out"
    path.mkdir(parents=True)
    nodes = [
        {"id": "service", "label": name.title() + "Service", "source_file": f"{name}.py"},
        {"id": "requests", "label": "requests", **({} if external else {"source_file": "vendor.py"})},
    ]
    return make_loaded(
        path,
        nodes=nodes,
        edges=[{"source": "service", "target": "requests", "relation": "imports"}],
    ).store_path


def test_prefix_preserves_labels_and_rewrites_edges():
    graph = _build(
        [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        [{"source": "a", "target": "b", "relation": "calls"}],
    )
    prefixed = prefix_graph_for_global(graph, "repo")
    assert {node.id for node in prefixed.nodes} == {"repo::a", "repo::b"}
    assert {node.attributes["label"] for node in prefixed.nodes} == {"A", "B"}
    assert all(node.attributes["repo"] == "repo" for node in prefixed.nodes)
    assert prefixed.edges[0].source == "repo::a" and prefixed.edges[0].target == "repo::b"


def test_prune_removes_only_selected_repo():
    graph = _build([
        {"id": "a::x", "repo": "a"}, {"id": "b::x", "repo": "b"},
    ], [{"source": "a::x", "target": "b::x"}])
    assert prune_repo_from_graph(graph, "a") == 1
    assert [node.id for node in graph.nodes] == ["b::x"]
    assert graph.edges == []


def test_global_add_list_skip_and_remove(tmp_path, monkeypatch):
    destination = tmp_path / "global.helix"
    monkeypatch.setattr("graphify.global_graph.DEFAULT_GLOBAL_STORE", destination)
    source = _source(tmp_path, "alpha")
    first = global_add(source, "alpha")
    assert first["nodes_added"] == 2 and not first["skipped"]
    assert global_add(source, "alpha")["skipped"] is True
    assert global_list()["alpha"]["source_path"] == str(source.resolve())
    assert global_remove("alpha") == 2
    assert global_list() == {}
    with pytest.raises(KeyError):
        global_remove("missing")


def test_two_repos_are_prefixed_without_collision(tmp_path, monkeypatch):
    destination = tmp_path / "global.helix"
    monkeypatch.setattr("graphify.global_graph.DEFAULT_GLOBAL_STORE", destination)
    global_add(_source(tmp_path, "alpha"), "alpha")
    global_add(_source(tmp_path, "beta"), "beta")
    loaded = load_graph(destination)
    assert {node.id for node in loaded.graph.nodes()} == {
        "alpha::service", "alpha::requests", "beta::service", "beta::requests",
    }


def test_external_nodes_deduplicate_and_edges_rewire(tmp_path, monkeypatch):
    destination = tmp_path / "global.helix"
    monkeypatch.setattr("graphify.global_graph.DEFAULT_GLOBAL_STORE", destination)
    global_add(_source(tmp_path, "alpha", external=True), "alpha")
    global_add(_source(tmp_path, "beta", external=True), "beta")
    loaded = load_graph(destination)
    requests = [node.id for node in loaded.graph.nodes() if node.attributes.get("attrs", {}).get("label") == "requests"]
    assert len(requests) == 1
    assert loaded.graph.edge_count == 2


def test_aggregate_accepts_projects_and_native_stores(tmp_path):
    alpha = _source(tmp_path, "alpha")
    beta = _source(tmp_path, "beta")
    destination = tmp_path / "aggregate.helix"
    assert aggregate([alpha.parent.parent, beta], destination) == destination.resolve()
    loaded = load_graph(destination)
    assert loaded.graph.node_count == 4 and loaded.graph.edge_count == 2
    assert loaded.state["build"]["kind"] == "global-aggregate"


def test_global_add_rejects_legacy_json(tmp_path, monkeypatch):
    monkeypatch.setattr("graphify.global_graph.DEFAULT_GLOBAL_STORE", tmp_path / "global.helix")
    legacy = tmp_path / "graph.json"
    legacy.write_text("{}")
    with pytest.raises(ValueError, match="obsolete"):
        global_add(legacy, "legacy")
