"""#3804: graph DB pushes must index (label, id) before the MERGE upsert loop.

`push_to_falkordb` / `push_to_neo4j` upsert every node with

    MERGE (n:<Label> {id: $id}) SET n += $props

which matches on ``(label, id)``. With no index on ``(n.id)`` the engine has to
scan every node already carrying that label to decide whether the node is new,
so each upsert costs O(nodes with that label) and a full push degrades to
O(n^2). Reported on a 167,428-node / 209,215-edge graph, where throughput
collapsed from ~10,000 node upserts/60s to ~100 upserts/300s partway through.

These tests drive the two push functions with fake SDK clients and assert the
Cypher that reaches the server, so they run without a database.
"""
from __future__ import annotations

import sys
import types

import networkx as nx
import pytest


def _graph() -> nx.Graph:
    """Two labels, so the per-label index creation is observable."""
    G = nx.Graph()
    G.add_node("parse_config", label="parse_config()", file_type="code", source_file="a.py")
    G.add_node("load_settings", label="load_settings()", file_type="code", source_file="a.py")
    G.add_node("sftp_service", label="SFTP service", file_type="document", source_file="b.md")
    G.add_node("payroll_db", label="Payroll DB", file_type="database", source_file="b.md")
    G.add_edge("parse_config", "sftp_service", relation="reads")
    G.add_edge("load_settings", "payroll_db", relation="reads")
    return G


class _RecordingGraph:
    """Stand-in for the FalkorDB graph handle; records Cypher in call order."""

    def __init__(self, fail_on_index: bool = False) -> None:
        self.calls: list[str] = []
        self._fail_on_index = fail_on_index

    def query(self, cypher: str, params: dict | None = None) -> None:
        self.calls.append(cypher)
        if self._fail_on_index and cypher.startswith("CREATE INDEX"):
            # What a re-run against an already-indexed graph gets back:
            # FalkorDB's CREATE INDEX has no IF NOT EXISTS.
            raise RuntimeError("index already exists")


class _RecordingSession:
    def __init__(self, graph: _RecordingGraph) -> None:
        self._graph = graph
        self.closed = False

    def run(self, cypher: str, **params) -> None:
        self._graph.calls.append(cypher)

    def __enter__(self) -> "_RecordingSession":
        return self

    def __exit__(self, *exc) -> bool:
        self.closed = True
        return False


@pytest.fixture()
def fake_falkordb(monkeypatch):
    """Install a fake `falkordb` module and return its recording graph handle."""
    graph = _RecordingGraph()
    client = types.SimpleNamespace(
        select_graph=lambda name: graph,
    )
    module = types.SimpleNamespace(FalkorDB=lambda **kwargs: client)
    monkeypatch.setitem(sys.modules, "falkordb", module)
    return graph


@pytest.fixture()
def fake_neo4j(monkeypatch):
    """Install a fake `neo4j` module and return its recording graph handle."""
    graph = _RecordingGraph()
    session = _RecordingSession(graph)
    driver = types.SimpleNamespace(
        session=lambda: session,
        close=lambda: None,
    )
    module = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda uri, auth=None: driver))
    monkeypatch.setitem(sys.modules, "neo4j", module)
    return graph


def test_falkordb_push_indexes_each_label_before_upserting(fake_falkordb):
    """Every MERGE label is indexed first, and before the first MERGE runs."""
    from graphify.exporters.graphdb import push_to_falkordb

    result = push_to_falkordb(_graph(), uri="localhost:6379", graph_name="graphify")

    assert result == {"nodes": 4, "edges": 2}

    indexes = [c for c in fake_falkordb.calls if c.startswith("CREATE INDEX")]
    merges = [i for i, c in enumerate(fake_falkordb.calls) if c.startswith("MERGE")]

    # One index per distinct label: the two code nodes share "Code", and
    # "document" and "database" each get their own.
    assert indexes == [
        "CREATE INDEX FOR (n:Code) ON (n.id)",
        "CREATE INDEX FOR (n:Database) ON (n.id)",
        "CREATE INDEX FOR (n:Document) ON (n.id)",
    ]
    assert merges, "expected the push to still upsert nodes"
    assert fake_falkordb.calls.index(indexes[-1]) < merges[0]


def test_falkordb_push_indexes_before_the_upsert_loop_runs(fake_falkordb):
    """Ordering, stated as the property it protects: no MERGE precedes its index."""
    from graphify.exporters.graphdb import push_to_falkordb

    push_to_falkordb(_graph(), uri="localhost:6379", graph_name="graphify")

    seen_index: set[str] = set()
    for cypher in fake_falkordb.calls:
        if cypher.startswith("CREATE INDEX FOR (n:"):
            seen_index.add(cypher.split("(n:")[1].split(")")[0])
            continue
        if cypher.startswith("MERGE (n:"):
            label = cypher.split("MERGE (n:")[1].split(" ")[0]
            assert label in seen_index, f"MERGE on unindexed label {label}: {cypher}"


def test_falkordb_push_survives_an_existing_index(monkeypatch):
    """FalkorDB has no IF NOT EXISTS, so a re-push must not abort on the error."""
    from graphify.exporters.graphdb import push_to_falkordb

    graph = _RecordingGraph(fail_on_index=True)
    client = types.SimpleNamespace(select_graph=lambda name: graph)
    monkeypatch.setitem(sys.modules, "falkordb", types.SimpleNamespace(FalkorDB=lambda **kw: client))

    result = push_to_falkordb(_graph(), uri="localhost:6379", graph_name="graphify")

    # The push still upserts every node and edge despite the index errors.
    assert result == {"nodes": 4, "edges": 2}
    assert sum(1 for c in graph.calls if c.startswith("MERGE (n:")) == 4
    assert sum(1 for c in graph.calls if c.startswith("CREATE INDEX")) == 3


def test_neo4j_push_indexes_each_label_before_upserting(fake_neo4j):
    """The Neo4j path had the same gap; it uses IF NOT EXISTS to stay idempotent."""
    from graphify.exporters.graphdb import push_to_neo4j

    result = push_to_neo4j(_graph(), uri="bolt://localhost:7687", user="neo4j", password="x")

    assert result == {"nodes": 4, "edges": 2}

    indexes = [c for c in fake_neo4j.calls if c.startswith("CREATE INDEX")]
    merges = [i for i, c in enumerate(fake_neo4j.calls) if c.startswith("MERGE")]

    assert indexes == [
        "CREATE INDEX IF NOT EXISTS FOR (n:Code) ON (n.id)",
        "CREATE INDEX IF NOT EXISTS FOR (n:Database) ON (n.id)",
        "CREATE INDEX IF NOT EXISTS FOR (n:Document) ON (n.id)",
    ]
    assert merges
    assert fake_neo4j.calls.index(indexes[-1]) < merges[0]


def test_distinct_node_labels_sanitizes_like_the_push_loop():
    """The index set must not contain a label the MERGE loop would never write."""
    from graphify.exporters.graphdb import _distinct_node_labels

    G = nx.Graph()
    # "code" -> "Code"; an all-punctuation value collapses to the "Entity"
    # fallback, exactly as _safe_label does inside the push loops.
    G.add_node("a", file_type="code")
    G.add_node("b", file_type="Code")
    G.add_node("c", file_type="!!!")
    G.add_node("d")  # no file_type at all -> "Entity"

    assert _distinct_node_labels(G) == ["Code", "Entity"]
