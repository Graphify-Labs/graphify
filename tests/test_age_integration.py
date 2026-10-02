"""Integration test / compatibility spike for Apache AGE (docs/AGE_PLAN.md Phase 0).

Runs for real against a pinned `apache/age` image (PostgreSQL 18.1, AGE
1.7.0, resolved during the Phase 0 spike):

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_integration.py -q

Pinned by digest, not a floating tag (see docs/AGE_PLAN.md, "Testing
strategy"), so results don't drift with upstream AGE/Postgres releases;
bump it as a deliberate decision, not incidentally.

The test auto-skips when the `psycopg` driver is not installed or no AGE
instance is reachable, so it is a no-op in the default CI (which provisions
no external services) and mirrors tests/test_falkordb_integration.py's
pattern exactly: importorskip + a service-identifying connection probe
(``LOAD 'age'``) rather than a bare port/ping check, so a plain Postgres
without the AGE extension fails closed into a skip instead of a confusing
test failure.

Host/port/db/user/password are overridable via AGE_HOST / AGE_PORT /
AGE_DB / AGE_USER / AGE_PASSWORD, matching the FALKORDB_HOST/FALKORDB_PORT
naming convention used by the FalkorDB suite.

These tests double as the Phase 0 compatibility spike: they pin down the
exact psycopg3 + AGE interaction patterns that graphify/exporters/graphdb.py's
push_to_age() (Phase 1) is built on. Mocked unit tests elsewhere cover CLI
wiring and sanitization only -- none of this file's behavior (agtype
encoding, prepared-statement semantics, transaction isolation, AGE
label-table internals) can be validated with mocks.

SPIKE FINDING (load-bearing for Phase 1's design): the graph name argument
to cypher() must be a literal at parse time -- AGE's custom parser hook
resolves it before normal bind-parameter substitution runs, so
``cypher($1, ...)`` fails with ``psycopg.errors.SyntaxError: a name
constant is expected``. The graph name can never be passed as a bound
parameter; it must be embedded as a validated SQL literal (via
psycopg.sql.Literal here, mirroring how push_to_age() must build its
statements from a sanitized name, never from raw user/branch input).
Cypher *data* values (property maps, agtype parameter maps passed via
PREPARE/EXECUTE) are still parameterized at the *cypher()* level, in the
sense that they never appear as raw text inside the dollar-quoted Cypher
body. But a second, psycopg-specific finding applies to how that agtype
payload reaches ``EXECUTE`` itself: ``EXECUTE stmt_name(%s)`` with the
payload as a normal bind parameter fails with
``psycopg.errors.IndeterminateDatatype: could not determine data type of
parameter $1`` -- EXECUTE's argument list isn't part of the extended query
protocol's normal parameterizable surface, and no explicit ``::agtype``
cast on the placeholder fixes it. The payload must instead be embedded via
``psycopg.sql.Literal`` (safe, properly escaped) -- fine here because it is
graphify-generated JSON, not raw external input. See ``_execute_prepared``
below.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
HOST = os.environ.get("AGE_HOST", "localhost")
PORT = int(os.environ.get("AGE_PORT", "5432"))
DBNAME = os.environ.get("AGE_DB", "postgres")
USER = os.environ.get("AGE_USER", "postgres")
PASSWORD = os.environ.get("AGE_PASSWORD", "graphify_test")
GRAPH_NAME = "graphify_spike"


def _conninfo() -> str:
    return f"host={HOST} port={PORT} dbname={DBNAME} user={USER} password={PASSWORD}"


def _cypher(graph_name: str, body: str, returns: str = "(result agtype)") -> sql.Composed:
    """Build a cypher() call with the graph name embedded as a literal.

    See the SPIKE FINDING in the module docstring: the graph name cannot be
    a bind parameter. sql.Literal renders it as a properly quoted/escaped
    SQL string literal, not string-interpolated raw text.
    """
    return sql.SQL("SELECT * FROM cypher({graph}, $${body}$$) AS {returns};").format(
        graph=sql.Literal(graph_name),
        body=sql.SQL(body),
        returns=sql.SQL(returns),
    )


def _execute_prepared(cur, stmt_name: str, payload: dict) -> None:
    """EXECUTE a prepared cypher() statement with an agtype payload.

    See the module docstring's second SPIKE FINDING: the payload cannot be
    a normal psycopg bind parameter here (IndeterminateDatatype). It is
    embedded as an escaped SQL literal instead.
    """
    stmt = sql.SQL("EXECUTE {name}({payload});").format(
        name=sql.Identifier(stmt_name), payload=sql.Literal(json.dumps(payload))
    )
    cur.execute(stmt)


def _connect():
    """Return a psycopg connection with AGE loaded, or skip.

    A bare TCP connect only proves *some* Postgres answers on the port --
    it says nothing about whether the AGE extension is installed. ``LOAD
    'age'`` is the service-identifying probe: it is a no-op if AGE is
    already loaded and fails cleanly if the extension isn't present.
    """
    try:
        conn = psycopg.connect(_conninfo(), connect_timeout=5)
    except Exception as e:  # pragma: no cover - depends on local environment
        pytest.skip(f"no server reachable at {HOST}:{PORT} ({e})")
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
        conn.commit()
    except Exception as e:  # pragma: no cover - depends on local environment
        conn.close()
        pytest.skip(f"server at {HOST}:{PORT} does not have the AGE extension ({e})")
    return conn


def _drop_graph_if_exists(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s", (GRAPH_NAME,)
        )
        if cur.fetchone()[0]:
            cur.execute("SELECT drop_graph(%s, true);", (GRAPH_NAME,))
    conn.commit()


@pytest.fixture()
def conn():
    c = _connect()
    _drop_graph_if_exists(c)
    yield c
    _drop_graph_if_exists(c)
    c.close()


# ---------------------------------------------------------------------------
# Spike 1: graph lifecycle, cypher() round trip
# ---------------------------------------------------------------------------

def test_create_graph_and_basic_cypher(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
        cur.execute(_cypher(GRAPH_NAME, "CREATE (n:Entity {id: 'a'}) RETURN n", "(n agtype)"))
        assert cur.fetchone() is not None
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (count,) = cur.fetchone()
        assert int(count) == 1


# ---------------------------------------------------------------------------
# Spike 2: agtype parameter maps via explicit PREPARE/EXECUTE.
#
# AGE documents cypher() parameters as usable only through prepared
# statements -- the query text is a dollar-quoted literal fixed at prepare
# time, so only the agtype parameter map (the third argument) is bindable.
# Prepared statements are session-scoped: prepare once per pooled
# connection, not once per call.
# ---------------------------------------------------------------------------

def test_prepared_statement_agtype_params(conn):
    """SPIKE FINDING: ``SET n += $props`` / ``SET n = $props`` reject a map
    that arrives via a parameter or via UNWIND-bound data --
    ``psycopg.errors.FeatureNotSupported: SET clause expects a map`` --
    even though dot-path access into the same parameter (``$props.label``)
    works fine. Only a literal map written directly in the query text
    satisfies SET's map-mode. The workaround (validated below and in
    ``test_unwind_batch_merge``) is explicit per-field ``SET n.field =
    row.field`` assignments -- which fits push_to_age()'s design anyway,
    since the pushed property set is a fixed, enumerable schema (see
    docs/AGE_SCHEMA.md), not arbitrary user-supplied keys.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
        prepare_stmt = sql.SQL(
            "PREPARE graphify_upsert_node(agtype) AS "
            "SELECT * FROM cypher({graph}, $$ "
            "  MERGE (n:Entity {{id: $id}}) "
            "  SET n.id = $id, n.label = $label "
            "  RETURN n "
            "$$, $1) AS (n agtype);"
        ).format(graph=sql.Literal(GRAPH_NAME))
        cur.execute(prepare_stmt)
        _execute_prepared(cur, "graphify_upsert_node", {"id": "x1", "label": "Foo"})
        assert cur.fetchone() is not None
        cur.execute("DEALLOCATE graphify_upsert_node;")
    conn.commit()


