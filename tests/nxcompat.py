"""Minimal networkx-compatible shim for the test suite.

The FalkorDB solution ships no networkx dependency (the package has zero runtime
networkx imports). The suite still builds small in-memory graph fixtures with the
`nx.Graph()` / `nx.DiGraph()` + add_node/add_edge idiom, so this module provides a
drop-in `nx`: a mutable builder whose read API is delegated to the in-house
`MemGraph` (which already exposes the full nx-style view API). Tests import it as
`from tests import nxcompat as nx` — no networkx install required.
"""
from graphify.store import MemGraph


class _MutableGraph:
    """nx-like mutable graph; reads delegate to a lazily (re)built MemGraph."""

    def __init__(self, directed: bool):
        self._nodes: dict = {}
        self._edges: list = []
        self._directed = directed
        self.graph: dict = {}
        self._mg = None

    # --- construction (networkx API) ---
    def add_node(self, nid, **attrs):
        self._nodes.setdefault(nid, {}).update(attrs)
        self._mg = None

    def add_nodes_from(self, items):
        for it in items:
            if isinstance(it, (tuple, list)):
                self.add_node(it[0], **(it[1] if len(it) > 1 and it[1] else {}))
            else:
                self.add_node(it)

    def add_edge(self, u, v, **attrs):
        self._nodes.setdefault(u, {})
        self._nodes.setdefault(v, {})
        self._edges.append((u, v, attrs))
        self._mg = None

    def add_edges_from(self, items):
        for it in items:
            attrs = it[2] if len(it) > 2 and it[2] else {}
            self.add_edge(it[0], it[1], **attrs)

    def is_directed(self):
        return self._directed

    # --- read API: build a MemGraph (sharing the .graph dict) and delegate ---
    def _build(self) -> MemGraph:
        if self._mg is None:
            self._mg = MemGraph(list(self._nodes.items()), self._edges, directed=self._directed)
            self._mg.graph = self.graph
        return self._mg

    def __getattr__(self, name):
        # Only reached for names not set on the instance (nodes/edges/degree/
        # neighbors/subgraph/number_of_*/has_*/shortest_path/...).
        return getattr(self._build(), name)

    def __contains__(self, x):
        return x in self._build()

    def __iter__(self):
        return iter(self._build())

    def __len__(self):
        return len(self._build())

    def __getitem__(self, key):
        return self._build()[key]


class Graph(_MutableGraph):
    def __init__(self):
        super().__init__(directed=False)


class DiGraph(_MutableGraph):
    def __init__(self):
        super().__init__(directed=True)


def relabel_nodes(G, mapping):
    """Return a new graph with node ids remapped via `mapping` (unmapped ids kept)."""
    out = DiGraph() if G.is_directed() else Graph()
    for nid, data in G.nodes(data=True):
        out.add_node(mapping.get(nid, nid), **data)
    for u, v, data in G.edges(data=True):
        out.add_edge(mapping.get(u, u), mapping.get(v, v), **data)
    return out


def complete_graph(n):
    """Undirected graph on nodes 0..n-1 with every pair connected (nx semantics)."""
    out = Graph()
    for i in range(n):
        out.add_node(i)
    for i in range(n):
        for j in range(i + 1, n):
            out.add_edge(i, j)
    return out
