"""Opt-in MultiDiGraph extraction, persistence, and read-surface behavior."""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

from graphify.affected import affected_nodes
from graphify.build import build_from_json, build_merge
from graphify.cluster_graph import build_cluster
from graphify.export import to_canvas, to_cypher, to_graphml, to_json
from graphify.exporters.html import to_html
from graphify.serve import _subgraph_to_text
from tests.test_cluster_build import _load_out, _node, make_member, write_cluster


def _parallel_extraction():
    return {
        "nodes": [
            _node("a", source_file="a.py"),
            _node("b", source_file="b.py"),
        ],
        "edges": [
            {
                "source": "a", "target": "b", "relation": "calls",
                "source_file": "a.py", "source_location": "L3",
                "confidence": "EXTRACTED",
            },
            {
                "source": "a", "target": "b", "relation": "references",
                "source_file": "a.py", "source_location": "L4",
                "confidence": "EXTRACTED",
            },
        ],
    }


def test_multigraph_build_preserves_parallel_relations_and_stable_keys(tmp_path):
    first = build_from_json(_parallel_extraction(), multigraph=True)
    second = build_from_json(_parallel_extraction(), multigraph=True)

    assert isinstance(first, nx.MultiDiGraph)
    assert first.number_of_edges("a", "b") == 2
    assert set(first["a"]["b"]) == set(second["a"]["b"])
    assert {data["relation"] for data in first["a"]["b"].values()} == {
        "calls", "references"
    }

    out = tmp_path / "graph.json"
    assert to_json(first, {0: ["a", "b"]}, str(out))
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["directed"] is True and raw["multigraph"] is True
    assert len({edge["key"] for edge in raw["links"]}) == 2


def test_multigraph_exact_duplicate_is_idempotent():
    extraction = _parallel_extraction()
    extraction["edges"].append(dict(extraction["edges"][0]))
    graph = build_from_json(extraction, multigraph=True)
    assert graph.number_of_edges("a", "b") == 2


def test_incremental_merge_infers_existing_multigraph_mode(tmp_path):
    graph = build_from_json(_parallel_extraction(), multigraph=True)
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps(json_graph.node_link_data(graph, edges="links")),
        encoding="utf-8",
    )

    merged = build_merge([], graph_path=path)
    assert isinstance(merged, nx.MultiDiGraph)
    assert merged.number_of_edges("a", "b") == 2


def test_multi_cluster_allows_distinct_declared_relations_on_same_pair(tmp_path):
    make_member(tmp_path, "web", [_node("client", source_file="client.py")])
    make_member(tmp_path, "svc", [_node("server", source_file="server.py")])
    cluster = tmp_path / "cluster"
    write_cluster(
        cluster,
        [{"tag": "web", "path": "../web"}, {"tag": "svc", "path": "../svc"}],
        links=[
            {
                "type": "api_call", "name": "api",
                "from": {"repo": "web", "id": "client"},
                "to": {"repo": "svc", "id": "server"},
            },
            {
                "type": "references", "name": "schema",
                "from": {"repo": "web", "id": "client"},
                "to": {"repo": "svc", "id": "server"},
            },
        ],
        graph_mode="multi",
    )

    build_cluster(cluster)
    graph = _load_out(cluster)
    assert isinstance(graph, nx.MultiDiGraph)
    assert {
        data["relation"] for data in graph["web::client"]["svc::server"].values()
    } == {"calls_api", "references"}


def test_query_and_affected_surface_all_parallel_relations():
    graph = build_from_json(_parallel_extraction(), multigraph=True)
    text = _subgraph_to_text(graph, {"a", "b"}, [("a", "b")])
    assert "--calls" in text and "--references" in text

    hits = affected_nodes(graph, "b", relations=("calls", "references"), depth=1)
    assert len(hits) == 1
    assert hits[0].node_id == "a"
    assert hits[0].via_relations == ("calls", "references")


