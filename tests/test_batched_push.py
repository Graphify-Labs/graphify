"""Unit tests for the batched UNWIND push to Neo4j and FalkorDB.

The per-entry push ran one query per node/edge, so a remote push spent nearly
all its time on round trips. These tests verify the batched replacement with
fake in-memory drivers (no server, no network): rows are grouped by sanitized
label/relation (labels cannot be Cypher parameters), chunked into batch_size
rows per query, and the row payloads carry exactly the per-entry params so
MERGE/SET upsert semantics are unchanged.
"""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import networkx as nx
import pytest

PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Fake drivers - record every (cypher, params) pair, touch no network.
# ---------------------------------------------------------------------------

def _fake_neo4j_module(recorded: list) -> types.ModuleType:
    """A stand-in for the `neo4j` package recording every session.run call."""

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, cypher, **params):
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


def _fake_falkordb_module(recorded: list) -> types.ModuleType:
    """A stand-in for the `falkordb` package recording every graph.query call."""

    class _Graph:
        def query(self, cypher, params):
            recorded.append((cypher, params))

    class FalkorDB:
        def __init__(self, host, port, username=None, password=None):
            pass

        def select_graph(self, name):
            return _Graph()

    mod = types.ModuleType("falkordb")
    mod.FalkorDB = FalkorDB
    return mod


def _make_graph(n_nodes: int = 0) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    for i in range(n_nodes):
        G.add_node(f"node-{i}", file_type="python", label=f"Node {i}")
    return G


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------

