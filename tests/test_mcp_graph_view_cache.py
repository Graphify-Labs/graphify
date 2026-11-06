"""The MCP server's traversal view and shortest-path graphs are built once per graph.

`query_graph` used to copy every edge of the loaded graph into an undirected
view on every call, and `shortest_path` rebuilt a sorted DiGraph of every edge
on every call. Both are now cached on `G.graph`, like the trigram index. These
tests pin what makes that safe: the cached structure is reused, answers equal a
freshly built one in any order of calls, and a reloaded graph (a new object)
never sees the previous graph's structures.
"""
import json

import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _load_graph,
    _path_search_graph,
    _query_graph_text,
    _shortest_path_text,
    _traversal_view,
)


def _write(tmp_path, edges, name="graph.json"):
    G = nx.Graph()
    for n in sorted({n for e in edges for n in e[:2]}):
        G.add_node(n, label=f"{n}_fn", source_file=f"{n}.py", source_location="L1", community=0)
    data = json_graph.node_link_data(G, edges="links")
    data["links"] = [
        {"source": u, "target": v, "relation": rel, "confidence": "EXTRACTED", "context": ctx}
        for u, v, rel, ctx in edges
    ]
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


EDGES = [
    ("main", "parse", "calls", "call"),
    ("parse", "lexer", "calls", "call"),
    ("parse", "ast", "imports", "import"),
    ("main", "config", "imports", "import"),
    ("config", "lexer", "calls", "call"),
    ("report", "main", "calls", "call"),
]
QUERIES = [
    ("parse_fn", "bfs", None),
    ("lexer_fn", "dfs", None),
    ("what calls lexer_fn", "bfs", None),
    ("config_fn", "bfs", ["import"]),
    ("main_fn", "dfs", ["call"]),
]


def _fresh(G):
    G.graph.pop("_traversal_view", None)
    G.graph.pop("_path_search_graphs", None)


def test_traversal_view_is_built_once_per_graph(tmp_path):
    G = _load_graph(str(_write(tmp_path, EDGES)))
    assert G.is_directed()
    assert _traversal_view(G) is _traversal_view(G)


def test_cached_view_answers_like_a_fresh_one_in_any_order(tmp_path):
    G = _load_graph(str(_write(tmp_path, EDGES)))
    expected = []
    for q, mode, ctx in QUERIES:
        _fresh(G)
        expected.append(_query_graph_text(G, q, mode=mode, depth=3, context_filters=ctx))
    _fresh(G)
    for order in (QUERIES, list(reversed(QUERIES)), QUERIES):
        for q, mode, ctx in order:
            got = _query_graph_text(G, q, mode=mode, depth=3, context_filters=ctx)
            assert got == expected[QUERIES.index((q, mode, ctx))], (q, mode, ctx)


def test_reloaded_graph_gets_its_own_view(tmp_path):
    path = _write(tmp_path, EDGES)
    old = _load_graph(str(path))
    before = _query_graph_text(old, "ast_fn", depth=1)
    assert "NODE extra_fn" not in before
    _write(tmp_path, EDGES + [("extra", "ast", "calls", "call")])
    new = _load_graph(str(path))
    assert _traversal_view(new) is not _traversal_view(old)
    assert "NODE extra_fn" in _query_graph_text(new, "ast_fn", depth=1)
    assert _query_graph_text(old, "ast_fn", depth=1) == before


def test_path_search_graphs_are_built_once_per_direction(tmp_path):
    G = _load_graph(str(_write(tmp_path, EDGES)))
    directed = _path_search_graph(G, False)
    undirected = _path_search_graph(G, True)
    assert directed is _path_search_graph(G, False)
    assert undirected is _path_search_graph(G, True)
    assert directed.is_directed() and not undirected.is_directed()


def test_cached_shortest_path_answers_like_a_fresh_one(tmp_path):
    G = _load_graph(str(_write(tmp_path, EDGES)))
    cases = [
        {"source": "report_fn", "target": "lexer_fn"},
        {"source": "lexer_fn", "target": "report_fn"},
        {"source": "lexer_fn", "target": "report_fn", "undirected": True},
        {"source": "ast_fn", "target": "config_fn", "undirected": True},
    ]
    expected = []
    for c in cases:
        _fresh(G)
        expected.append(_shortest_path_text(G, dict(c)))
    _fresh(G)
    for _ in range(2):
        assert [_shortest_path_text(G, dict(c)) for c in cases] == expected


def test_reloaded_graph_gets_its_own_path_graph(tmp_path):
    path = _write(tmp_path, EDGES)
    old = _load_graph(str(path))
    assert "No directed path" in _shortest_path_text(old, {"source": "lexer_fn", "target": "ast_fn"})
    _write(tmp_path, EDGES + [("lexer", "ast", "calls", "call")])
    new = _load_graph(str(path))
    assert "Shortest path (1 hops)" in _shortest_path_text(new, {"source": "lexer_fn", "target": "ast_fn"})
    assert "No directed path" in _shortest_path_text(old, {"source": "lexer_fn", "target": "ast_fn"})
