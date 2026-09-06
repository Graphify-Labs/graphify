"""Tier-3 integration fixtures for docs/AGE_PLAN.md Phase 5: the review-
agent and quality-agent query contract. Each test seeds a live AGE
instance and executes one of the pinned queries from docs/AGE_SCHEMA.md's
"Example pinned queries" section verbatim (or with only parameter
substitution), so the doc can never silently drift from what actually
runs.

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_agent_queries_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching the other AGE live-suite files' convention.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql  # noqa: E402

from graphify import age_registry as reg  # noqa: E402
from graphify.analyze import god_nodes  # noqa: E402
from graphify.build import build_from_json  # noqa: E402
from graphify.exporters.graphdb import push_to_age  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
HOST = os.environ.get("AGE_HOST", "localhost")
PORT = int(os.environ.get("AGE_PORT", "5432"))
DBNAME = os.environ.get("AGE_DB", "postgres")
USER = os.environ.get("AGE_USER", "postgres")
PASSWORD = os.environ.get("AGE_PASSWORD", "graphify_test")
GRAPH_NAME = "graphify_agent_queries_test"


def _conninfo() -> str:
    return f"host={HOST} port={PORT} dbname={DBNAME} user={USER} password={PASSWORD}"


def _connect_or_skip():
    try:
        conn = psycopg.connect(_conninfo(), connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
        conn.rollback()
    except Exception as e:  # pragma: no cover - depends on local environment
        pytest.skip(f"no AGE-enabled Postgres reachable at {HOST}:{PORT} ({e})")
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


def _drop_graph_if_exists(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (name,))
        if cur.fetchone()[0]:
            cur.execute("SELECT drop_graph(%s, true);", (name,))
    conn.commit()


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    _drop_registry_tables(c)
    _drop_graph_if_exists(c, GRAPH_NAME)
    yield c
    _drop_registry_tables(c)
    _drop_graph_if_exists(c, GRAPH_NAME)
    c.close()


@pytest.fixture()
def seeded_graph(conn):
    """Pushes tests/fixtures/extraction.json -- the same fixture the
    falkordb suite builds from -- into a fresh AGE graph, and returns the
    built nx.Graph alongside it so tests can compute expectations (e.g.
    which nodes are actually god nodes) rather than hardcoding them."""
    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    return G


def _cypher(graph_name: str, body: str, returns: str) -> sql.Composed:
    return sql.SQL("SELECT * FROM cypher({graph}, $${body}$$) AS {returns};").format(
        graph=sql.Literal(graph_name), body=sql.SQL(body), returns=sql.SQL(returns)
    )


def _agtype_str(raw) -> str:
    """AGE returns agtype scalars as their JSON text form (quoted for
    strings) -- strip the quotes to compare against a plain Python str."""
    return json.loads(raw) if isinstance(raw, str) else raw


def _parse_agtype_objects(raw: str) -> list[tuple[dict, str | None]]:
    """docs/AGE_SCHEMA.md's pinned parser: a returned vertex/edge/path is
    not plain JSON -- each top-level object carries a `::vertex`/`::edge`
    type suffix that breaks json.loads and a naive regex alike (the
    nested "properties" object has its own braces). Depth-aware splitting
    handles it; kept identical to the doc's copy so drift is caught here."""
    results: list[tuple[dict, str | None]] = []
    depth, start = 0, None
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj = json.loads(raw[start:i + 1])
                j = i + 1
                kind = None
                if raw[j:j + 2] == "::":
                    k = j + 2
                    while k < n and raw[k].isalpha():
                        k += 1
                    kind = raw[j + 2:k]
                results.append((obj, kind))
                start = None
        i += 1
    return results


# ---------------------------------------------------------------------------
# Review agent: shortest path, reverse-dependency traversal.
# ---------------------------------------------------------------------------

