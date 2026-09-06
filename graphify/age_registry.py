"""Apache AGE registry: repository identity, ownership, and the authoritative
SQL schema for multi-repo/multi-branch tracking (docs/AGE_PLAN.md Phase 2).

This is plain PostgreSQL, not AGE: the registry tables live outside any AGE
graph namespace, since AGE-owned label tables accept no direct DML/DDL and
the registry must be queryable/writable with ordinary SQL. Registry tests
are tier 2 in docs/AGE_PLAN.md's "Testing strategy" (a live Postgres probe,
no AGE extension required).
"""
from __future__ import annotations

import re
import subprocess as _sp
import uuid
from pathlib import Path
from urllib.parse import urlparse

# Fixed namespace for deriving a stable repository_id from a normalized
# remote URL via uuid5 (docs/AGE_PLAN.md: "a stable repository_id (UUID)
# keyed off the normalized remote URL"). Never change this constant -
# doing so would silently mint new repository_ids for every existing repo.
_REPOSITORY_ID_NAMESPACE = uuid.UUID("6f6e6570-6167-6531-4147-450000000001")

# Bump when the Cypher-facing node/edge schema (docs/AGE_SCHEMA.md) changes
# in a way that makes an old graph incompatible with new agent queries.
SCHEMA_VERSION = "1"


# ---------------------------------------------------------------------------
# Identity: normalizing a git remote URL to a stable dedup key, and owner
# resolution. Pure functions, tier-1 testable (no DB, no subprocess).
# ---------------------------------------------------------------------------

def normalize_remote_url(remote_url: str) -> str:
    """Canonicalize a git remote URL to "<host>/<owner>/<repo>", lowercased,
    with no scheme, credentials, trailing ".git", or trailing slash.

    Handles the two common forms:
      git@github.com:owner/repo.git      -> github.com/owner/repo
      https://github.com/owner/repo.git  -> github.com/owner/repo

    This is the string hashed into repository_id (see repository_id_for) -
    two remotes that normalize the same are the same repository, so ssh vs.
    https clones of the same repo share one registry row.
    """
    url = remote_url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]

    scp_match = re.match(r"^(?:[\w.-]+@)?([\w.-]+):(.+)$", url)
    if "://" not in url and scp_match:
        host, path = scp_match.groups()
    else:
        parsed = urlparse(url if "://" in url else f"ssh://{url}")
        host = parsed.hostname or ""
        path = parsed.path

    host = host.strip("/")
    path = path.strip("/")
    # Lowercase the whole key, not just the host: GitHub/GitLab/etc. repo
    # paths are case-insensitive for routing even though case is preserved
    # for display, so two remotes differing only in path case are the same
    # repository and must dedupe to one registry row.
    return (f"{host}/{path}" if host else path).lower()


def repository_id_for(remote_url: str) -> str:
    """Deterministic UUID (as a string) for a repository, derived from its
    normalized remote URL. The same repo always maps to the same id,
    without a database round trip - the id can be computed client-side
    before the repo has ever been registered.
    """
    return str(uuid.uuid5(_REPOSITORY_ID_NAMESPACE, normalize_remote_url(remote_url)))


def resolve_owner(
    explicit: str | None = None,
    remote_url: str | None = None,
    git_email: str | None = None,
) -> str | None:
    """Owner resolution order (docs/AGE_PLAN.md "Ownership"):
    explicit --owner flag -> the owner segment of the git remote URL
    (github.com/<owner>/<repo>) -> `git config user.email`.
    """
    if explicit:
        return explicit
    if remote_url:
        normalized = normalize_remote_url(remote_url)
        parts = normalized.split("/")
        if len(parts) >= 2:
            return parts[-2]
    if git_email:
        return git_email
    return None


# ---------------------------------------------------------------------------
# Git helpers, cwd-anchored like graphify.watch._git_head (#2316): without
# an explicit cwd these would silently report the *invoker's* repo instead
# of the target repo when export is run from the wrong directory.
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path | str | None = None) -> str | None:
    try:
        r = _sp.run(
            ["git", *args], capture_output=True, text=True, timeout=3,
            cwd=str(cwd) if cwd is not None else None,
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def current_branch(cwd: Path | str | None = None) -> str | None:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)


def current_commit_sha(cwd: Path | str | None = None) -> str | None:
    from graphify.watch import _git_head
    return _git_head(cwd=cwd)


