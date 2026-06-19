"""Integration test for push_to_falkordb against a real FalkorDB instance.

Runs for real against `falkordb/falkordb:latest`:

    docker run -d -p 6379:6379 falkordb/falkordb:latest
    uv run pytest tests/test_falkordb_integration.py -q

The test auto-skips when the `falkordb` SDK is not installed or no FalkorDB is
reachable, so it is a no-op in the default CI (which runs no external services).
Host/port are overridable via FALKORDB_HOST / FALKORDB_PORT.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

falkordb = pytest.importorskip("falkordb")

FIXTURES = Path(__file__).parent / "fixtures"
HOST = os.environ.get("FALKORDB_HOST", "localhost")
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
GRAPH_NAME = "graphify_test"


def _connect():
    """Return a connected FalkorDB client, or skip if none is reachable."""
    try:
        db = falkordb.FalkorDB(host=HOST, port=PORT)
        db.connection.ping()
        return db
    except Exception as e:  # pragma: no cover - depends on local environment
        pytest.skip(f"no FalkorDB reachable at {HOST}:{PORT} ({e})")


@pytest.fixture()
def db():
    client = _connect()
    # Start from a clean slate and clean up afterwards.
    try:
        client.select_graph(GRAPH_NAME).delete()
    except Exception:
        pass
    yield client
    try:
        client.select_graph(GRAPH_NAME).delete()
    except Exception:
        pass


def test_push_to_falkordb_creates_expected_graph(db):
    from graphify.build import build_from_json
    from graphify.export import push_to_falkordb

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)

    result = push_to_falkordb(
        G, uri=f"{HOST}:{PORT}", graph_name=GRAPH_NAME
    )

    assert result["nodes"] == G.number_of_nodes()
    assert result["edges"] == G.number_of_edges()

    graph = db.select_graph(GRAPH_NAME)
    node_count = graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    edge_count = graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

    assert node_count == G.number_of_nodes()
    assert edge_count == G.number_of_edges()


def test_push_to_falkordb_is_idempotent(db):
    """MERGE-based push is safe to re-run - counts must not grow."""
    from graphify.build import build_from_json
    from graphify.export import push_to_falkordb

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)

    push_to_falkordb(G, uri=f"{HOST}:{PORT}", graph_name=GRAPH_NAME)
    push_to_falkordb(G, uri=f"{HOST}:{PORT}", graph_name=GRAPH_NAME)

    graph = db.select_graph(GRAPH_NAME)
    node_count = graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    edge_count = graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

    assert node_count == G.number_of_nodes()
    assert edge_count == G.number_of_edges()