def test_pinned_shortest_path_query(conn, seeded_graph):
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute(
            _cypher(
                GRAPH_NAME,
                "MATCH p = (a {label: 'Transformer'})-[*..6]-(b {label: 'LayerNorm'}) "
                "RETURN p "
                "ORDER BY length(p) ASC "
                "LIMIT 1",
                "(p agtype)",
            )
        )
        row = cur.fetchone()
    assert row is not None
    elements = _parse_agtype_objects(row[0])
    node_ids = [obj["properties"]["id"] for obj, kind in elements if kind == "vertex"]
    assert node_ids == ["n_transformer", "n_layernorm"]


def test_pinned_reverse_dependency_traversal_query(conn, seeded_graph):
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute(
            _cypher(
                GRAPH_NAME,
                "MATCH (caller)-[r:CONTAINS]->(target {id: 'n_attention'}) "
                "RETURN caller.id, caller.source_file, r.confidence",
                "(caller_id agtype, source_file agtype, confidence agtype)",
            )
        )
        rows = cur.fetchall()
    callers = {_agtype_str(r[0]) for r in rows}
    assert callers == {"n_transformer"}


# ---------------------------------------------------------------------------
# Review agent: branch-diff seed selection (plain SQL, no Cypher).
# ---------------------------------------------------------------------------

def test_pinned_branch_diff_seed_selection_query(conn):
    remote = f"https://github.com/testowner/agent-query-{uuid.uuid4().hex[:8]}.git"
    row = reg.register_repository(_conninfo(), remote, default_branch="main")
    repository_id = row["repository_id"]

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO graphify_branches (repository_id, branch, base_commit_sha, head_commit_sha) "
            "VALUES (%s, %s, %s, %s);",
            (repository_id, "feature", "base1", "head1"),
        )
        cur.execute(
            "INSERT INTO graphify_branch_revisions "
            "(repository_id, branch, generation, base_commit_sha, head_commit_sha, active) "
            "VALUES (%s, %s, 1, %s, %s, true);",
            (repository_id, "feature", "base1", "head1"),
        )
        for seq, kind, payload in [
            (1, "node_add", {"id": "n_new", "label": "New", "properties": {"label": "New"}}),
            (2, "node_del", {"id": "n_old", "label": "Old", "properties": {"label": "Old"}}),
            (3, "node_change", {"id": "n_changed", "old": {"community": 1}, "new": {"community": 2}}),
        ]:
            cur.execute(
                "INSERT INTO graphify_branch_diff "
                "(repository_id, branch, generation, seq, from_commit_sha, to_commit_sha, kind, payload) "
                "VALUES (%s, %s, 1, %s, %s, %s, %s, %s);",
                (repository_id, "feature", seq, "base1", "head1", kind, json.dumps(payload)),
            )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT kind, payload->>'id' AS node_id "
            "FROM graphify_branch_diff "
            "WHERE repository_id = %(repository_id)s "
            "AND branch = %(branch)s "
            "AND generation = %(generation)s "
            "ORDER BY seq;",
            {"repository_id": repository_id, "branch": "feature", "generation": 1},
        )
        rows = cur.fetchall()
    assert rows == [
        ("node_add", "n_new"),
        ("node_del", "n_old"),
        ("node_change", "n_changed"),
    ]


# ---------------------------------------------------------------------------
# Review agent: depth-capped, limited, timed-out traversal against a graph
# large enough for the cap/limit/timeout to matter (docs/AGE_PLAN.md
# Phase 5: "grow a dedicated larger fixture rather than weakening
# assertions").
# ---------------------------------------------------------------------------

