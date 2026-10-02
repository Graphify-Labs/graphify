"""Tier-3 integration tests for graphify.age_branches (docs/AGE_PLAN.md
Phase 4): initial/incremental/rebase branch pushes, lazy materialization,
reaping, and advisory-lock concurrency. Requires a live PostgreSQL with
the AGE extension (materialize_branch/reap_branch touch real AGE graphs).

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_branches_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching the other AGE live-suite files' convention.
"""
from __future__ import annotations

import os
import subprocess
import uuid

import networkx as nx
import pytest

psycopg = pytest.importorskip("psycopg")

from graphify import age_branches as ab  # noqa: E402
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


def _drop_all_age_graphs(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SELECT name FROM ag_catalog.ag_graph;")
        names = [r[0] for r in cur.fetchall()]
        for name in names:
            cur.execute("SELECT drop_graph(%s, true);", (name,))
    conn.commit()


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    _drop_registry_tables(c)
    _drop_all_age_graphs(c)
    yield c
    _drop_registry_tables(c)
    _drop_all_age_graphs(c)
    c.close()


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def _commit_all(cwd, message="commit"):
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _graph(nodes, edges):
    G = nx.Graph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    for src, tgt, attrs in edges:
        G.add_edge(src, tgt, **attrs)
    return G


@pytest.fixture()
def repository_id(conn) -> str:
    remote = f"https://github.com/testowner/branch-e2e-{uuid.uuid4().hex[:8]}.git"
    row = reg.register_repository(_conninfo(), remote, default_branch="main")
    return row["repository_id"]


def _push_kwargs():
    return dict(graphify_version="0.9.54", schema_version=reg.SCHEMA_VERSION)


def test_push_branch_initial_records_diff_against_default_branch(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    main_sha = _commit_all(cwd, "main initial")

    G_main = _graph([("a", {"label": "A", "file_type": "code"})], [])
    snap.record_snapshot(_conninfo(), repository_id, main_sha, G_main, **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("def bar():\n    return 2\n")
    branch_sha = _commit_all(cwd, "feature work")
    G_branch = _graph(
        [("a", {"label": "A", "file_type": "code"}), ("b", {"label": "B", "file_type": "code"})], []
    )

    result = ab.push_branch(
        _conninfo(), repository_id, "feature", G_branch,
        cwd=cwd, default_branch="main", **_push_kwargs(),
    )
    assert result["kind"] == "initial"
    assert result["base_commit_sha"] == main_sha
    assert result["head_commit_sha"] == branch_sha
    assert result["rows"] == 1  # one new node

    with conn.cursor() as cur:
        cur.execute(
            "SELECT materialized, base_commit_sha, head_commit_sha FROM graphify_branches "
            "WHERE repository_id = %s AND branch = %s;",
            (repository_id, "feature"),
        )
        materialized, base_commit_sha, head_commit_sha = cur.fetchone()
    assert materialized is False
    assert base_commit_sha == main_sha
    assert head_commit_sha == branch_sha


def test_push_branch_falls_back_to_worktree_extraction_for_unrecorded_base(conn, repository_id, tmp_path):
    """No graphify_snapshots row was ever recorded for main -- push_branch
    must fall back to a git-worktree extraction at the merge-base commit
    rather than failing (docs/AGE_PLAN.md Phase 4's missing-base-snapshot
    fallback chain)."""
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    return bar()\n\ndef bar():\n    return 1\n")
    main_sha = _commit_all(cwd, "main initial")
    # Deliberately skip snap.record_snapshot() here.

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("def baz():\n    return 2\n")
    branch_sha = _commit_all(cwd, "feature work")

    G_branch = _graph(
        [("a", {"label": "A", "file_type": "code"}), ("b", {"label": "B", "file_type": "code"})], []
    )
    result = ab.push_branch(
        _conninfo(), repository_id, "feature", G_branch,
        cwd=cwd, default_branch="main", **_push_kwargs(),
    )
    assert result["base_commit_sha"] == main_sha
    assert result["head_commit_sha"] == branch_sha

    with conn.cursor() as cur:
        cur.execute(
            "SELECT commit_sha, kind FROM graphify_snapshots WHERE repository_id = %s;",
            (repository_id,),
        )
        rows = cur.fetchall()
    assert (main_sha, "checkpoint") in rows


def test_push_branch_second_push_appends_to_same_generation(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main initial")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    sha1 = _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"})], [])
    r1 = ab.push_branch(_conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main", **_push_kwargs())
    assert r1["generation"] == 1

    (tmp_path / "c.py").write_text("z = 1\n")
    sha2 = _commit_all(cwd, "feature 2")
    G2 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})], [])
    r2 = ab.push_branch(_conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main", **_push_kwargs())
    assert r2["kind"] == "incremental"
    assert r2["generation"] == 1  # same generation, no rebase

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM graphify_branch_revisions WHERE repository_id=%s AND branch=%s;",
            (repository_id, "feature"),
        )
        (gen_count,) = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM graphify_branch_diff WHERE repository_id=%s AND branch=%s;",
            (repository_id, "feature"),
        )
        (diff_row_count,) = cur.fetchone()
    assert gen_count == 1
    assert diff_row_count == 2  # 1 new node from first push + 1 from second
    assert sha1 and sha2