def test_multigraph_exporters_keep_parallel_edges(tmp_path):
    graph = build_from_json(_parallel_extraction(), multigraph=True)
    communities = {0: ["a", "b"]}

    graphml = tmp_path / "graph.graphml"
    to_graphml(graph, communities, str(graphml))
    loaded = nx.read_graphml(graphml)
    assert loaded.number_of_edges() == 2

    cypher = tmp_path / "graph.cypher"
    to_cypher(graph, str(cypher))
    cypher_text = cypher.read_text(encoding="utf-8")
    assert cypher_text.count("MERGE (a)-[") == 2  # keyed MERGE: re-runs stay idempotent
    assert cypher_text.count("graphify_key") == 2

    html = tmp_path / "graph.html"
    to_html(graph, communities, str(html))
    rendered = html.read_text(encoding="utf-8")
    assert '"label": "calls"' in rendered
    assert '"label": "references"' in rendered

    canvas = tmp_path / "graph.canvas"
    to_canvas(graph, communities, str(canvas))
    payload = json.loads(canvas.read_text(encoding="utf-8"))
    assert len(payload["edges"]) == 2
    assert len({edge["id"] for edge in payload["edges"]}) == 2


def test_get_neighbors_surfaces_all_parallel_relations():
    """get_neighbors must iterate edge_datas like query/path: edge_data picks
    one arbitrary parallel edge, so a relation_filter could return empty for
    relations that exist."""
    from graphify.serve import _neighbor_lines

    G = nx.MultiDiGraph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_edge("a", "b", key="k1", relation="calls", confidence="EXTRACTED")
    G.add_edge("a", "b", key="k2", relation="references", confidence="INFERRED")

    out = _neighbor_lines(G, "a")
    assert any("[calls]" in line for line in out)
    assert any("[references]" in line for line in out)
    incoming = _neighbor_lines(G, "b")
    assert any("[calls]" in line for line in incoming)
    assert any("[references]" in line for line in incoming)
    # The filter applies per edge, not to an arbitrarily-picked one.
    assert _neighbor_lines(G, "a", "references") and all(
        "[references]" in line for line in _neighbor_lines(G, "a", "references")
    )


def test_mixed_graph_modes_compose_with_warning(tmp_path, capsys):
    """A simple member in a multi cluster promotes with a warning; a
    multigraph member in a simple cluster collapses parallels silently
    (the coercion the loader documents)."""
    # simple member into multi cluster
    make_member(tmp_path, "plain", [
        _node("a", source_file="a.ts"), _node("b", source_file="b.ts"),
    ], edges=[("a", "b", {"relation": "calls"})])
    multi_cluster = tmp_path / "multi-cluster"
    write_cluster(
        multi_cluster, [{"tag": "plain", "path": "../plain"}],
        name="multi-cluster", graph_mode="multi",
    )
    build_cluster(multi_cluster)
    assert "re-extract it with --multigraph" in capsys.readouterr().err
    assert isinstance(_load_out(multi_cluster), nx.MultiDiGraph)

    # multigraph member into simple cluster: parallel edges collapse to one
    keyed = tmp_path / "keyed" / "graphify-out"
    keyed.mkdir(parents=True)
    M = nx.MultiDiGraph()
    M.add_node("x", label="x", source_file="x.ts")
    M.add_node("y", label="y", source_file="y.ts")
    M.add_edge("x", "y", key="k1", relation="calls")
    M.add_edge("x", "y", key="k2", relation="references")
    (keyed / "graph.json").write_text(
        json.dumps(json_graph.node_link_data(M, edges="links")), encoding="utf-8"
    )
    simple_cluster = tmp_path / "simple-cluster"
    write_cluster(
        simple_cluster, [{"tag": "keyed", "path": "../keyed"}], name="simple-cluster"
    )
    build_cluster(simple_cluster)
    G = _load_out(simple_cluster)
    assert not G.is_multigraph()
    assert G.number_of_edges() == 1
