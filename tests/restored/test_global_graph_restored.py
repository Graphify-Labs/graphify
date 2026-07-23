"""Retained global-graph regressions, adapted to native Helix stores."""
from __future__ import annotations

import pytest

from graphify.build import prefix_graph_for_global, prune_repo_from_graph
from graphify.dedup import deduplicate_entities
from graphify.global_graph import aggregate, global_add, global_list, global_remove
from graphify.helix.model import GraphBuildData
from graphify.helix.persistence import load_graph
from tests.native_helpers import make_loaded


def _make_graph(nodes, edges=None):
    return GraphBuildData.from_node_link({
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": nodes,
        "links": edges or [],
    })


def _source(root, dirname, nodes, edges=None):
    project = root / dirname / "graphify-out"
    project.mkdir(parents=True, exist_ok=True)
    return make_loaded(project, nodes=nodes, edges=edges or []).store_path


def _destination(tmp_path, monkeypatch):
    destination = tmp_path / "global.helix"
    monkeypatch.setattr("graphify.global_graph.DEFAULT_GLOBAL_STORE", destination)
    return destination


def test_prefix_graph_preserves_label():
    graph = _make_graph([{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}])
    prefixed = prefix_graph_for_global(graph, "repoA")
    assert [node.id for node in prefixed.nodes] == ["repoA::userservice"]
    assert prefixed.nodes[0].attributes["label"] == "UserService"


def test_prefix_graph_sets_repo_and_local_id():
    prefixed = prefix_graph_for_global(
        _make_graph([{"id": "userservice", "label": "UserService"}]), "repoA"
    )
    attrs = prefixed.nodes[0].attributes
    assert attrs["repo"] == "repoA"
    assert attrs["local_id"] == "userservice"


def test_prefix_graph_rewrites_edges():
    prefixed = prefix_graph_for_global(
        _make_graph(
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            [{"source": "a", "target": "b"}],
        ),
        "repo1",
    )
    assert [(edge.source, edge.target) for edge in prefixed.edges] == [
        ("repo1::a", "repo1::b")
    ]


def test_prune_repo_removes_correct_nodes():
    graph = _make_graph(
        [
            {"id": "repoA::userservice", "repo": "repoA", "label": "UserService"},
            {"id": "repoB::userservice", "repo": "repoB", "label": "UserService"},
            {"id": "repoA::auth", "repo": "repoA", "label": "Auth"},
        ]
    )
    assert prune_repo_from_graph(graph, "repoA") == 2
    assert [node.id for node in graph.nodes] == ["repoB::userservice"]


def test_prune_repo_returns_zero_if_not_present():
    graph = _make_graph([{"id": "repoA::x", "repo": "repoA"}])
    assert prune_repo_from_graph(graph, "repoB") == 0
    assert graph.node_count == 1


def test_global_add_creates_global_graph(tmp_path, monkeypatch):
    destination = _destination(tmp_path, monkeypatch)
    source = _source(
        tmp_path,
        "source",
        [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}],
    )
    result = global_add(source, "repoA")
    assert result["skipped"] is False
    assert result["nodes_added"] == 1
    assert destination.is_dir()
    assert "repoA" in global_list()


def test_global_add_skip_on_unchanged_hash(tmp_path, monkeypatch):
    _destination(tmp_path, monkeypatch)
    source = _source(
        tmp_path,
        "source",
        [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}],
    )
    global_add(source, "repoA")
    assert global_add(source, "repoA")["skipped"] is True


def test_global_add_two_repos_no_collision(tmp_path, monkeypatch):
    destination = _destination(tmp_path, monkeypatch)
    node = [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}]
    global_add(_source(tmp_path, "one", node), "repoA")
    global_add(_source(tmp_path, "two", node), "repoB")
    graph = load_graph(destination).graph
    assert {record.id for record in graph.nodes()} == {
        "repoA::userservice",
        "repoB::userservice",
    }


def test_global_remove(tmp_path, monkeypatch):
    _destination(tmp_path, monkeypatch)
    source = _source(
        tmp_path,
        "source",
        [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}],
    )
    global_add(source, "repoA")
    assert global_remove("repoA") == 1
    assert "repoA" not in global_list()


def test_global_remove_unknown_tag_raises(tmp_path, monkeypatch):
    _destination(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        global_remove("nonexistent")


def test_global_add_replaces_same_tag_from_new_source(tmp_path, monkeypatch):
    destination = _destination(tmp_path, monkeypatch)
    first = _source(tmp_path, "one", [{"id": "x", "label": "X", "source_file": "x.py"}])
    second = _source(tmp_path, "two", [{"id": "y", "label": "Y", "source_file": "y.py"}])
    global_add(first, "myrepo")
    result = global_add(second, "myrepo")
    assert result["nodes_removed"] == 1 and result["nodes_added"] == 1
    assert {node.id for node in load_graph(destination).graph.nodes()} == {"myrepo::y"}


def test_dedup_raises_on_cross_repo_nodes():
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoB::userservice", "label": "UserService", "repo": "repoB"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [], communities={})


def test_dedup_ok_with_single_repo():
    nodes = [
        {"id": "repoA::userservice", "label": "UserService", "repo": "repoA"},
        {"id": "repoA::auth", "label": "Auth", "repo": "repoA"},
    ]
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2
    assert result_edges == []


def test_dedup_ok_with_no_repo_attr():
    nodes = [
        {"id": "userservice", "label": "UserService"},
        {"id": "auth", "label": "Auth"},
    ]
    result_nodes, result_edges = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2
    assert result_edges == []


def test_aggregate_prefixes_duplicate_ids(tmp_path):
    node = [{"id": "userservice", "label": "UserService", "source_file": "src/user.py"}]
    first = _source(tmp_path, "repo1", node)
    second = _source(tmp_path, "repo2", node)
    destination = tmp_path / "aggregate.helix"
    aggregate([first, second], destination)
    assert {record.id for record in load_graph(destination).graph.nodes()} == {
        "repo1::userservice",
        "repo2::userservice",
    }


def test_global_add_rewires_edges_to_deduplicated_externals(tmp_path, monkeypatch):
    destination = _destination(tmp_path, monkeypatch)
    source_a = _source(
        tmp_path,
        "one",
        [
            {"id": "moda", "label": "ModA", "source_file": "src/a.py"},
            {"id": "requests", "label": "requests"},
        ],
        [{"source": "moda", "target": "requests", "relation": "imports"}],
    )
    source_b = _source(
        tmp_path,
        "two",
        [
            {"id": "modb", "label": "ModB", "source_file": "src/b.py"},
            {"id": "requests", "label": "requests"},
        ],
        [{"source": "modb", "target": "requests", "relation": "imports"}],
    )
    global_add(source_a, "repoA")
    global_add(source_b, "repoB")
    graph = load_graph(destination).graph
    ids = {node.id for node in graph.nodes()}
    externals = {node_id for node_id in ids if str(node_id).startswith("external::")}
    assert len(externals) == 1
    external = next(iter(externals))
    assert graph.edges_between("repoA::moda", external)
    assert graph.edges_between("repoB::modb", external)