def test_push_branch_noop_when_head_unchanged(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())
    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature")
    G = _graph([("a", {"label": "A"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G, cwd=cwd, default_branch="main", **_push_kwargs())
    result = ab.push_branch(_conninfo(), repository_id, "feature", G, cwd=cwd, default_branch="main", **_push_kwargs())
    assert result["kind"] == "noop"
    assert result["rows"] == 0


def test_push_branch_detects_rebase_and_starts_new_generation(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"})], [])
    r1 = ab.push_branch(_conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main", **_push_kwargs())
    assert r1["generation"] == 1

    # Amend to rewrite history -- old head is no longer an ancestor.
    (tmp_path / "b.py").write_text("y = 2\n")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "--amend", "-m", "feature 1 amended")

    G2 = _graph([("a", {"label": "A"}), ("c", {"label": "C"})], [])
    r2 = ab.push_branch(_conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main", **_push_kwargs())
    assert r2["kind"] == "rebased"
    assert r2["generation"] == 2

    with conn.cursor() as cur:
        cur.execute(
            "SELECT generation, active FROM graphify_branch_revisions "
            "WHERE repository_id = %s AND branch = %s ORDER BY generation;",
            (repository_id, "feature"),
        )
        rows = cur.fetchall()
    assert rows == [(1, False), (2, True)]


def test_push_branch_rejects_incompatible_schema_version(conn, repository_id, tmp_path):
    """Regression (found via review): nothing used to reject continuing a
    branch's diff chain under a different schema_version than the one it
    was originally pushed with, risking an incompatible checkpoint/delta
    getting spliced into one replay."""
    cwd = _repo(tmp_path)
    (tmp_path / "readme.txt").write_text("main\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "a.py").write_text("x = 1\n")
    _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main", **_push_kwargs())

    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature 2")
    G2 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})], [])
    with pytest.raises(ValueError, match="schema_version"):
        ab.push_branch(
            _conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main",
            graphify_version="0.9.54", schema_version="not-" + reg.SCHEMA_VERSION,
        )


def test_push_branch_rejects_incompatible_extraction_config_hash(conn, repository_id, tmp_path):
    """Regression (found via review): extraction_config_hash needed the
    same continuation-rejection schema_version already got -- a push
    continuing a branch's diff chain under a different extraction
    configuration (same schema_version) must not be silently spliced in."""
    cwd = _repo(tmp_path)
    (tmp_path / "readme.txt").write_text("main\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "a.py").write_text("x = 1\n")
    _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"})], [])
    ab.push_branch(
        _conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main",
        graphify_version="0.9.54", schema_version=reg.SCHEMA_VERSION,
        extraction_config_hash="config-a",
    )

    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature 2")
    G2 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})], [])
    with pytest.raises(ValueError, match="extraction_config_hash"):
        ab.push_branch(
            _conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main",
            graphify_version="0.9.54", schema_version=reg.SCHEMA_VERSION,
            extraction_config_hash="config-b",
        )


