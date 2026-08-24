"""Contract tests for the index-driven DB push.

Production measurements on a real 1.87GB graph (1,211,189 nodes / ~1.15M
edges) against FalkorDB with the previous writers: node MERGEs without
indexes ran ~3.6s per 500-row batch (~137 entries/sec, ~60x slower than with
per-label (id) indexes created by hand), and the edge phase crawled at ~2
edges/sec because the edge MERGE matched its endpoints with NO label
(``MATCH (a {id: row.src}) ...``) — per-label indexes cannot serve
label-less lookups, so every edge full-scanned all 1.2M nodes twice, putting
1.15M edges days away.

The fix under test (graphify/exporters/graphdb.py, all four writers —
push_to_* and stream_push_to_*):

- every node gets the shared ``:GraphifyNode`` label (SHARED_NODE_LABEL) on
  top of its per-type label, added via ``SET n:<Type>`` on a MERGE that
  merges on the shared label + id;
- edge endpoints MATCH via the shared label, so the one GraphifyNode-(id)
  index serves both phases;
- indexes are created idempotently BEFORE any write (Neo4j: ``CREATE INDEX
  IF NOT EXISTS``; FalkorDB has no IF NOT EXISTS, so the "already indexed"
  error is tolerated by message);
- old-container contract = ADOPT-ON-PUSH: every push first runs one
  full-scan ``MATCH (n) WHERE n.id IS NOT NULL SET n:GraphifyNode`` so a
  container loaded by the previous unlabeled pusher is adopted in place and
  re-pushing over it never duplicates (verified below against a semantic
  fake that actually executes the emitted Cypher shapes).

Fake drivers only — no server, no network.
"""
from __future__ import annotations

import sys
import types

import networkx as nx
import pytest

from tests.test_batched_push import (
    _fake_falkordb_module,
    _fake_neo4j_module,
)
from tests.test_streaming_push import _synthetic_raw, _write

SHARED = "GraphifyNode"
SHARED_INDEX_FALKOR = f"CREATE INDEX FOR (n:{SHARED}) ON (n.id)"
SHARED_INDEX_NEO4J = f"CREATE INDEX IF NOT EXISTS FOR (n:{SHARED}) ON (n.id)"
ADOPT = f"MATCH (n) WHERE n.id IS NOT NULL SET n:{SHARED}"


def _small_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.add_node("a", file_type="python", label="A")
    G.add_node("b", file_type="markdown", label="B")
    G.add_edge("a", "b", relation="calls", confidence="INFERRED")
    return G


# ---------------------------------------------------------------------------
# (a) Index creation precedes all writes — all four writers
# ---------------------------------------------------------------------------

def _assert_setup_precedes_writes(cyphers: list[str], shared_index: str,
                                  index_for) -> None:
    """Shared index + adoption first; each type-label index before that
    label's first write; every write after the setup pair."""
    assert cyphers[0] == shared_index
    assert cyphers[1] == ADOPT
    for pos, cypher in enumerate(cyphers):
        if "UNWIND $rows AS row" in cypher and "SET n:" in cypher:
            label = cypher.split("SET n:")[1].split(" ")[0]
            assert index_for(label) in cyphers[:pos], (
                f"write for label {label} at {pos} not preceded by its index"
            )


