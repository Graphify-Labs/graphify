"""`graphify query` must render every edge between visited nodes (#2323).

`_bfs`/`_dfs` recorded an edge only when it discovered an *unvisited* neighbour,
so the result was a traversal tree rather than the induced subgraph over the
node set the query returns. The most visible casualty is an edge between two
seed nodes: both endpoints render, the edge between them does not.
"""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.serve import _bfs, _dfs, _filter_graph_by_context, _query_graph_text

# Hub suppression only kicks in at degree >= 50 (serve.py `hub_threshold`).
_HUB_PADDING = 60


def _add(G, *names):
    for n in names:
        G.add_node(n, label=n, source_file=f"{n}.py", source_location="L1", community=0)


def _link(G, a, b, relation="calls", context="call"):
    G.add_edge(a, b, relation=relation, confidence="EXTRACTED", context=context)


def _pairs(edges):
    return {frozenset(e) for e in edges}


def _induced(G, visited):
    return {frozenset((u, v)) for u, v in G.edges() if u in visited and v in visited}


# --- the reported case -------------------------------------------------------


def test_bfs_records_edge_between_two_seeds():
    """The reporter's repro: both endpoints are seeds, so neither discovers the other."""
    G = nx.Graph()
    _add(G, "checkout", "discounted_total")
    _link(G, "checkout", "discounted_total")

    visited, edges = _bfs(G, ["checkout", "discounted_total"], depth=1)

    assert visited == {"checkout", "discounted_total"}
    assert _pairs(edges) == {frozenset(("checkout", "discounted_total"))}


def test_bfs_records_cross_edge_in_a_triangle():
    """n2-n3 closes the triangle but discovers nothing, so it was dropped."""
    G = nx.Graph()
    _add(G, "n1", "n2", "n3")
    _link(G, "n1", "n2")
    _link(G, "n1", "n3")
    _link(G, "n2", "n3")

    visited, edges = _bfs(G, ["n1"], depth=2)

    assert visited == {"n1", "n2", "n3"}
    assert _pairs(edges) == _induced(G, visited)


def test_bfs_records_edge_between_two_visited_hubs():
    """A hub is visited but never expanded, so hub-to-hub edges vanished."""
    G = nx.Graph()
    _add(G, "seed", "hub_a", "hub_b")
    _link(G, "seed", "hub_a")
    _link(G, "seed", "hub_b")
    _link(G, "hub_a", "hub_b")
    for i in range(_HUB_PADDING):
        _add(G, f"a{i}", f"b{i}")
        _link(G, "hub_a", f"a{i}")
        _link(G, "hub_b", f"b{i}")

    visited, edges = _bfs(G, ["seed"], depth=1)

    assert visited == {"seed", "hub_a", "hub_b"}
    assert frozenset(("hub_a", "hub_b")) in _pairs(edges)


def test_dfs_records_edge_between_two_visited_hubs():
    """DFS's only induced-edge gap: neither endpoint expands, so neither records it.

    DFS appends on push rather than on visit, so unlike `_bfs` it already
    captured seed-to-seed and ordinary cross-edges. Two mutually adjacent
    non-seed hubs are the case it could not reach.
    """
    G = nx.Graph()
    _add(G, "seed", "hub_a", "hub_b")
    _link(G, "seed", "hub_a")
    _link(G, "seed", "hub_b")
    _link(G, "hub_a", "hub_b")
    for i in range(_HUB_PADDING):
        _add(G, f"a{i}", f"b{i}")
        _link(G, "hub_a", f"a{i}")
        _link(G, "hub_b", f"b{i}")

    visited, edges = _dfs(G, ["seed"], depth=1)

    assert visited == {"seed", "hub_a", "hub_b"}
    assert frozenset(("hub_a", "hub_b")) in _pairs(edges)


# --- invariants the completion pass must not break ---------------------------


def test_traversal_edges_keep_discovery_order_and_come_first():
    G = nx.Graph()
    _add(G, "n1", "n2", "n3")
    _link(G, "n1", "n2")
    _link(G, "n1", "n3")
    _link(G, "n2", "n3")

    _, edges = _bfs(G, ["n1"], depth=2)

    assert edges[:2] == [("n1", "n2"), ("n1", "n3")]