def test_rebase_drop_and_registry_transition_are_one_transaction(conn, repository_id, tmp_path):
    """Regression (found via review): the old-graph drop_graph() call used
    to commit in its own transaction, separately from the generation
    transition that clears materialized/age_graph_name -- if anything
    failed in between, the registry could still say materialized=true for
    an AGE graph that no longer existed. Verify the materialized graph
    from generation 1 is actually gone, and the registry consistently
    reflects generation 2, not-yet-materialized."""
    cwd = _repo(tmp_path)
    (tmp_path / "readme.txt").write_text("main\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "a.py").write_text("x = 1\n")
    _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main", **_push_kwargs())
    mat1 = ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_rebase_e2e")
    old_graph_name = mat1["age_graph_name"]

    (tmp_path / "a.py").write_text("x = 2\n")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "--amend", "-m", "feature 1 amended")
    G2 = _graph([("a", {"label": "A"}), ("c", {"label": "C"})], [])
    r2 = ab.push_branch(_conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main", **_push_kwargs())
    assert r2["kind"] == "rebased"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT materialized, age_graph_name FROM graphify_branches "
            "WHERE repository_id = %s AND branch = %s;",
            (repository_id, "feature"),
        )
        materialized, age_graph_name = cur.fetchone()
    assert materialized is False
    assert age_graph_name is None

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (old_graph_name,))
        assert cur.fetchone()[0] == 0