# ---------------------------------------------------------------------------
# Spike 3: UNWIND $rows + MERGE batch writes and batch sizing.
# ---------------------------------------------------------------------------

def test_unwind_batch_merge(conn):
    """Batch write pattern push_to_age() will actually use: UNWIND $rows +
    MERGE by id + explicit per-field SET (see the SPIKE FINDING in
    test_prepared_statement_agtype_params -- ``SET n += row.props`` fails
    here for the same reason).
    """
    rows = [{"id": f"n{i}", "label": f"Node {i}"} for i in range(50)]
    prepare_stmt = sql.SQL(
        "PREPARE graphify_batch_upsert(agtype) AS "
        "SELECT * FROM cypher({graph}, $$ "
        "  UNWIND $rows AS row "
        "  MERGE (n:Entity {{id: row.id}}) "
        "  SET n.id = row.id, n.label = row.label "
        "$$, $1) AS (result agtype);"
    ).format(graph=sql.Literal(GRAPH_NAME))

    with conn.cursor() as cur:
        cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
        cur.execute(prepare_stmt)
        _execute_prepared(cur, "graphify_batch_upsert", {"rows": rows})
        cur.execute("DEALLOCATE graphify_batch_upsert;")
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (count,) = cur.fetchone()
        assert int(count) == len(rows)
    conn.commit()

    # Idempotency: re-running the same UNWIND/MERGE batch must not grow counts.
    with conn.cursor() as cur:
        cur.execute(prepare_stmt.as_string(conn).replace(
            "graphify_batch_upsert", "graphify_batch_upsert2"
        ))
        _execute_prepared(cur, "graphify_batch_upsert2", {"rows": rows})
        cur.execute("DEALLOCATE graphify_batch_upsert2;")
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (count,) = cur.fetchone()
        assert int(count) == len(rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Spike 4: transactional write behavior -- a failure mid-batch must roll
# back the whole write, leaving the prior graph state intact (this is the
# guarantee push_to_age()'s deletion-safe reconcile depends on).
# ---------------------------------------------------------------------------

def test_transaction_rolls_back_on_failure(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
        cur.execute(_cypher(GRAPH_NAME, "CREATE (n:Entity {id: 'keep'})", "(r agtype)"))
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "CREATE (n:Entity {id: 'partial'})", "(r agtype)"))
        with pytest.raises(Exception):
            # Deliberately malformed Cypher to force a mid-transaction error.
            cur.execute(_cypher(GRAPH_NAME, "CREAT BROKEN SYNTAX", "(r agtype)"))
        conn.rollback()

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (count,) = cur.fetchone()
        # The 'partial' node from the rolled-back transaction must not
        # survive; only the previously committed 'keep' node remains.
        assert int(count) == 1


