"""`_query_graph_text` on the directed graph `_load_graph` builds (the MCP path).

The CLI `query` loads graph.json undirected and is covered by
tests/test_query_cli.py::test_query_cli_preserves_calls_direction_when_seeded_on_callee.
The MCP server loads the same file through `_load_graph`, which forces
`directed: True` (#2309), and `_bfs`/`_dfs` expand through `G.neighbors()` —
successors only on a DiGraph. Seeded on a node with no outgoing edges the
traversal therefore stopped at the seed, and `query_graph` answered with one
node where the CLI answered with the callers.
"""
import json

import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import _load_graph, _query_graph_text


def _write_calls_graph(tmp_path):
    """One `calls` edge, on-disk undirected — the `graphify extract` shape."""
    G = nx.Graph()
    G.add_node("caller", label="caller_fn", source_file="a.py", source_location="L1", community=0)
    G.add_node("callee", label="callee_fn", source_file="b.py", source_location="L1", community=1)
    G.add_edge("caller", "callee", relation="calls", confidence="EXTRACTED", context="call")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_mcp_query_seeded_on_callee_reaches_the_caller(tmp_path):
    G = _load_graph(str(tmp_path / "graph.json")) if False else _load_graph(str(_write_calls_graph(tmp_path)))
    assert G.is_directed()  # the precondition the defect depends on
    for mode in ("bfs", "dfs"):
        text = _query_graph_text(G, "callee_fn", mode=mode, depth=2)
        assert "2 nodes found" in text, text
        assert "NODE caller_fn" in text
        # Direction is rendered from the stored edge, not from the visit order.
        assert "caller_fn --calls" in text
        assert "callee_fn --calls" not in text


def test_mcp_query_seeded_on_caller_is_unchanged(tmp_path):
    G = _load_graph(str(_write_calls_graph(tmp_path)))
    text = _query_graph_text(G, "caller_fn", mode="bfs", depth=2)
    assert "2 nodes found" in text
    assert "caller_fn --calls" in text
    assert "callee_fn --calls" not in text


def test_mcp_query_explicit_context_filter_still_applies(tmp_path):
    G = _load_graph(str(_write_calls_graph(tmp_path)))
    kept = _query_graph_text(G, "callee_fn", depth=2, context_filters=["call"])
    assert "Context: call (explicit)" in kept and "NODE caller_fn" in kept
    dropped = _query_graph_text(G, "callee_fn", depth=2, context_filters=["import"])
    assert "Context: import (explicit)" in dropped and "NODE caller_fn" not in dropped


def test_traversal_view_keeps_multigraph_parallel_and_mutual_edges():
    from graphify.serve import _traversal_view
    G = nx.MultiDiGraph()
    G.add_node("a", label="a"); G.add_node("b", label="b")
    G.add_edge("a", "b", relation="calls"); G.add_edge("a", "b", relation="imports")
    # Mutual arcs get key 0 on both sides of the DiGraph; on an undirected
    # multigraph that key names one edge per unordered pair, so carrying the
    # keys over would collapse a<->b into a single edge.
    G.add_edge("b", "a", relation="calls")
    H = _traversal_view(G)
    assert not H.is_directed() and H.is_multigraph()
    assert H.number_of_edges() == 3
    assert sorted((d["_src"], d["_tgt"]) for _, _, d in H.edges(data=True)) == [("a", "b"), ("a", "b"), ("b", "a")]


def test_traversal_view_leaves_undirected_graph_alone():
    from graphify.serve import _traversal_view
    G = nx.Graph()
    G.add_edge("a", "b", relation="calls")
    assert _traversal_view(G) is G


def test_traversal_view_folds_mutual_arcs_like_the_cli_loader(tmp_path):
    """On a plain DiGraph, u->v and v->u become one undirected edge — the same
    fold the CLI's undirected load of graph.json performs, so the two read
    surfaces keep returning the same subgraph."""
    from graphify.serve import _traversal_view
    G = nx.Graph()
    G.add_node("a", label="a_fn", source_file="a.py", source_location="L1", community=0)
    G.add_node("b", label="b_fn", source_file="b.py", source_location="L1", community=0)
    # An undirected on-disk graph can only hold one a-b link; write it as the
    # links list explicitly so both directions are present on disk.
    data = json_graph.node_link_data(G, edges="links")
    data["links"] = [
        {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED", "context": "call"},
        {"source": "b", "target": "a", "relation": "calls", "confidence": "EXTRACTED", "context": "call"},
    ]
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    cli_like = json_graph.node_link_graph(json.loads(p.read_text()), edges="links")
    mcp_view = _traversal_view(_load_graph(str(p)))
    assert cli_like.number_of_edges() == mcp_view.number_of_edges() == 1