def test_no_duplicate_edges_are_returned():
    G = nx.Graph()
    _add(G, "n1", "n2", "n3", "n4")
    for a, b in [("n1", "n2"), ("n1", "n3"), ("n2", "n3"), ("n2", "n4"), ("n3", "n4")]:
        _link(G, a, b)

    for traverse in (_bfs, _dfs):
        _, edges = traverse(G, ["n1"], depth=3)
        assert len(edges) == len(_pairs(edges)), traverse.__name__


def test_completion_respects_the_context_filter():
    """The completion pass must scan the filtered graph, never the raw one.

    Scanning raw `G` would resurrect the `import` edge the user explicitly
    filtered out, which is worse than the bug being fixed. The two relations
    need distinct node pairs: on a plain Graph a second `add_edge` on the same
    pair overwrites the first, which would leave nothing to filter and make
    this assertion vacuous.
    """
    G = nx.Graph()
    _add(G, "n1", "n2", "n3")
    _link(G, "n1", "n2", relation="calls", context="call")
    _link(G, "n1", "n3", relation="imports", context="import")
    _link(G, "n2", "n3", relation="imports", context="import")

    filtered = _filter_graph_by_context(G, ["call"])
    _, edges = _bfs(filtered, ["n1", "n2", "n3"], depth=1)

    assert _pairs(edges) == {frozenset(("n1", "n2"))}, "an import edge came back"


def test_self_loops_are_not_introduced():
    """A recursive function carries a self-loop; the traversal never rendered one.

    Surfacing them would be an output change beyond the missing edges reported
    in #2323, so the completion pass skips them.
    """
    G = nx.Graph()
    _add(G, "recurse", "caller")
    _link(G, "recurse", "recurse")
    _link(G, "caller", "recurse")

    _, edges = _bfs(G, ["caller", "recurse"], depth=1)

    assert _pairs(edges) == {frozenset(("caller", "recurse"))}


def test_directed_graph_keeps_both_directions_of_a_mutual_edge():
    """u->v and v->u are distinct on a DiGraph (mutual recursion, circular imports).

    The MCP `query_graph` path forces `directed: True`, so unordered dedup here
    would silently drop a real edge.
    """
    G = nx.DiGraph()
    _add(G, "ping", "pong")
    _link(G, "ping", "pong")
    _link(G, "pong", "ping")

    _, edges = _bfs(G, ["ping", "pong"], depth=1)

    assert set(edges) == {("ping", "pong"), ("pong", "ping")}


def test_directed_graph_renders_the_seed_to_seed_edge():
    """Mirrors the MCP path, which loads every graph with directed=True."""
    G = nx.DiGraph()
    _add(G, "checkout", "discounted_total")
    _link(G, "checkout", "discounted_total")

    text = _query_graph_text(G, "checkout discounted_total", depth=1)

    assert "EDGE checkout --calls" in text
    assert "discounted_total" in text


# --- end to end through the real CLI ----------------------------------------


def _write_two_seed_graph(tmp_path):
    """The reporter's shape: one `calls` edge whose endpoints are both seeds."""
    G = nx.Graph()
    G.add_node(
        "app.py::checkout",
        label="checkout",
        source_file="app.py",
        source_location="L4",
        community=0,
    )
    G.add_node(
        "pricing.py::discounted_total",
        label="discounted_total",
        source_file="pricing.py",
        source_location="L1",
        community=0,
    )
    G.add_edge(
        "app.py::checkout",
        "pricing.py::discounted_total",
        relation="calls",
        confidence="EXTRACTED",
        context="call",
        source_file="app.py",
        source_location="L5",
    )
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_query_cli_renders_the_edge_between_two_seeds(monkeypatch, tmp_path, capsys):
    graph_path = _write_two_seed_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "checkout discounted_total", "--graph", str(graph_path)],
    )

    mainmod.main()
    out = capsys.readouterr().out

    assert "NODE checkout" in out
    assert "NODE discounted_total" in out
    assert "EDGE checkout --calls" in out
    assert "discounted_total" in out.split("EDGE checkout --calls", 1)[1]