def git_remote_url(cwd: Path | str | None = None, remote: str = "origin") -> str | None:
    return _run_git(["remote", "get-url", remote], cwd=cwd)


def git_user_email(cwd: Path | str | None = None) -> str | None:
    return _run_git(["config", "user.email"], cwd=cwd)


def graphify_package_version() -> str:
    import importlib.metadata
    try:
        return importlib.metadata.version("graphifyy")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - editable/dev installs
        return "0.0.0-dev"


# ---------------------------------------------------------------------------
# Authoritative SQL schema (docs/AGE_PLAN.md "Registry and authoritative SQL
# schema"). Applied as an ordered list of idempotent migrations, tracked in
# graphify_registry_migrations so re-running ensure_schema() is a no-op once
# every migration has landed - a lightweight versioned migration, not a
# dependency on an external migration framework.
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[int, str]] = [
    (1, """
        CREATE TABLE IF NOT EXISTS graphify_repos (
            repository_id UUID PRIMARY KEY,
            remote_url TEXT UNIQUE NOT NULL,
            repo_tag TEXT,
            owner_id TEXT,
            default_branch TEXT,
            age_graph_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS graphify_snapshots (
            snapshot_id UUID PRIMARY KEY,
            repository_id UUID NOT NULL REFERENCES graphify_repos,
            commit_sha TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('checkpoint', 'delta')),
            parent_snapshot_id UUID,
            payload JSONB,
            graphify_version TEXT,
            schema_version TEXT,
            extraction_config_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (repository_id, commit_sha, kind, schema_version,
                    extraction_config_hash, graphify_version)
        );

        CREATE TABLE IF NOT EXISTS graphify_branches (
            repository_id UUID NOT NULL REFERENCES graphify_repos,
            branch TEXT NOT NULL,
            base_commit_sha TEXT,
            head_commit_sha TEXT,
            base_snapshot_id UUID REFERENCES graphify_snapshots,
            age_graph_name TEXT,
            materialized BOOLEAN NOT NULL DEFAULT false,
            last_push_hash TEXT,
            pushed_by TEXT,
            pushed_at TIMESTAMPTZ,
            bytes_used BIGINT,
            graphify_version TEXT,
            schema_version TEXT,
            extraction_config_hash TEXT,
            PRIMARY KEY (repository_id, branch)
        );

        CREATE TABLE IF NOT EXISTS graphify_branch_revisions (
            repository_id UUID NOT NULL,
            branch TEXT NOT NULL,
            generation BIGINT NOT NULL,
            base_commit_sha TEXT,
            head_commit_sha TEXT,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (repository_id, branch, generation),
            FOREIGN KEY (repository_id, branch) REFERENCES graphify_branches
        );

        CREATE UNIQUE INDEX IF NOT EXISTS graphify_one_active_branch_revision
            ON graphify_branch_revisions (repository_id, branch)
            WHERE active;

        CREATE TABLE IF NOT EXISTS graphify_branch_diff (
            repository_id UUID NOT NULL,
            branch TEXT NOT NULL,
            generation BIGINT NOT NULL,
            seq BIGINT NOT NULL,
            from_commit_sha TEXT,
            to_commit_sha TEXT,
            kind TEXT NOT NULL CHECK (kind IN (
                'node_add', 'node_del', 'node_change',
                'edge_add', 'edge_del', 'edge_change'
            )),
            payload JSONB NOT NULL,
            PRIMARY KEY (repository_id, branch, generation, seq),
            FOREIGN KEY (repository_id, branch, generation)
                REFERENCES graphify_branch_revisions
        );

        CREATE TABLE IF NOT EXISTS graphify_quality_findings (
            repository_id UUID NOT NULL,
            commit_sha TEXT NOT NULL,
            node_id TEXT NOT NULL,
            rule TEXT NOT NULL,
            severity TEXT,
            evidence JSONB,
            tool_version TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """),
]


