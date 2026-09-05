"""Tier-2 integration tests for graphify.age_snapshots (docs/AGE_PLAN.md
"Testing strategy"): a live PostgreSQL instance is required, but the AGE
extension is NOT -- graphify_snapshots is a plain SQL table outside any AGE
graph namespace. Reuses the same apache/age container as
tests/test_age_registry_integration.py for convenience.

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_snapshots_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching test_age_registry_integration.py's convention.
"""
from __future__ import annotations

import os
import uuid

import networkx as nx
import pytest

psycopg = pytest.importorskip("psycopg")

from graphify import age_registry as reg  # noqa: E402
from graphify import age_snapshots as snap  # noqa: E402

HOST = os.environ.get("AGE_HOST", "localhost")
PORT = int(os.environ.get("AGE_PORT", "5432"))
DBNAME = os.environ.get("AGE_DB", "postgres")
USER = os.environ.get("AGE_USER", "postgres")
PASSWORD = os.environ.get("AGE_PASSWORD", "graphify_test")


def _conninfo() -> str:
    return f"host={HOST} port={PORT} dbname={DBNAME} user={USER} password={PASSWORD}"


def _connect_or_skip():
    try:
        conn = psycopg.connect(_conninfo(), connect_timeout=5)
    except Exception as e:  # pragma: no cover - depends on local environment
        pytest.skip(f"no Postgres reachable at {HOST}:{PORT} ({e})")
    return conn


def _drop_registry_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS
                graphify_quality_findings,
                graphify_branch_diff,
                graphify_branch_revisions,
                graphify_branches,
                graphify_snapshots,
                graphify_repos,
                graphify_registry_migrations
            CASCADE;
        """)
    conn.commit()


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    _drop_registry_tables(c)
    yield c
    _drop_registry_tables(c)
    c.close()


@pytest.fixture()
def repository_id(conn) -> str:
    remote = f"https://github.com/testowner/repo-{uuid.uuid4().hex[:8]}.git"
    row = reg.register_repository(_conninfo(), remote, default_branch="main")
    return row["repository_id"]


def _graph(nodes, edges):
    G = nx.Graph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    return G


def test_latest_snapshot_graph_unregistered_repo_returns_none(conn):
    graph, commit_sha = snap.latest_snapshot_graph(_conninfo(), str(uuid.uuid4()))
    assert graph is None and commit_sha is None


def test_latest_snapshot_graph_unmigrated_db_returns_none():
    """No graphify_repos/graphify_snapshots tables at all yet -- must not
    raise UndefinedTable (mirrors age_registry.resolve_age_graph_name)."""
    conn = _connect_or_skip()
    _drop_registry_tables(conn)
    try:
        graph, commit_sha = snap.latest_snapshot_graph(_conninfo(), str(uuid.uuid4()))
        assert graph is None and commit_sha is None
    finally:
        conn.close()


def test_first_push_is_recorded_as_a_checkpoint(conn, repository_id):
    G = _graph([("a", {"label": "A"})], [])
    result = snap.record_snapshot(
        _conninfo(), repository_id, "c1", G,
        graphify_version="0.9.54", schema_version="1",
    )
    assert result["kind"] == "checkpoint"
    with conn.cursor() as cur:
        cur.execute("SELECT kind FROM graphify_snapshots WHERE repository_id = %s;", (repository_id,))
        rows = cur.fetchall()
    assert rows == [("checkpoint",)]


def test_second_push_is_recorded_as_a_delta(conn, repository_id):
    G1 = _graph([("a", {"label": "A"})], [])
    G2 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})], [])
    snap.record_snapshot(_conninfo(), repository_id, "c1", G1,
                          graphify_version="0.9.54", schema_version="1")
    result = snap.record_snapshot(_conninfo(), repository_id, "c2", G2,
                                   graphify_version="0.9.54", schema_version="1")
    assert result["kind"] == "delta"


def test_latest_snapshot_graph_reconstructs_after_checkpoint_and_delta(conn, repository_id):
    G1 = _graph([("a", {"label": "A"})], [])
    G2 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})],
                [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})])
    snap.record_snapshot(_conninfo(), repository_id, "c1", G1,
                          graphify_version="0.9.54", schema_version="1")
    snap.record_snapshot(_conninfo(), repository_id, "c2", G2,
                          graphify_version="0.9.54", schema_version="1")

    graph, commit_sha = snap.latest_snapshot_graph(_conninfo(), repository_id)
    assert commit_sha == "c2"
    assert set(graph.nodes()) == {"a", "b"}
    assert graph.has_edge("a", "b")


def test_checkpoint_cadence_triggers_on_the_nth_push(conn, repository_id):
    for i in range(5):
        G = _graph([(f"n{i}", {"label": f"N{i}"})], [])
        result = snap.record_snapshot(
            _conninfo(), repository_id, f"c{i}", G,
            graphify_version="0.9.54", schema_version="1", cadence=3,
        )
        expected_kind = "checkpoint" if i % 3 == 0 else "delta"
        assert result["kind"] == expected_kind, f"push {i} expected {expected_kind}"


def test_record_snapshot_is_idempotent_for_same_commit(conn, repository_id):
    G = _graph([("a", {"label": "A"})], [])
    snap.record_snapshot(_conninfo(), repository_id, "c1", G,
                          graphify_version="0.9.54", schema_version="1")
    snap.record_snapshot(_conninfo(), repository_id, "c1", G,
                          graphify_version="0.9.54", schema_version="1")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graphify_snapshots WHERE repository_id = %s;", (repository_id,))
        (count,) = cur.fetchone()
    assert count == 1


def test_full_cycle_matches_incremental_push_diff(conn, repository_id):
    """The scenario push_to_age() actually relies on: reconstruct the last
    snapshot, diff the new graph against it, and confirm the diff matches
    what really changed."""
    from graphify.analyze import graph_diff

    G1 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})],
                [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})])
    snap.record_snapshot(_conninfo(), repository_id, "c1", G1,
                          graphify_version="0.9.54", schema_version="1")

    G2 = _graph([("a", {"label": "A"}), ("c", {"label": "C"})],
                [("a", "c", {"relation": "uses", "confidence": "INFERRED"})])
    old_graph, old_commit = snap.latest_snapshot_graph(_conninfo(), repository_id)
    assert old_commit == "c1"
    diff = graph_diff(old_graph, G2)
    assert {n["id"] for n in diff["new_nodes"]} == {"c"}
    assert {n["id"] for n in diff["removed_nodes"]} == {"b"}

    snap.record_snapshot(_conninfo(), repository_id, "c2", G2,
                          graphify_version="0.9.54", schema_version="1")
    final_graph, final_commit = snap.latest_snapshot_graph(_conninfo(), repository_id)
    assert final_commit == "c2"
    assert set(final_graph.nodes()) == {"a", "c"}
