"""Tier-2 integration tests for graphify.age_registry (docs/AGE_PLAN.md
"Testing strategy"): a live PostgreSQL instance is required, but the AGE
extension is NOT - the registry tables are plain SQL outside any AGE graph
namespace. Reuses the same apache/age container as
tests/test_age_integration.py for convenience (it's a Postgres server that
happens to also have AGE installed), but the probe here only checks for
plain Postgres connectivity, not `LOAD 'age'`.

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_registry_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching test_age_integration.py's convention.
"""
from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from graphify import age_registry as reg  # noqa: E402

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


def _unique_remote() -> str:
    # Unique per test so parallel/rerun invocations never collide.
    return f"https://github.com/testowner/repo-{uuid.uuid4().hex[:8]}.git"


def test_ensure_schema_is_idempotent(conn):
    reg.ensure_schema(_conninfo())
    reg.ensure_schema(_conninfo())  # must not raise or duplicate migrations
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graphify_registry_migrations;")
        (count,) = cur.fetchone()
    assert count == len(reg._MIGRATIONS)


def test_register_repository_creates_row(conn):
    remote = _unique_remote()
    row = reg.register_repository(
        _conninfo(), remote, repo_tag="myrepo", owner_id="testowner",
        default_branch="main", age_graph_name="graphify_myrepo",
    )
    assert row["repository_id"] == reg.repository_id_for(remote)
    assert row["remote_url"] == reg.normalize_remote_url(remote)
    assert row["repo_tag"] == "myrepo"
    assert row["owner_id"] == "testowner"
    assert row["default_branch"] == "main"
    assert row["age_graph_name"] == "graphify_myrepo"


def test_register_repository_is_idempotent_by_remote_url(conn):
    remote = _unique_remote()
    row1 = reg.register_repository(_conninfo(), remote, repo_tag="a")
    row2 = reg.register_repository(_conninfo(), remote, repo_tag="a")
    assert row1["repository_id"] == row2["repository_id"]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graphify_repos WHERE remote_url = %s;",
                     (reg.normalize_remote_url(remote),))
        (count,) = cur.fetchone()
    assert count == 1


def test_register_repository_does_not_null_out_existing_fields(conn):
    """A later push that doesn't know the owner must not blank it out -
    COALESCE keeps the previously-registered value."""
    remote = _unique_remote()
    reg.register_repository(_conninfo(), remote, owner_id="alice", repo_tag="a")
    row = reg.register_repository(_conninfo(), remote, owner_id=None, repo_tag="b")
    assert row["owner_id"] == "alice"
    assert row["repo_tag"] == "b"


def test_ssh_and_https_remotes_dedupe_to_one_repository(conn):
    suffix = uuid.uuid4().hex[:8]
    https = f"https://github.com/testowner/repo-{suffix}.git"
    ssh = f"git@github.com:testowner/repo-{suffix}.git"
    row1 = reg.register_repository(_conninfo(), https, repo_tag="via-https")
    row2 = reg.register_repository(_conninfo(), ssh, repo_tag="via-ssh")
    assert row1["repository_id"] == row2["repository_id"]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graphify_repos WHERE repository_id = %s;",
                     (row1["repository_id"],))
        (count,) = cur.fetchone()
    assert count == 1


def test_resolve_age_graph_name_for_default_branch(conn):
    remote = _unique_remote()
    reg.register_repository(
        _conninfo(), remote, default_branch="main", age_graph_name="graphify_x"
    )
    assert reg.resolve_age_graph_name(_conninfo(), remote) == "graphify_x"
    assert reg.resolve_age_graph_name(_conninfo(), remote, branch="main") == "graphify_x"


def test_resolve_age_graph_name_unknown_branch_returns_none(conn):
    remote = _unique_remote()
    reg.register_repository(
        _conninfo(), remote, default_branch="main", age_graph_name="graphify_x"
    )
    assert reg.resolve_age_graph_name(_conninfo(), remote, branch="feature/x") is None


def test_resolve_age_graph_name_unregistered_repo_returns_none(conn):
    assert reg.resolve_age_graph_name(_conninfo(), _unique_remote()) is None


def test_partial_unique_index_rejects_second_active_revision(conn):
    """The one-active-generation-per-branch invariant from
    docs/AGE_PLAN.md, enforced in the database."""
    remote = _unique_remote()
    row = reg.register_repository(_conninfo(), remote, default_branch="main")
    repository_id = row["repository_id"]

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO graphify_branches (repository_id, branch) VALUES (%s, %s);",
            (repository_id, "main"),
        )
        cur.execute(
            "INSERT INTO graphify_branch_revisions "
            "(repository_id, branch, generation, active) VALUES (%s, %s, 1, true);",
            (repository_id, "main"),
        )
    conn.commit()

    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO graphify_branch_revisions "
                "(repository_id, branch, generation, active) VALUES (%s, %s, 2, true);",
                (repository_id, "main"),
            )
    conn.rollback()

    # A second INACTIVE revision for the same branch is fine - only one
    # active generation is enforced.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO graphify_branch_revisions "
            "(repository_id, branch, generation, active) VALUES (%s, %s, 2, false);",
            (repository_id, "main"),
        )
    conn.commit()


def test_snapshot_uniqueness_allows_delta_and_checkpoint_to_coexist(conn):
    """docs/AGE_PLAN.md: a commit may first be stored as a delta and later
    also gain a reconstructed checkpoint; both records are immutable and
    coexist because `kind` is part of the unique key."""
    remote = _unique_remote()
    row = reg.register_repository(_conninfo(), remote)
    repository_id = row["repository_id"]

    with conn.cursor() as cur:
        for kind in ("delta", "checkpoint"):
            cur.execute(
                "INSERT INTO graphify_snapshots "
                "(snapshot_id, repository_id, commit_sha, kind, schema_version, "
                " extraction_config_hash, graphify_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s);",
                (str(uuid.uuid4()), repository_id, "abc123", kind, "1", "cfg1", "0.9.54"),
            )
        cur.execute(
            "SELECT count(*) FROM graphify_snapshots WHERE repository_id = %s;",
            (repository_id,),
        )
        (count,) = cur.fetchone()
    assert count == 2
    conn.commit()

    # But a second delta for the exact same key must be rejected.
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO graphify_snapshots "
                "(snapshot_id, repository_id, commit_sha, kind, schema_version, "
                " extraction_config_hash, graphify_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s);",
                (str(uuid.uuid4()), repository_id, "abc123", "delta", "1", "cfg1", "0.9.54"),
            )
    conn.rollback()
