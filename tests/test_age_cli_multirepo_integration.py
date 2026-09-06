"""Tier-3 regression test (post-review, docs/AGE_PLAN.md v15) for the
critical default-AGE-graph-name collision: `graphify export age --push`
used to default every repository to the literal graph name "graphify"
when `--graph-name` wasn't passed, so a second repository's push -- via
push_to_age()'s deletion-safe reconcile -- would delete the first
repository's nodes and edges. Fixed by deriving a default graph name from
repository_id (graphify.age_registry.default_age_graph_name) instead.

This drives the real CLI entry point (`graphify.__main__.main()`) end to
end, from two separate git repositories with distinct remotes, exactly
the way a user hitting this bug would.

    docker run -d --name graphify-age -p 5432:5432 \\
        -e POSTGRES_PASSWORD=graphify_test \\
        apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb
    uv run pytest tests/test_age_cli_multirepo_integration.py -q

Host/port/db/user/password: AGE_HOST / AGE_PORT / AGE_DB / AGE_USER /
AGE_PASSWORD, matching the other AGE live-suite files' convention.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

import graphify.__main__ as mainmod  # noqa: E402
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


def _make_repo(root, remote_url: str, node_id: str):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "remote", "add", "origin", remote_url)
    out_dir = root / "graphify-out"
    out_dir.mkdir()
    graph = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": node_id, "label": node_id, "file_type": "code"}],
        "links": [],
    }
    (out_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (root / "README.md").write_text(node_id, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")


def _run_cli(monkeypatch, cwd, argv: list[str]) -> None:
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    mainmod.main()


def _fetch_age_node_ids(conn, graph_name: str) -> set[str]:
    from psycopg import sql

    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (graph_name,)
        )
        if not cur.fetchone()[0]:
            return set()
        # cypher()'s graph name argument must be a SQL literal, not a bind
        # parameter (AGE rejects a parameterized graph name) -- same
        # constraint push_to_age() is built around.
        cur.execute(
            sql.SQL("SELECT * FROM cypher({graph}, $$ MATCH (n) RETURN n.id $$) AS (id agtype);").format(
                graph=sql.Literal(graph_name)
            )
        )
        return {str(r[0]).strip('"') for r in cur.fetchall()}


def test_first_push_from_feature_branch_uses_explicit_default_branch(conn, tmp_path, monkeypatch, capsys):
    """Regression (found via review): an unregistered repository's first
    `graphify export age` push used to unconditionally treat whatever
    branch was currently checked out as the default branch -- pushing
    first from a feature branch with no `origin/HEAD` set would register
    *that* branch as the durable default-branch graph, with no diff chain
    recorded at all. --default-branch must let the caller state the truth
    explicitly."""
    repo = tmp_path / "repo_feature_first"
    remote = f"https://github.com/testowner/feature-first-{uuid.uuid4().hex[:8]}.git"
    _make_repo(repo, remote, "node_on_main")
    _git(repo, "checkout", "-qb", "feature/foo")
    (repo / "graphify-out" / "graph.json").write_text(
        json.dumps({
            "directed": False, "multigraph": False, "graph": {},
            "nodes": [{"id": "node_on_main", "label": "node_on_main", "file_type": "code"},
                      {"id": "node_on_feature", "label": "node_on_feature", "file_type": "code"}],
            "links": [],
        }),
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature work")

    conninfo = _conninfo()
    _run_cli(monkeypatch, repo, ["export", "age", "--push", conninfo, "--default-branch", "main"])

    row = reg.get_repository(conninfo, remote)
    assert row["default_branch"] == "main"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT branch FROM graphify_branches WHERE repository_id = %s;",
            (row["repository_id"],),
        )
        branch_rows = cur.fetchall()
    assert branch_rows == [("feature/foo",)]


def test_first_push_from_feature_branch_without_default_branch_warns(conn, tmp_path, monkeypatch, capsys):
    """Without --default-branch and no resolvable origin/HEAD, the CLI
    still proceeds (backward-compatible for the common single-branch
    workflow) but must say plainly that it's guessing, rather than
    silently registering a feature branch as the default."""
    repo = tmp_path / "repo_feature_no_flag"
    remote = f"https://github.com/testowner/feature-no-flag-{uuid.uuid4().hex[:8]}.git"
    _make_repo(repo, remote, "node_on_main")
    _git(repo, "checkout", "-qb", "feature/bar")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "feature work")

    _run_cli(monkeypatch, repo, ["export", "age", "--push", _conninfo()])
    err = capsys.readouterr().err
    assert "could not confirm this repository's default branch" in err
    assert "feature/bar" in err


def test_two_repos_pushed_without_graph_name_do_not_collide(conn, tmp_path, monkeypatch):
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    remote_a = f"https://github.com/testowner/repo-a-{uuid.uuid4().hex[:8]}.git"
    remote_b = f"https://github.com/testowner/repo-b-{uuid.uuid4().hex[:8]}.git"
    _make_repo(repo_a, remote_a, "node_from_a")
    _make_repo(repo_b, remote_b, "node_from_b")

    conninfo = _conninfo()
    push_argv = ["export", "age", "--push", conninfo]

    _run_cli(monkeypatch, repo_a, push_argv)
    _run_cli(monkeypatch, repo_b, push_argv)

    repo_id_a = reg.repository_id_for(remote_a)
    repo_id_b = reg.repository_id_for(remote_b)
    row_a = reg.get_repository(conninfo, remote_a)
    row_b = reg.get_repository(conninfo, remote_b)
    assert row_a is not None and row_b is not None

    graph_name_a = row_a["age_graph_name"]
    graph_name_b = row_b["age_graph_name"]
    # The critical bug: both used to default to the literal "graphify".
    assert graph_name_a != graph_name_b
    assert graph_name_a == reg.default_age_graph_name(repo_id_a)
    assert graph_name_b == reg.default_age_graph_name(repo_id_b)

    # And, most importantly: repo B's push must not have deleted repo A's
    # nodes via the deletion-safe reconcile (they'd only collide if both
    # landed in the same graph).
    assert _fetch_age_node_ids(conn, graph_name_a) == {"node_from_a"}
    assert _fetch_age_node_ids(conn, graph_name_b) == {"node_from_b"}