def test_materialize_branch_creates_age_graph_with_correct_content(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha,
                          _graph([("a", {"label": "A", "file_type": "code"})], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature")
    G = _graph(
        [("a", {"label": "A", "file_type": "code"}), ("b", {"label": "B", "file_type": "code"})],
        [("a", "b", {"relation": "uses", "confidence": "EXTRACTED"})],
    )
    ab.push_branch(_conninfo(), repository_id, "feature", G, cwd=cwd, default_branch="main", **_push_kwargs())

    result = ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")
    assert result["already_materialized"] is False
    graph_name = result["age_graph_name"]
    assert graph_name == "graphify_e2e__feature"

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        from psycopg import sql
        cur.execute(
            sql.SQL("SELECT * FROM cypher({g}, $$ MATCH (n) RETURN n.id $$) AS (id agtype);")
            .format(g=sql.Literal(graph_name))
        )
        ids = sorted(str(r[0]).strip('"') for r in cur.fetchall())
    assert ids == ["a", "b"]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT materialized, age_graph_name FROM graphify_branches "
            "WHERE repository_id = %s AND branch = %s;", (repository_id, "feature"),
        )
        materialized, stored_name = cur.fetchone()
    assert materialized is True
    assert stored_name == graph_name


def test_materialize_branch_is_idempotent(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())
    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature")
    G = _graph([("a", {"label": "A"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G, cwd=cwd, default_branch="main", **_push_kwargs())

    r1 = ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")
    r2 = ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")
    assert r1["already_materialized"] is False
    assert r2["already_materialized"] is True
    assert r1["age_graph_name"] == r2["age_graph_name"]


def test_push_branch_applies_incremental_diff_to_materialized_graph(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature 1")
    G1 = _graph([("a", {"label": "A"}), ("b", {"label": "B"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G1, cwd=cwd, default_branch="main", **_push_kwargs())
    ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")

    (tmp_path / "c.py").write_text("z = 1\n")
    _commit_all(cwd, "feature 2")
    G2 = _graph([("a", {"label": "A"}), ("c", {"label": "C"})], [])  # b removed, c added
    ab.push_branch(_conninfo(), repository_id, "feature", G2, cwd=cwd, default_branch="main", **_push_kwargs())

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        from psycopg import sql
        cur.execute(
            sql.SQL("SELECT * FROM cypher({g}, $$ MATCH (n) RETURN n.id $$) AS (id agtype);")
            .format(g=sql.Literal("graphify_e2e__feature"))
        )
        ids = sorted(str(r[0]).strip('"') for r in cur.fetchall())
    assert ids == ["a", "c"]


def test_reap_branch_drops_graph_after_idle_threshold(conn, repository_id, tmp_path):
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha, _graph([], []), **_push_kwargs())
    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature")
    G = _graph([("a", {"label": "A"})], [])
    ab.push_branch(_conninfo(), repository_id, "feature", G, cwd=cwd, default_branch="main", **_push_kwargs())
    ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")

    not_yet = ab.reap_branch(_conninfo(), repository_id, "feature", min_idle_seconds=3600)
    assert not_yet["reaped"] is False

    result = ab.reap_branch(_conninfo(), repository_id, "feature", min_idle_seconds=0)
    assert result["reaped"] is True

    with conn.cursor() as cur:
        cur.execute(
            "SELECT materialized, age_graph_name FROM graphify_branches "
            "WHERE repository_id = %s AND branch = %s;", (repository_id, "feature"),
        )
        materialized, age_graph_name = cur.fetchone()
    assert materialized is False
    assert age_graph_name is None

    # Diff rows/snapshots are retained -- re-materializing must still work.
    remat = ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_e2e")
    assert remat["already_materialized"] is False


def test_cross_branch_comparison_query(conn, repository_id, tmp_path):
    """docs/AGE_SCHEMA.md's pinned cross-branch comparison query: two
    independent cypher() calls joined in one SQL statement, no
    cross-graph Cypher syntax needed."""
    cwd = _repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    main_sha = _commit_all(cwd, "main")
    snap.record_snapshot(_conninfo(), repository_id, main_sha,
                          _graph([("a", {"label": "A", "file_type": "code"})], []), **_push_kwargs())
    from graphify.exporters.graphdb import push_to_age
    push_to_age(_graph([("a", {"label": "A", "file_type": "code"})], []),
                conninfo=_conninfo(), graph_name="graphify_cmp")

    _git(cwd, "checkout", "-qb", "feature")
    (tmp_path / "b.py").write_text("y = 1\n")
    _commit_all(cwd, "feature")
    G_branch = _graph(
        [("a", {"label": "A", "file_type": "code"}), ("b", {"label": "B", "file_type": "code"})], []
    )
    ab.push_branch(_conninfo(), repository_id, "feature", G_branch, cwd=cwd,
                    default_branch="main", **_push_kwargs())
    ab.materialize_branch(_conninfo(), repository_id, "feature", default_graph_name="graphify_cmp")

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("""
            SELECT feature.id FROM
              cypher('graphify_cmp__feature', $$ MATCH (n) RETURN n.id $$) AS feature(id agtype)
              LEFT JOIN
              cypher('graphify_cmp', $$ MATCH (n) RETURN n.id $$) AS base(id agtype)
              ON feature.id = base.id
            WHERE base.id IS NULL;
        """)
        only_in_feature = [str(r[0]).strip('"') for r in cur.fetchall()]
    assert only_in_feature == ["b"]


def test_advisory_lock_blocks_concurrent_holder(conn):
    """Deterministic concurrency check (docs/AGE_PLAN.md Phase 4): a second
    connection's pg_try_advisory_lock must fail while the first holds the
    same key -- no sleep-based races. Takes the `conn` fixture purely so
    this test skips (rather than erroring) when no live AGE-enabled
    Postgres is reachable, matching every other test in this file."""
    key = ab._advisory_lock_key("repo-x", "branch-y")
    conn1 = psycopg.connect(_conninfo())
    conn2 = psycopg.connect(_conninfo())
    try:
        with conn1.cursor() as cur1:
            cur1.execute("SELECT pg_advisory_lock(%s);", (key,))
        conn1.commit()

        with conn2.cursor() as cur2:
            cur2.execute("SELECT pg_try_advisory_lock(%s);", (key,))
            (acquired,) = cur2.fetchone()
        conn2.rollback()
        assert acquired is False

        with conn1.cursor() as cur1:
            cur1.execute("SELECT pg_advisory_unlock(%s);", (key,))
        conn1.commit()

        with conn2.cursor() as cur2:
            cur2.execute("SELECT pg_try_advisory_lock(%s);", (key,))
            (acquired_after_release,) = cur2.fetchone()
        conn2.commit()
        assert acquired_after_release is True
        with conn2.cursor() as cur2:
            cur2.execute("SELECT pg_advisory_unlock(%s);", (key,))
        conn2.commit()
    finally:
        conn1.close()
        conn2.close()