@pytest.fixture()
def fan_out_graph(conn):
    """A hub node with 200 direct callers -- big enough that LIMIT and a
    hop-count cap both have real, observable effects, unlike the 4-node
    extraction.json fixture."""
    import networkx as nx

    G = nx.Graph()
    G.add_node("hub", label="Hub", file_type="code", source_file="hub.py")
    for i in range(200):
        node_id = f"caller_{i:03d}"
        G.add_node(node_id, label=f"Caller{i}", file_type="code", source_file=f"caller_{i}.py")
        # _src/_tgt: real graphify graphs always carry these (build.py
        # stamps them on every edge, since an undirected nx.Graph's own
        # tuple order depends on node insertion order, not extracted
        # direction) - set them explicitly here so this synthetic graph
        # behaves like a real one for push_to_age()'s direction handling.
        G.add_edge(node_id, "hub", relation="calls", confidence="EXTRACTED",
                   _src=node_id, _tgt="hub")
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    return G


def test_pinned_depth_capped_limited_timed_out_traversal(conn, fan_out_graph):
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SET statement_timeout = '5s';")
        cur.execute(
            _cypher(
                GRAPH_NAME,
                "MATCH (caller)-[:CALLS*1..3]->(target {id: 'hub'}) "
                "RETURN caller.id, caller.source_file "
                "LIMIT 50",
                "(caller_id agtype, source_file agtype)",
            )
        )
        rows = cur.fetchall()
    # 200 real callers exist; LIMIT 50 must actually cap the result set.
    assert len(rows) == 50


def test_statement_timeout_actually_cancels_a_runaway_query(conn, fan_out_graph):
    """Proves the pinned statement_timeout guidance isn't decorative: an
    absurdly low timeout against a real (if modest) traversal must raise
    QueryCanceled, not silently ignore the setting."""
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SET statement_timeout = '1ms';")
        with pytest.raises(psycopg.errors.QueryCanceled):
            cur.execute(
                _cypher(
                    GRAPH_NAME,
                    "MATCH (caller)-[:CALLS*1..3]->(target {id: 'hub'}) "
                    "RETURN caller.id, caller.source_file",
                    "(caller_id agtype, source_file agtype)",
                )
            )
    conn.rollback()


# ---------------------------------------------------------------------------
# Quality agent: structural properties joined with graphify_quality_findings.
# ---------------------------------------------------------------------------

def test_pinned_quality_findings_join_query(conn, seeded_graph):
    remote = f"https://github.com/testowner/agent-query-{uuid.uuid4().hex[:8]}.git"
    row = reg.register_repository(_conninfo(), remote, default_branch="main")
    repository_id = row["repository_id"]
    commit_sha = "c1"

    god_ids = {n["id"] for n in god_nodes(seeded_graph, top_n=seeded_graph.number_of_nodes())}
    assert god_ids, "fixture must produce at least one god node for this test to mean anything"
    target_id = sorted(god_ids)[0]

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO graphify_quality_findings "
            "(repository_id, commit_sha, node_id, rule, severity) "
            "VALUES (%s, %s, %s, %s, %s);",
            (repository_id, commit_sha, target_id, "god_node_review", "warning"),
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute(
            sql.SQL(
                "SELECT n.id, n.source_file, n.degree, f.rule, f.severity "
                "FROM cypher({graph}, $$ "
                "  MATCH (n) WHERE n.is_god_node = true "
                "  RETURN n.id, n.source_file, n.degree "
                "$$) AS n(id agtype, source_file agtype, degree agtype) "
                "LEFT JOIN graphify_quality_findings f "
                "  ON f.node_id = trim(both '\"' from n.id::text) "
                "  AND f.repository_id = {repository_id} "
                "  AND f.commit_sha = {commit_sha};"
            ).format(
                graph=sql.Literal(GRAPH_NAME),
                repository_id=sql.Literal(repository_id),
                commit_sha=sql.Literal(commit_sha),
            )
        )
        rows = cur.fetchall()

    by_id = {_agtype_str(r[0]): r for r in rows}
    assert target_id in by_id
    matched_row = by_id[target_id]
    assert matched_row[3] == "god_node_review"  # rule
    assert matched_row[4] == "warning"  # severity