def test_neo4j_nodes_are_chunked_by_batch_size(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import push_to_neo4j

    G = _make_graph(250)
    result = push_to_neo4j(G, uri="bolt://x", user="neo4j", password="pw",
                           batch_size=100)

    assert result == {"nodes": 250, "edges": 0}
    # One label -> ceil(250 / 100) = 3 round trips instead of 250.
    assert len(recorded) == 3
    assert [len(p["rows"]) for _, p in recorded] == [100, 100, 50]
    for cypher, _ in recorded:
        assert "UNWIND $rows AS row" in cypher
        assert "MERGE (n:Python {id: row.id})" in cypher
        assert "SET n += row.props" in cypher
    # Every node arrives exactly once, in graph order, with the id in props
    # exactly as the per-entry queries sent it.
    all_rows = [r for _, p in recorded for r in p["rows"]]
    assert [r["id"] for r in all_rows] == [f"node-{i}" for i in range(250)]
    assert all_rows[0]["props"]["id"] == "node-0"
    assert all_rows[0]["props"]["label"] == "Node 0"


def test_neo4j_nodes_are_grouped_by_sanitized_label(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import push_to_neo4j

    G = nx.MultiDiGraph()
    G.add_node("a", file_type="python")
    G.add_node("b", file_type="markdown")
    G.add_node("c", file_type="python")
    # Injection attempt must be sanitized, not parameterized away.
    G.add_node("d", file_type="x) DETACH DELETE n //")

    result = push_to_neo4j(G, uri="bolt://x", user="neo4j", password="pw")

    assert result["nodes"] == 4
    labels = sorted(c.split("MERGE (n:")[1].split(" ")[0] for c, _ in recorded)
    assert labels == ["Markdown", "Python", "Xdetachdeleten"]
    by_label = {c.split("MERGE (n:")[1].split(" ")[0]: p["rows"] for c, p in recorded}
    assert [r["id"] for r in by_label["Python"]] == ["a", "c"]


def test_neo4j_edges_are_grouped_and_batched(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import push_to_neo4j

    G = _make_graph(3)
    G.add_edge("node-0", "node-1", relation="calls", confidence="INFERRED")
    G.add_edge("node-1", "node-2", relation="calls")
    G.add_edge("node-0", "node-2", relation="imports")

    result = push_to_neo4j(G, uri="bolt://x", user="neo4j", password="pw",
                           batch_size=100)

    assert result == {"nodes": 3, "edges": 3}
    edge_queries = [(c, p) for c, p in recorded if "MATCH (a {id: row.src})" in c]
    assert len(edge_queries) == 2  # one per relation: CALLS, IMPORTS
    by_rel = {c.split("MERGE (a)-[r:")[1].split("]")[0]: p["rows"]
              for c, p in edge_queries}
    assert sorted(by_rel) == ["CALLS", "IMPORTS"]
    assert [(r["src"], r["tgt"]) for r in by_rel["CALLS"]] == [
        ("node-0", "node-1"), ("node-1", "node-2")
    ]
    assert by_rel["CALLS"][0]["props"] == {"relation": "calls", "confidence": "INFERRED"}


def test_neo4j_community_lands_in_props(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module(recorded))
    from graphify.export import push_to_neo4j

    G = _make_graph(2)
    push_to_neo4j(G, uri="bolt://x", user="neo4j", password="pw",
                  communities={7: ["node-1"]})

    rows = recorded[0][1]["rows"]
    by_id = {r["id"]: r["props"] for r in rows}
    assert by_id["node-1"]["community"] == 7
    assert "community" not in by_id["node-0"]


def test_neo4j_rejects_nonpositive_batch_size(monkeypatch):
    monkeypatch.setitem(sys.modules, "neo4j", _fake_neo4j_module([]))
    from graphify.export import push_to_neo4j

    with pytest.raises(ValueError, match="batch_size"):
        push_to_neo4j(_make_graph(1), uri="bolt://x", user="neo4j",
                      password="pw", batch_size=0)


# ---------------------------------------------------------------------------
# FalkorDB
# ---------------------------------------------------------------------------

def test_falkordb_nodes_and_edges_are_batched(monkeypatch):
    recorded: list = []
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module(recorded))
    from graphify.export import push_to_falkordb

    G = _make_graph(150)
    G.add_edge("node-0", "node-1", relation="calls")

    result = push_to_falkordb(G, uri="localhost:6379", batch_size=100)

    assert result == {"nodes": 150, "edges": 1}
    node_queries = [(c, p) for c, p in recorded if "MERGE (n:" in c]
    edge_queries = [(c, p) for c, p in recorded if "MATCH (a {id: row.src})" in c]
    assert len(node_queries) == 2  # 100 + 50
    assert [len(p["rows"]) for _, p in node_queries] == [100, 50]
    assert len(edge_queries) == 1
    for cypher, params in recorded:
        assert "UNWIND $rows AS row" in cypher
        assert set(params) == {"rows"}  # positional params dict, rows only
    assert edge_queries[0][1]["rows"] == [
        {"src": "node-0", "tgt": "node-1", "props": {"relation": "calls"}}
    ]


def test_falkordb_rejects_nonpositive_batch_size(monkeypatch):
    monkeypatch.setitem(sys.modules, "falkordb", _fake_falkordb_module([]))
    from graphify.export import push_to_falkordb

    with pytest.raises(ValueError, match="batch_size"):
        push_to_falkordb(_make_graph(1), uri="localhost:6379", batch_size=-1)


# ---------------------------------------------------------------------------
# CLI flag validation (no graph, no driver, no network - rejected on parse)
# ---------------------------------------------------------------------------

def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_cli_rejects_zero_batch_size(tmp_path):
    proc = _run_cli(["export", "neo4j", "--push", "bolt://x", "--batch-size", "0"],
                    cwd=tmp_path)
    assert proc.returncode == 2
    assert "error: --batch-size must be a positive integer" in proc.stderr


def test_cli_rejects_non_integer_batch_size(tmp_path):
    proc = _run_cli(["export", "falkordb", "--push", "localhost:6379",
                     "--batch-size", "many"], cwd=tmp_path)
    assert proc.returncode == 2
    assert "error: --batch-size must be an integer" in proc.stderr