# ---------------------------------------------------------------------------
# Spike 5: index options on AGE label tables that don't touch AGE internals.
# AGE exposes each label as a real Postgres table under the graph's schema;
# a GIN index on the agtype properties column is supported without reaching
# into AGE-internal catalogs.
# ---------------------------------------------------------------------------

def test_index_on_label_table(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT create_graph(%s);", (GRAPH_NAME,))
        cur.execute(_cypher(GRAPH_NAME, "CREATE (n:Entity {id: 'idx1'})", "(r agtype)"))
        index_stmt = sql.SQL(
            "CREATE INDEX IF NOT EXISTS graphify_spike_entity_props_idx "
            "ON {schema}.{table} USING gin (properties);"
        ).format(schema=sql.Identifier(GRAPH_NAME), table=sql.Identifier("Entity"))
        cur.execute(index_stmt)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n:Entity {id: 'idx1'}) RETURN n", "(n agtype)"))
        assert cur.fetchone() is not None


def test_push_to_age_creates_expected_graph(conn):
    """End-to-end: build a NetworkX graph from the shared test fixture and
    push it with push_to_age(), then verify node/edge counts via cypher().

    Exercises the real Phase 1 exporter, not just raw psycopg -- this is
    the test that will need updating once push_to_age() lands.
    """
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")
    from graphify.build import build_from_json

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    G = build_from_json(extraction)

    result = push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)

    assert result["nodes"] == G.number_of_nodes()
    assert result["edges"] == G.number_of_edges()

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (node_count,) = cur.fetchone()
        cur.execute(_cypher(GRAPH_NAME, "MATCH ()-[r]->() RETURN count(r)", "(c agtype)"))
        (edge_count,) = cur.fetchone()

    assert int(node_count) == G.number_of_nodes()
    assert int(edge_count) == G.number_of_edges()


