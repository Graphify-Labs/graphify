"""INC-QML-132: generic multigraph flags coexist with accepted source storage."""
from __future__ import annotations

import json
from collections import Counter

import networkx as nx
import pytest

import graphify.__main__ as entrypoint
from graphify.analyze import surprising_connections
from graphify.build import add_source_relationship
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD, is_source_graph, make_source_graph
from tests.source_relationship_projection_watch_helpers import products
from tests.test_qt_final_incremental_parity import run


def publish(root, monkeypatch, operation, changes=None):
    """Exercise each actual raw publisher while suppressing unrelated skill upkeep."""
    if operation != "extract":
        return run(root, monkeypatch, operation, changes)
    monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(entrypoint.sys, "argv", [
        "graphify", "extract", str(root), "--code-only", "--no-cluster",
    ])
    try:
        entrypoint.main()
    except SystemExit as completion:
        # Extract owns an explicit success exit; update returns to its caller.
        assert completion.code in (None, 0)
    return load_node_link_graph(root / "graphify-out/graph.json")


@pytest.mark.parametrize("operation", ["extract", "manual", "watch"])
def test_req_qml022_ac06_inherited_source_profile_survives_last_parallel_pair(
    tmp_path, monkeypatch, operation,
):
    """Deletion leaves one ordinary arc, but its accepted source profile must survive."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    local = tmp_path / "Data.cs"
    local.write_text("class Owner{void Run(){void Local(){} Local();}}", encoding="utf-8")
    (tmp_path / "keep.py").write_text("def retained(): return 1\n", encoding="utf-8")
    original = publish(tmp_path, monkeypatch, operation)
    assert is_source_graph(original)
    assert any(node.get("metadata", {}).get("csharp_local_function")
               for _, node in original.nodes(data=True))

    local.unlink()
    updated = publish(tmp_path, monkeypatch, operation, [local])
    payload = json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert len(payload["links"]) == 1
    assert payload["multigraph"] is True
    assert payload["graph"][FIELD] == {"contract_version": 1}
    assert is_source_graph(updated)
    assert not any(node.get("metadata", {}).get("csharp_local_function")
                   for _, node in updated.nodes(data=True))
    accepted = products(tmp_path)
    publish(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == accepted


@pytest.mark.parametrize("operation", ["extract", "manual", "watch"])
@pytest.mark.parametrize("parallel", [False, True])
def test_req_qml022_ac06_ordinary_raw_flags_reflect_parallel_links(
    tmp_path, monkeypatch, operation, parallel,
):
    """Unpromised legacy graphs infer their mode without acquiring source storage."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    if parallel:
        (tmp_path / "sample.ts").write_text(
            "function owner() { function child() { return 1 } return child() }\n",
            encoding="utf-8",
        )
    else:
        (tmp_path / "keep.py").write_text("def retained(): return 1\n", encoding="utf-8")
    graph = publish(tmp_path, monkeypatch, operation)
    payload = json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert payload["multigraph"] is parallel
    assert FIELD not in payload.get("graph", {})
    assert not is_source_graph(graph)
    # Legacy extract retains its established edges alias; update writes links.
    stored_links = payload.get("links", payload.get("edges", []))
    assert stored_links
    pairs = [frozenset((edge["source"], edge["target"])) for edge in stored_links]
    assert (len(pairs) != len(set(pairs))) is parallel


@pytest.mark.parametrize("source_profile", [False, True], ids=["legacy", "source"])
@pytest.mark.parametrize("directed", [False, True], ids=["undirected", "directed"])
@pytest.mark.parametrize("top_n", [1, 5], ids=["bounded", "all"])
def test_req_qml022_ac06_bridge_rows_keep_profile_topology_and_generic_relations(
    source_profile, directed, top_n,
):
    """The source topology view stays bounded and directed while generic rows retain every relation."""
    graph = (make_source_graph(directed=directed, graph_metadata={FIELD: {"contract_version": 1}})
             if source_profile else (nx.MultiDiGraph() if directed else nx.MultiGraph()))
    # Reverse physical node order so an undirected source row must recover its
    # accepted logical direction rather than borrow adjacency enumeration.
    graph.add_nodes_from([("second", {"label": "Second"}), ("first", {"label": "First"})])
    for source, target, relation in (("first", "second", "contains"),
                                     ("first", "second", "calls"), ("second", "first", "calls")):
        attrs = {"relation": relation, "confidence": "EXTRACTED"}
        if source_profile:
            add_source_relationship(graph, source, target, attrs)
        else:
            graph.add_edge(source, target, **attrs)
    before = json.dumps(nx.node_link_data(graph, edges="links"), sort_keys=True)
    rows = surprising_connections(graph, {}, top_n=top_n)
    expected_count = (2 if directed else 1) if source_profile else 3
    assert len(rows) == min(top_n, expected_count)
    assert all(row["note"].startswith("Bridges graph structure") for row in rows)
    if source_profile:
        expected_directions = ({("First", "Second"), ("Second", "First")}
                               if directed else {("First", "Second")})
        assert {(row["source"], row["target"]) for row in rows} <= expected_directions
        if top_n == 5:
            assert {(row["source"], row["target"]) for row in rows} == expected_directions
    elif top_n == 5:
        assert Counter(row["relation"] for row in rows) == {"contains": 1, "calls": 2}
    assert graph.number_of_edges() == 3
    assert json.dumps(nx.node_link_data(graph, edges="links"), sort_keys=True) == before