def test_falkordb_in_memory_indexes_precede_writes(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import push_to_falkordb

    push_to_falkordb(_small_graph(), uri="localhost:6379")

    cyphers = [c for c, _ in recorded]
    _assert_setup_precedes_writes(
        cyphers, SHARED_INDEX_FALKOR,
        lambda label: f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    # In-memory: every index (shared + both type labels) precedes every write.
    first_write = next(i for i, c in enumerate(cyphers) if "UNWIND" in c)
    assert sorted(cyphers[:first_write]) == sorted([
        SHARED_INDEX_FALKOR, ADOPT,
        "CREATE INDEX FOR (n:Python) ON (n.id)",
        "CREATE INDEX FOR (n:Markdown) ON (n.id)",
    ])


def test_neo4j_in_memory_indexes_precede_writes(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import push_to_neo4j

    push_to_neo4j(_small_graph(), uri="bolt://x", user="neo4j", password="pw")

    cyphers = [c for c, _ in recorded]
    _assert_setup_precedes_writes(
        cyphers, SHARED_INDEX_NEO4J,
        lambda label: f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id)")


def test_falkordb_stream_indexes_precede_writes(tmp_path, monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import stream_push_to_falkordb

    path = _write(tmp_path, _synthetic_raw())
    stream_push_to_falkordb(path, uri="localhost:6379", batch_size=3)

    cyphers = [c for c, _ in recorded]
    _assert_setup_precedes_writes(
        cyphers, SHARED_INDEX_FALKOR,
        lambda label: f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    # Streaming creates each type-label index exactly once, at first
    # encounter — never again for later batches of the same label.
    index_ddl = [c for c in cyphers if c.startswith("CREATE INDEX")]
    assert len(index_ddl) == len(set(index_ddl))


def test_neo4j_stream_indexes_precede_writes(tmp_path, monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import stream_push_to_neo4j

    path = _write(tmp_path, _synthetic_raw())
    stream_push_to_neo4j(path, uri="bolt://x", user="neo4j", password="pw",
                         batch_size=3)

    cyphers = [c for c, _ in recorded]
    _assert_setup_precedes_writes(
        cyphers, SHARED_INDEX_NEO4J,
        lambda label: f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id)")
    index_ddl = [c for c in cyphers if c.startswith("CREATE INDEX")]
    assert len(index_ddl) == len(set(index_ddl))


# ---------------------------------------------------------------------------
# (b) Node and edge Cypher go through the shared label
# ---------------------------------------------------------------------------

def test_writes_use_shared_label_falkordb(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import push_to_falkordb

    push_to_falkordb(_small_graph(), uri="localhost:6379")

    writes = [(c, p) for c, p in recorded if "UNWIND $rows AS row" in c]
    node_writes = [(c, p) for c, p in writes if "MERGE (n:" in c]
    edge_writes = [(c, p) for c, p in writes if (c, p) not in node_writes]
    assert node_writes and edge_writes
    for cypher, _ in node_writes:
        assert f"MERGE (n:{SHARED} {{id: row.id}})" in cypher
        assert "SET n += row.props" in cypher
    for cypher, _ in edge_writes:
        assert (f"MATCH (a:{SHARED} {{id: row.src}}), "
                f"(b:{SHARED} {{id: row.tgt}})") in cypher
        assert "MERGE (a)-[r:CALLS]->(b) SET r += row.props" in cypher


def test_writes_use_shared_label_neo4j_stream(tmp_path, monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import stream_push_to_neo4j

    path = _write(tmp_path, _synthetic_raw())
    stream_push_to_neo4j(path, uri="bolt://x", user="neo4j", password="pw")

    writes = [(c, p) for c, p in recorded if "UNWIND $rows AS row" in c]
    assert writes
    for cypher, _ in writes:
        assert (f"MERGE (n:{SHARED} {{id: row.id}})" in cypher
                or f"MATCH (a:{SHARED} {{id: row.src}}), "
                   f"(b:{SHARED} {{id: row.tgt}})" in cypher)


# ---------------------------------------------------------------------------
# (c) Row payloads are byte-identical to the pre-index pusher
# ---------------------------------------------------------------------------

def test_row_payloads_unchanged(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import push_to_falkordb

    push_to_falkordb(_small_graph(), uri="localhost:6379",
                     communities={7: ["b"]})

    writes = [(c, p) for c, p in recorded if "UNWIND $rows AS row" in c]
    node_rows = [r for c, p in writes if "MERGE (n:" in c for r in p["rows"]]
    edge_rows = [r for c, p in writes if "MERGE (a)" in c for r in p["rows"]]
    # Exactly the shapes the unlabeled pusher sent — the type label moved
    # into the Cypher text (SET n:<Type>), never into the rows.
    assert node_rows == [
        {"id": "a", "props": {"file_type": "python", "label": "A", "id": "a"}},
        {"id": "b", "props": {"file_type": "markdown", "label": "B", "id": "b",
                              "community": 7}},
    ]
    assert edge_rows == [
        {"src": "a", "tgt": "b",
         "props": {"relation": "calls", "confidence": "INFERRED"}},
    ]


# ---------------------------------------------------------------------------
# Idempotent index creation: already-exists tolerated, real errors raised
# ---------------------------------------------------------------------------

def _neo4j_module_failing_index(recorded: list, message: str) -> types.ModuleType:
    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, cypher, **params):
            if cypher.startswith("CREATE INDEX"):
                raise RuntimeError(message)
            recorded.append((cypher, params))

    class _Driver:
        def session(self):
            return _Session()

        def close(self):
            pass

    class GraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return _Driver()

    mod = types.ModuleType("neo4j")
    mod.GraphDatabase = GraphDatabase
    return mod


def test_already_exists_index_response_is_tolerated(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _neo4j_module_failing_index(
        recorded, "An equivalent index already exists, "
                  "'Index( id=1, name='index_x' )'."))
    from graphify.export import push_to_neo4j

    result = push_to_neo4j(_small_graph(), uri="bolt://x", user="neo4j",
                           password="pw")

    assert result == {"nodes": 2, "edges": 1}          # push completed
    assert recorded[0][0] == ADOPT                      # adoption still ran
    assert any("UNWIND" in c for c, _ in recorded)      # writes still ran


def test_falkordb_already_indexed_response_is_tolerated(monkeypatch):
    recorded: list = []

    class _Graph:
        def query(self, cypher, params=None):
            if cypher.startswith("CREATE INDEX"):
                raise RuntimeError("Attribute 'id' is already indexed")
            recorded.append((cypher, params))

    class FalkorDB:
        def __init__(self, host, port, username=None, password=None):
            pass

        def select_graph(self, name):
            return _Graph()

    mod = types.ModuleType("falkordb")
    mod.FalkorDB = FalkorDB
    monkeypatch.setitem(sys.modules, "falkordb", mod)
    from graphify.export import push_to_falkordb

    result = push_to_falkordb(_small_graph(), uri="localhost:6379")

    assert result == {"nodes": 2, "edges": 1}
    assert recorded[0][0] == ADOPT


def test_unrelated_index_error_propagates(monkeypatch):
    monkeypatch.setitem(sys.modules, "neo4j", _neo4j_module_failing_index(
        [], "Connection refused"))
    from graphify.export import push_to_neo4j

    with pytest.raises(RuntimeError, match="Connection refused"):
        push_to_neo4j(_small_graph(), uri="bolt://x", user="neo4j",
                      password="pw")


# ---------------------------------------------------------------------------
# (d) Old-container contract: adopt-on-push, no duplicates — proven against a
# semantic fake that executes the emitted Cypher shapes over a node store.
# ---------------------------------------------------------------------------

class _SemanticFalkorGraph:
    """Executes exactly the query shapes the pusher emits, semantically.

    Nodes are {"labels": set, "props": dict}; MERGE on (:GraphifyNode {id})
    matches only nodes that CARRY the shared label — precisely the behaviour
    that would duplicate a legacy container if adoption did not run first.
    """

    def __init__(self):
        self.nodes: list[dict] = []
        self.edges: dict[tuple, dict] = {}
        self.indexes: set[str] = set()

    def _find(self, label: str, node_id):
        for node in self.nodes:
            if label in node["labels"] and node["props"].get("id") == node_id:
                return node
        return None

    def query(self, cypher, params=None):
        if cypher.startswith("CREATE INDEX"):
            label = cypher.split("FOR (n:")[1].split(")")[0]
            if label in self.indexes:
                raise RuntimeError(
                    f"Attribute 'id' is already indexed for label '{label}'")
            self.indexes.add(label)
            return
        if cypher == ADOPT:
            for node in self.nodes:
                if "id" in node["props"]:
                    node["labels"].add(SHARED)
            return
        if f"MERGE (n:{SHARED} {{id: row.id}})" in cypher:
            type_label = cypher.split("SET n:")[1].split(" ")[0]
            for row in params["rows"]:
                node = self._find(SHARED, row["id"])
                if node is None:
                    node = {"labels": {SHARED}, "props": {}}
                    self.nodes.append(node)
                node["labels"].add(type_label)
                node["props"].update(row["props"])
            return
        if (f"MATCH (a:{SHARED} {{id: row.src}}), "
                f"(b:{SHARED} {{id: row.tgt}})") in cypher:
            rel = cypher.split("MERGE (a)-[r:")[1].split("]")[0]
            for row in params["rows"]:
                a = self._find(SHARED, row["src"])
                b = self._find(SHARED, row["tgt"])
                if a is None or b is None:
                    continue  # MATCH bound nothing; the MERGE never ran
                self.edges.setdefault((id(a), id(b), rel), {}).update(row["props"])
            return
        raise AssertionError(f"semantic fake got unexpected cypher: {cypher}")


def _semantic_falkordb_module(store: _SemanticFalkorGraph) -> types.ModuleType:
    class FalkorDB:
        def __init__(self, host, port, username=None, password=None):
            pass

        def select_graph(self, name):
            return store

    mod = types.ModuleType("falkordb")
    mod.FalkorDB = FalkorDB
    return mod


def _seed_legacy_container(store: _SemanticFalkorGraph, raw: dict) -> None:
    """Load the store the way the OLD unlabeled pusher left it: per-type
    label only, NO shared label, props exactly as pushed."""
    from graphify.exporters.graphdb import _stream_safe_label

    for item in raw["nodes"]:
        props = {k: v for k, v in item.items()
                 if isinstance(v, (str, int, float, bool))
                 and not k.startswith("_")}
        props["id"] = item["id"]
        label = _stream_safe_label(item.get("file_type", "Entity").capitalize())
        store.nodes.append({"labels": {label}, "props": props})


def test_old_unlabeled_container_is_adopted_without_duplicates(tmp_path, monkeypatch):
    raw = _synthetic_raw()
    path = _write(tmp_path, raw)
    store = _SemanticFalkorGraph()
    _seed_legacy_container(store, raw)
    assert all(SHARED not in n["labels"] for n in store.nodes)  # true legacy

    monkeypatch.setitem(sys.modules, "falkordb", _semantic_falkordb_module(store))
    from graphify.export import stream_push_to_falkordb
    result = stream_push_to_falkordb(path, uri="localhost:6379", batch_size=3)

    assert result == {"nodes": 12, "edges": 11}
    # No duplicates: the 12 legacy nodes were adopted in place, not recreated.
    assert len(store.nodes) == 12
    assert all(SHARED in n["labels"] for n in store.nodes)
    # Every edge bound real endpoints (no MATCH miss silently dropped rows).
    assert len(store.edges) == 11


def test_repush_over_migrated_container_stays_idempotent(tmp_path, monkeypatch):
    raw = _synthetic_raw()
    path = _write(tmp_path, raw)
    store = _SemanticFalkorGraph()
    monkeypatch.setitem(sys.modules, "falkordb", _semantic_falkordb_module(store))
    from graphify.export import stream_push_to_falkordb

    stream_push_to_falkordb(path, uri="localhost:6379", batch_size=3)
    nodes_after_first = len(store.nodes)
    edges_after_first = len(store.edges)

    # Second push: indexes now exist (the fake raises "already indexed",
    # which must be tolerated) and every MERGE must match, not create.
    result = stream_push_to_falkordb(path, uri="localhost:6379", batch_size=3)

    assert result == {"nodes": 12, "edges": 11}
    assert len(store.nodes) == nodes_after_first == 12
    assert len(store.edges) == edges_after_first == 11
