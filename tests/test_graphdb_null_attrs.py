"""Regression tests for None / null node and edge attributes in graphdb exporters."""
from __future__ import annotations

import sys
import types

import networkx as nx
import pytest

from graphify.exporters.graphdb import _distinct_node_labels, push_to_falkordb, push_to_neo4j


class _RecordingTarget:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def query(self, cypher: str, params: dict | None = None) -> None:
        self.calls.append((cypher, params or {}))

    def run(self, cypher: str, **params) -> None:
        self.calls.append((cypher, params))

    def __enter__(self) -> "_RecordingTarget":
        return self

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture()
def fake_neo4j(monkeypatch):
    target = _RecordingTarget()
    driver = types.SimpleNamespace(session=lambda: target, close=lambda: None)
    module = types.SimpleNamespace(
        GraphDatabase=types.SimpleNamespace(driver=lambda uri, auth=None: driver)
    )
    monkeypatch.setitem(sys.modules, "neo4j", module)
    return target


@pytest.fixture()
def fake_falkordb(monkeypatch):
    target = _RecordingTarget()
    client = types.SimpleNamespace(select_graph=lambda name: target)
    module = types.SimpleNamespace(FalkorDB=lambda **kwargs: client)
    monkeypatch.setitem(sys.modules, "falkordb", module)
    return target


def _null_attr_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label=None, file_type=None)
    G.add_node("n2", label="ok", file_type="code")
    G.add_edge("n1", "n2", relation=None)
    return G


def test_distinct_node_labels_handles_none_file_type():
    G = nx.Graph()
    G.add_node("n1", label=None, file_type=None)
    G.add_node("n2", label="foo", file_type="code")

    assert _distinct_node_labels(G) == ["Code", "Entity"]


def test_push_to_neo4j_handles_null_file_type_label_and_relation(fake_neo4j):
    result = push_to_neo4j(_null_attr_graph(), uri="bolt://localhost:7687", user="neo4j", password="pw")

    assert result == {"nodes": 2, "edges": 1}
    cyphers = [c for c, _ in fake_neo4j.calls]
    assert "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.id)" in cyphers
    assert any(c.startswith("MERGE (n:Entity ") for c in cyphers)
    assert any("MERGE (a)-[r:RELATED_TO]->(b)" in c for c in cyphers)

    n1_params = [p for c, p in fake_neo4j.calls if c.startswith("MERGE (n:Entity ")][0]
    assert n1_params["props"] == {"id": "n1"}


def test_push_to_falkordb_handles_null_file_type_label_and_relation(fake_falkordb):
    result = push_to_falkordb(_null_attr_graph(), uri="localhost:6379", graph_name="graphify")

    assert result == {"nodes": 2, "edges": 1}
    cyphers = [c for c, _ in fake_falkordb.calls]
    assert "CREATE INDEX FOR (n:Entity) ON (n.id)" in cyphers
    assert any(c.startswith("MERGE (n:Entity ") for c in cyphers)
    assert any("MERGE (a)-[r:RELATED_TO]->(b)" in c for c in cyphers)

    n1_params = [p for c, p in fake_falkordb.calls if c.startswith("MERGE (n:Entity ")][0]
    assert n1_params["props"] == {"id": "n1"}


def test_push_handles_empty_string_file_type_and_relation(fake_neo4j, fake_falkordb):
    G = nx.Graph()
    G.add_node("a", label="a", file_type="")
    G.add_node("b", label="b", file_type="")
    G.add_edge("a", "b", relation="")

    assert push_to_neo4j(G, uri="bolt://localhost:7687", user="neo4j", password="pw") == {
        "nodes": 2,
        "edges": 1,
    }
    assert push_to_falkordb(G, uri="localhost:6379") == {"nodes": 2, "edges": 1}