def test_push_to_age_creates_property_indexes(conn):
    """push_to_age() must index every vertex label's ``properties`` -- a GIN
    index (for the ``@>`` matches it emits itself) plus a btree expression
    index per agent-filtered property (``id``, ``source_file``). Without
    these a push is O(nodes x edges) and agent ``WHERE n.id = ...`` queries
    seq-scan. See docs/AGE_PLAN.md dogfooding pass + docs/AGE_SCHEMA.md.
    """
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")
    from graphify.build import build_from_json

    G = build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ag_catalog.ag_label l "
            "JOIN ag_catalog.ag_graph g ON g.graphid = l.graph "
            "WHERE g.name = %s AND l.kind = 'v' "
            "AND l.name <> '_ag_label_vertex';",  # AGE's base label, never written
            (GRAPH_NAME,),
        )
        (vlabel_count,) = cur.fetchone()
        cur.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = %s;", (GRAPH_NAME,)
        )
        defs = [d for (d,) in cur.fetchall()]

    gin = [d for d in defs if "USING gin (properties)" in d]
    id_btree = [d for d in defs if '"id"' in d and "USING btree" in d and "agtype_access_operator" in d]
    sf_btree = [d for d in defs if '"source_file"' in d and "USING btree" in d]
    assert len(gin) == vlabel_count, f"expected one GIN index per vertex label:\n{defs}"
    assert len(id_btree) == vlabel_count, f"expected one id btree per vertex label:\n{defs}"
    assert len(sf_btree) == vlabel_count, f"expected one source_file btree per vertex label:\n{defs}"


# ---------------------------------------------------------------------------
# push_to_age() reconcile matrix (docs/AGE_PLAN.md Phase 1 checklist):
# fresh push, idempotent re-push, node/edge deletion, property change,
# label change, lean vs. full-props. Uses small hand-built graphs so each
# case is exact and independent of the shared fixture's shape.
# ---------------------------------------------------------------------------

def _build_graph(nodes: list[tuple], edges: list[tuple]):
    import networkx as nx

    G = nx.DiGraph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    return G


def _counts(conn):
    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n) RETURN count(n)", "(c agtype)"))
        (n,) = cur.fetchone()
        cur.execute(_cypher(GRAPH_NAME, "MATCH ()-[r]->() RETURN count(r)", "(c agtype)"))
        (e,) = cur.fetchone()
    return int(n), int(e)


def test_push_to_age_is_idempotent(conn):
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G = _build_graph(
        [("a", {"file_type": "code", "label": "A"}), ("b", {"file_type": "code", "label": "B"})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})],
    )
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    assert _counts(conn) == (2, 1)