def ensure_schema(conninfo: str) -> None:
    """Apply every not-yet-applied migration, in order, inside one
    transaction per migration. Safe to call on every push - a fully
    migrated database is a no-op.
    """
    try:
        import psycopg
    except ImportError as e:
        raise ImportError(
            'psycopg not installed. Run: pip install "graphifyy[age]"'
        ) from e

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS graphify_registry_migrations ("
                "  version INT PRIMARY KEY,"
                "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ");"
            )
            cur.execute("SELECT version FROM graphify_registry_migrations;")
            applied = {row[0] for row in cur.fetchall()}
            for version, sql in _MIGRATIONS:
                if version in applied:
                    continue
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO graphify_registry_migrations (version) VALUES (%s);",
                    (version,),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def register_repository(
    conninfo: str,
    remote_url: str,
    *,
    repo_tag: str | None = None,
    owner_id: str | None = None,
    default_branch: str | None = None,
    age_graph_name: str | None = None,
) -> dict:
    """Upsert this repository's identity row and return it as a dict.

    Ensures the registry schema exists first (see ensure_schema). Fields
    passed as None do not overwrite an existing non-null value on conflict
    - a later push that doesn't know the owner, say, won't blank it out.
    """
    import psycopg

    ensure_schema(conninfo)
    repository_id = repository_id_for(remote_url)
    normalized = normalize_remote_url(remote_url)

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO graphify_repos
                    (repository_id, remote_url, repo_tag, owner_id,
                     default_branch, age_graph_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (remote_url) DO UPDATE SET
                    repo_tag = COALESCE(EXCLUDED.repo_tag, graphify_repos.repo_tag),
                    owner_id = COALESCE(EXCLUDED.owner_id, graphify_repos.owner_id),
                    default_branch = COALESCE(EXCLUDED.default_branch, graphify_repos.default_branch),
                    age_graph_name = COALESCE(EXCLUDED.age_graph_name, graphify_repos.age_graph_name),
                    updated_at = now()
                RETURNING repository_id, remote_url, repo_tag, owner_id,
                          default_branch, age_graph_name, created_at, updated_at;
                """,
                (repository_id, normalized, repo_tag, owner_id, default_branch, age_graph_name),
            )
            row = cur.fetchone()
            columns = [d.name for d in cur.description]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result = dict(zip(columns, row))
    # psycopg adapts the UUID column to a Python uuid.UUID; normalize to
    # str so callers (CLI output, JSON, comparisons against
    # repository_id_for()'s str return) get one consistent type.
    result["repository_id"] = str(result["repository_id"])
    return result


def get_repository(conninfo: str, remote_url: str) -> dict | None:
    """Read-only lookup of this repository's registry row, or None if it
    isn't registered yet (or the registry schema doesn't exist at all).

    Used by callers (docs/AGE_PLAN.md Phase 4's branch-aware CLI dispatch)
    that need the registered default_branch to decide whether the current
    push targets the default branch or a feature branch, without the
    side-effecting upsert register_repository() always performs.
    """
    import psycopg

    repository_id = repository_id_for(remote_url)
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT repository_id, remote_url, repo_tag, owner_id, "
                    "default_branch, age_graph_name FROM graphify_repos "
                    "WHERE repository_id = %s;",
                    (repository_id,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return None
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d.name for d in cur.description]
    finally:
        conn.close()

    result = dict(zip(columns, row))
    result["repository_id"] = str(result["repository_id"])
    return result


def resolve_age_graph_name(
    conninfo: str, remote_url: str, branch: str | None = None
) -> str | None:
    """Agent-facing discovery: which AGE graph holds `remote_url`'s `branch`?

    Returns the durable default-branch graph name when `branch` is None or
    equals the registered default branch; otherwise looks up
    graphify_branches (populated starting in Phase 4 - returns None for an
    unmaterialized or not-yet-known branch, meaning "not registered/not
    materialized", not "the default branch"). Also returns None (rather
    than raising) if the registry schema doesn't exist yet at all - a
    read-only discovery call has no business creating tables as a side
    effect, so an unmigrated database just means "nothing registered".
    """
    import psycopg

    repository_id = repository_id_for(remote_url)
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT default_branch, age_graph_name FROM graphify_repos "
                    "WHERE repository_id = %s;",
                    (repository_id,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return None
            row = cur.fetchone()
            if row is None:
                return None
            default_branch, default_graph_name = row
            if branch is None or branch == default_branch:
                return default_graph_name
            cur.execute(
                "SELECT age_graph_name FROM graphify_branches "
                "WHERE repository_id = %s AND branch = %s;",
                (repository_id, branch),
            )
            branch_row = cur.fetchone()
            return branch_row[0] if branch_row else None
    finally:
        conn.close()