def test_push_to_age_reconciles_deletions(conn):
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G1 = _build_graph(
        [
            ("a", {"file_type": "code", "label": "A"}),
            ("b", {"file_type": "code", "label": "B"}),
            ("c", {"file_type": "code", "label": "C"}),
        ],
        [
            ("a", "b", {"relation": "calls", "confidence": "EXTRACTED"}),
            ("b", "c", {"relation": "calls", "confidence": "EXTRACTED"}),
        ],
    )
    push_to_age(G1, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    assert _counts(conn) == (3, 2)

    # Node 'c' (and its incident edge) removed; edge a->b removed too.
    G2 = _build_graph(
        [
            ("a", {"file_type": "code", "label": "A"}),
            ("b", {"file_type": "code", "label": "B"}),
        ],
        [],
    )
    push_to_age(G2, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    assert _counts(conn) == (2, 0)


def test_push_to_age_property_change_updates_in_place(conn):
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G1 = _build_graph([("a", {"file_type": "code", "label": "Old"})], [])
    push_to_age(G1, conninfo=_conninfo(), graph_name=GRAPH_NAME)

    G2 = _build_graph([("a", {"file_type": "code", "label": "New"})], [])
    push_to_age(G2, conninfo=_conninfo(), graph_name=GRAPH_NAME)

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n {id: 'a'}) RETURN n.label", "(l agtype)"))
        (label,) = cur.fetchone()
    assert json.loads(label) == "New"
    assert _counts(conn) == (1, 0)


def test_push_to_age_label_change_removes_old_label(conn):
    """A node whose file_type changes must not survive under two labels
    (docs/AGE_PLAN.md Phase 1: 'delete it under the old label')."""
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G1 = _build_graph([("a", {"file_type": "code", "label": "A"})], [])
    push_to_age(G1, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n:Code) RETURN count(n)", "(c agtype)"))
        assert int(cur.fetchone()[0]) == 1

    G2 = _build_graph([("a", {"file_type": "document", "label": "A"})], [])
    push_to_age(G2, conninfo=_conninfo(), graph_name=GRAPH_NAME)

    with conn.cursor() as cur:
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n:Code) RETURN count(n)", "(c agtype)"))
        assert int(cur.fetchone()[0]) == 0
        cur.execute(_cypher(GRAPH_NAME, "MATCH (n:Document) RETURN count(n)", "(c agtype)"))
        assert int(cur.fetchone()[0]) == 1
    assert _counts(conn) == (1, 0)


def test_push_to_age_rolls_back_whole_push_on_failure(conn, monkeypatch):
    """A failure before push_to_age() opens its write transaction must
    leave the graph exactly as it was, with no partial write reaching the
    database at all. This complements (not replaces)
    test_transaction_rolls_back_on_failure above, which validates AGE's
    own mid-transaction ROLLBACK behavior directly; push_to_age() runs its
    entire write phase in one transaction, so a DB-level failure partway
    through gets the same guarantee from Postgres itself."""
    try:
        from graphify.exporters import graphdb
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G1 = _build_graph([("a", {"file_type": "code", "label": "A"})], [])
    graphdb.push_to_age(G1, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    assert _counts(conn) == (1, 0)

    G2 = _build_graph(
        [("a", {"file_type": "code", "label": "A"}), ("b", {"file_type": "code", "label": "B"})],
        [("a", "b", {"relation": "calls", "confidence": "EXTRACTED"})],
    )

    real_edge_rows = graphdb._age_edge_rows

    def _boom(*args, **kwargs):
        raise RuntimeError("injected failure before edge upsert")

    monkeypatch.setattr(graphdb, "_age_edge_rows", _boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        graphdb.push_to_age(G2, conninfo=_conninfo(), graph_name=GRAPH_NAME)
    monkeypatch.setattr(graphdb, "_age_edge_rows", real_edge_rows)

    # Nothing from G2's push (including node 'b') must have landed, and the
    # prior committed state (node 'a' only) must be intact.
    assert _counts(conn) == (1, 0)


def test_push_to_age_full_props_includes_extra_scalar_fields(conn):
    try:
        from graphify.exporters.graphdb import push_to_age
    except ImportError:
        pytest.skip("push_to_age() not implemented yet (Phase 1)")

    G = _build_graph(
        [("a", {"file_type": "code", "label": "A", "custom_score": 0.75})], []
    )
    push_to_age(G, conninfo=_conninfo(), graph_name=GRAPH_NAME, full_props=True)

    with conn.cursor() as cur:
        cur.execute(
            _cypher(GRAPH_NAME, "MATCH (n {id: 'a'}) RETURN n.custom_score", "(s agtype)")
        )
        (score,) = cur.fetchone()
    assert json.loads(score) == 0.75
