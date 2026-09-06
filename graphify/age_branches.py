"""Apache AGE branches: commit-anchored diffs, lazy materialization, and
reaping (docs/AGE_PLAN.md Phase 4).

A non-default branch is never pushed as its own full AGE graph up front.
Instead, `push_branch()` records an ordered, reversible diff chain in
`graphify_branch_diff` (Phase 2's schema) against a pinned base snapshot;
an AGE graph only gets created the first time something actually queries
the branch, via `materialize_branch()`. `reap_branch()` drops that graph
again once it's gone idle -- the diff rows and snapshots are never
deleted, so a reaped branch can always be rehydrated.

Replay/validation logic (`replay_branch_diffs`, `diff_to_rows`,
`rows_to_diff`) is pure and DB-free (tier-1 testable against NetworkX
directly); only `push_branch`/`materialize_branch`/`reap_branch` touch
Postgres, and only `materialize_branch` touches AGE.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess as _sp
import tempfile
import uuid
from pathlib import Path

import networkx as nx

# ---------------------------------------------------------------------------
# Git helpers, cwd-anchored like graphify.age_registry's (#2316 precedent).
# ---------------------------------------------------------------------------

def merge_base(cwd: Path | str | None, ref_a: str, ref_b: str) -> str | None:
    from graphify.age_registry import _run_git
    return _run_git(["merge-base", ref_a, ref_b], cwd=cwd)


def is_ancestor(cwd: Path | str | None, ancestor: str, descendant: str) -> bool:
    """git merge-base --is-ancestor communicates purely via exit code (no
    stdout on success), so this can't reuse age_registry._run_git, which
    treats empty-stdout-on-success the same as failure."""
    try:
        r = _sp.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True, text=True, timeout=5,
            cwd=str(cwd) if cwd is not None else None,
        )
        return r.returncode == 0
    except Exception:
        return False


def detect_rebase(cwd: Path | str | None, old_head: str | None, new_head: str) -> bool:
    """True when `old_head` is no longer an ancestor of `new_head` -- a
    force-push or rebase happened since the last push, per
    docs/AGE_PLAN.md Phase 4."""
    if old_head is None or old_head == new_head:
        return False
    return not is_ancestor(cwd, old_head, new_head)


def _extract_graph_at_commit(cwd: Path | str, commit_sha: str) -> nx.Graph:
    """Fallback path 2 for a missing base snapshot: extract at an
    arbitrary historical commit via a temporary git worktree.

    Only used when the commit predates every retained checkpoint/delta
    (see ensure_base_snapshot) -- the normal path reconstructs from
    graphify_snapshots without touching git at all.
    """
    from graphify.build import build
    from graphify.extract import collect_files, extract

    with tempfile.TemporaryDirectory(prefix="graphify-age-worktree-") as tmpdir:
        worktree = Path(tmpdir) / "wt"
        add = _sp.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit_sha],
            cwd=str(cwd), capture_output=True, text=True, timeout=60,
        )
        if add.returncode != 0:
            raise RuntimeError(
                f"could not create a git worktree at {commit_sha}: {add.stderr.strip()}"
            )
        try:
            paths = collect_files(worktree)
            extraction = extract(paths, root=worktree)
            return build([extraction], root=worktree)
        finally:
            _sp.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=str(cwd), capture_output=True, text=True, timeout=30,
            )


# ---------------------------------------------------------------------------
# Pure helpers: AGE branch-graph naming, diff row (de)serialization, and
# replay validation. Tier-1 testable, no DB.
# ---------------------------------------------------------------------------

_POSTGRES_IDENTIFIER_MAX_BYTES = 63


def sanitize_branch_graph_name(base_graph_name: str, branch: str) -> str:
    """`<base_graph_name>__<sanitized branch>`, with a hashing fallback
    when that would exceed Postgres's 63-byte identifier limit."""
    safe_branch = re.sub(r"[^A-Za-z0-9_]", "_", branch)
    candidate = f"{base_graph_name}__{safe_branch}"
    if len(candidate.encode("utf-8")) <= _POSTGRES_IDENTIFIER_MAX_BYTES:
        return candidate

    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:16]
    suffix = f"__{digest}"
    max_base_bytes = _POSTGRES_IDENTIFIER_MAX_BYTES - len(suffix.encode("utf-8"))
    truncated_base = base_graph_name.encode("utf-8")[:max_base_bytes].decode("utf-8", "ignore")
    return f"{truncated_base}{suffix}"


_KIND_TO_BUCKET = {
    "node_add": "new_nodes",
    "node_del": "removed_nodes",
    "node_change": "changed_nodes",
    "edge_add": "new_edges",
    "edge_del": "removed_edges",
    "edge_change": "changed_edges",
}
_BUCKET_TO_KIND = {v: k for k, v in _KIND_TO_BUCKET.items()}
_DIFF_BUCKETS = (
    "removed_nodes", "new_nodes", "changed_nodes",
    "removed_edges", "new_edges", "changed_edges",
)


def diff_to_rows(diff: dict) -> list[tuple[str, dict]]:
    """A graph_diff()-shaped dict -> ordered (kind, payload) pairs matching
    graphify_branch_diff's `kind` CHECK constraint. Pure, DB-free."""
    rows = []
    for bucket in _DIFF_BUCKETS:
        kind = _BUCKET_TO_KIND[bucket]
        for entry in diff.get(bucket, []):
            rows.append((kind, entry))
    return rows


def rows_to_diff(kind_payload_pairs: list[tuple[str, dict]]) -> dict:
    """Inverse of diff_to_rows(): reconstructs a graph_diff()-shaped dict
    from stored (kind, payload) rows, ready for
    age_snapshots.apply_diff_to_payload(). Pure, DB-free."""
    diff: dict = {bucket: [] for bucket in _DIFF_BUCKETS}
    for kind, payload in kind_payload_pairs:
        diff[_KIND_TO_BUCKET[kind]].append(payload)
    return diff


def replay_branch_diffs(
    base_payload: dict,
    rows: list[tuple],
    *,
    base_commit_sha: str,
    head_commit_sha: str,
) -> dict:
    """Replay ordered `(seq, generation, from_commit_sha, to_commit_sha,
    kind, payload)` rows (already sorted by seq) onto `base_payload`,
    producing the payload at `head_commit_sha`.

    Validates the chain before replaying anything: rejects rows spanning
    more than one generation (a caller bug -- always query one active
    generation), and rejects a non-contiguous transition chain (a gap, or
    one that doesn't actually start at base_commit_sha / end at
    head_commit_sha). Pure and DB-free (tier-1 testable) -- the only
    DB-dependent part is fetching `rows` and `base_payload` in the first
    place.
    """
    from graphify import age_snapshots as _snap

    if not rows:
        if base_commit_sha != head_commit_sha:
            raise ValueError(
                f"no diff rows but base_commit_sha {base_commit_sha!r} != "
                f"head_commit_sha {head_commit_sha!r}"
            )
        return base_payload

    generations = {r[1] for r in rows}
    if len(generations) > 1:
        raise ValueError(f"diff rows span multiple generations: {sorted(generations)}")

    transitions: list[list] = []  # [from_sha, to_sha, [(kind, payload), ...]]
    for row in rows:
        _seq, _generation, from_sha, to_sha, kind, payload = row
        if transitions and (transitions[-1][0], transitions[-1][1]) == (from_sha, to_sha):
            transitions[-1][2].append((kind, payload))
        else:
            transitions.append([from_sha, to_sha, [(kind, payload)]])

    if transitions[0][0] != base_commit_sha:
        raise ValueError(
            f"diff chain starts at {transitions[0][0]!r}, not "
            f"base_commit_sha {base_commit_sha!r}"
        )
    for i in range(len(transitions) - 1):
        if transitions[i][1] != transitions[i + 1][0]:
            raise ValueError(
                f"non-contiguous diff chain: {transitions[i][1]!r} -> "
                f"{transitions[i + 1][0]!r}"
            )
    if transitions[-1][1] != head_commit_sha:
        raise ValueError(
            f"diff chain ends at {transitions[-1][1]!r}, not "
            f"head_commit_sha {head_commit_sha!r}"
        )

    payload = base_payload
    for _from_sha, _to_sha, kind_payload_pairs in transitions:
        payload = _snap.apply_diff_to_payload(payload, rows_to_diff(kind_payload_pairs))
    return payload


def _advisory_lock_key(repository_id: str, branch: str) -> int:
    """A deterministic bigint key for pg_advisory_lock, keyed on
    (repository_id, branch) per docs/AGE_PLAN.md Phase 4."""
    digest = hashlib.sha256(f"{repository_id}:{branch}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


# ---------------------------------------------------------------------------
# DB-dependent machinery: base-snapshot resolution, branch push, lazy
# materialization, and reaping. Tier 2/3 (live Postgres, AGE only for
# materialize_branch/reap_branch's graph mutation).
# ---------------------------------------------------------------------------

def ensure_base_snapshot(
    conninfo: str,
    repository_id: str,
    base_commit_sha: str,
    *,
    cwd: Path | str | None,
    graphify_version: str | None,
    schema_version: str | None,
    extraction_config_hash: str | None = None,
) -> tuple[str, nx.Graph]:
    """Resolve `base_commit_sha`'s graph, creating it if nothing retained
    already covers that exact commit (docs/AGE_PLAN.md Phase 4's
    missing-base-snapshot fallback chain):

    1. If a graphify_snapshots row already exists at that commit_sha for
       this repository, reconstruct up to (and including) it.
    2. Otherwise, extract at that commit via a temporary git worktree and
       persist the result as a backdated historical checkpoint, so this
       resolution only has to happen once per commit.

    Returns (snapshot_id, graph).
    """
    import psycopg
    from graphify import age_snapshots as _snap

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT snapshot_id, commit_sha, kind, payload FROM graphify_snapshots "
                    "WHERE repository_id = %s ORDER BY created_at ASC;",
                    (repository_id,),
                )
                rows = cur.fetchall()
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                rows = []
    finally:
        conn.close()

    match = next((r for r in rows if r[1] == base_commit_sha), None)
    if match is not None:
        payload, _commit_sha, snapshot_id = _snap._reconstruct_payload_up_to(rows, match[0])
        if payload is not None:
            return snapshot_id, _snap.payload_to_graph(payload)

    G = _extract_graph_at_commit(cwd, base_commit_sha)
    result = _snap.record_historical_checkpoint(
        conninfo, repository_id, base_commit_sha, G,
        graphify_version=graphify_version, schema_version=schema_version,
        extraction_config_hash=extraction_config_hash,
    )
    return result["snapshot_id"], G


def _replay_branch_to_head(
    conninfo: str,
    repository_id: str,
    branch: str,
    generation: int,
    *,
    base_snapshot_id: str,
    base_commit_sha: str,
    head_commit_sha: str,
) -> nx.Graph:
    """Reconstruct a branch's current graph: its pinned base snapshot plus
    every diff row in its active generation, replayed in order."""
    import psycopg
    from graphify import age_snapshots as _snap

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT seq, generation, from_commit_sha, to_commit_sha, kind, payload "
                "FROM graphify_branch_diff WHERE repository_id = %s AND branch = %s "
                "AND generation = %s ORDER BY seq ASC;",
                (repository_id, branch, generation),
            )
            diff_rows = [
                (seq, gen, frm, to, kind, (json.loads(p) if isinstance(p, str) else p))
                for seq, gen, frm, to, kind, p in cur.fetchall()
            ]
    finally:
        conn.close()

    base_graph, _base_commit = _snap.snapshot_graph_by_id(conninfo, repository_id, base_snapshot_id)
    if base_graph is None:
        raise RuntimeError(
            f"branch {branch!r}'s base_snapshot_id {base_snapshot_id!r} could not be reconstructed"
        )
    base_payload = _snap.graph_to_payload(base_graph)
    payload = replay_branch_diffs(
        base_payload, diff_rows, base_commit_sha=base_commit_sha, head_commit_sha=head_commit_sha,
    )
    return _snap.payload_to_graph(payload)


def _insert_diff_rows(cur, repository_id, branch, generation, from_sha, to_sha, rows, start_seq):
    for i, (kind, payload) in enumerate(rows):
        cur.execute(
            "INSERT INTO graphify_branch_diff "
            "(repository_id, branch, generation, seq, from_commit_sha, to_commit_sha, kind, payload) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (repository_id, branch, generation, seq) DO NOTHING;",
            (repository_id, branch, generation, start_seq + i, from_sha, to_sha, kind, json.dumps(payload)),
        )


def _drop_age_graph_if_exists(conn, graph_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
        cur.execute("SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (graph_name,))
        if cur.fetchone()[0]:
            cur.execute("SELECT drop_graph(%s, true);", (graph_name,))


def _insert_branch_first_push(
    conninfo, repository_id, branch, base_commit_sha, head_commit_sha,
    base_snapshot_id, generation, rows, *, pushed_by=None,
) -> None:
    import psycopg
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO graphify_branches "
                "(repository_id, branch, base_commit_sha, head_commit_sha, base_snapshot_id, "
                " materialized, last_push_hash, pushed_by, pushed_at) "
                "VALUES (%s, %s, %s, %s, %s, false, %s, %s, now()) "
                "ON CONFLICT (repository_id, branch) DO UPDATE SET "
                "  base_commit_sha = EXCLUDED.base_commit_sha, "
                "  head_commit_sha = EXCLUDED.head_commit_sha, "
                "  base_snapshot_id = EXCLUDED.base_snapshot_id, "
                "  last_push_hash = EXCLUDED.last_push_hash, "
                "  pushed_by = COALESCE(EXCLUDED.pushed_by, graphify_branches.pushed_by), "
                "  pushed_at = now();",
                (repository_id, branch, base_commit_sha, head_commit_sha, base_snapshot_id,
                 head_commit_sha, pushed_by),
            )
            cur.execute(
                "INSERT INTO graphify_branch_revisions "
                "(repository_id, branch, generation, base_commit_sha, head_commit_sha, active) "
                "VALUES (%s, %s, %s, %s, %s, true) "
                "ON CONFLICT (repository_id, branch, generation) DO NOTHING;",
                (repository_id, branch, generation, base_commit_sha, head_commit_sha),
            )
            _insert_diff_rows(
                cur, repository_id, branch, generation,
                base_commit_sha, head_commit_sha, rows, start_seq=1,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _append_branch_push(
    conninfo, repository_id, branch, generation, from_sha, to_sha, rows,
    *, G=None, diff=None, age_graph_name=None, pushed_by=None,
) -> None:
    """Append this push's diff rows and, when the branch is already
    materialized, apply the same diff to its live AGE graph -- all in one
    transaction, so the registry can never claim a head commit the AGE
    graph doesn't actually contain (docs/AGE_PLAN.md Phase 4)."""
    import psycopg
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM graphify_branch_diff "
                "WHERE repository_id = %s AND branch = %s AND generation = %s;",
                (repository_id, branch, generation),
            )
            (max_seq,) = cur.fetchone()
            _insert_diff_rows(cur, repository_id, branch, generation, from_sha, to_sha, rows, start_seq=max_seq + 1)
            cur.execute(
                "UPDATE graphify_branches SET head_commit_sha = %s, last_push_hash = %s, "
                "pushed_by = COALESCE(%s, pushed_by), pushed_at = now() "
                "WHERE repository_id = %s AND branch = %s;",
                (to_sha, to_sha, pushed_by, repository_id, branch),
            )
            cur.execute(
                "UPDATE graphify_branch_revisions SET head_commit_sha = %s "
                "WHERE repository_id = %s AND branch = %s AND generation = %s;",
                (to_sha, repository_id, branch, generation),
            )

        if age_graph_name is not None:
            from graphify.exporters.graphdb import push_to_age
            push_to_age(G, conninfo=conninfo, graph_name=age_graph_name, diff=diff, conn=conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _insert_branch_new_generation(
    conninfo, repository_id, branch, new_base_commit_sha, head_commit_sha,
    new_base_snapshot_id, old_generation, new_generation, rows, *, pushed_by=None,
) -> None:
    """Supersede the active generation (marked inactive, never deleted --
    history stays auditable) and start a fresh diff chain from a newly
    resolved base, for a detected force-push/rebase."""
    import psycopg
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE graphify_branch_revisions SET active = false "
                "WHERE repository_id = %s AND branch = %s AND generation = %s;",
                (repository_id, branch, old_generation),
            )
            cur.execute(
                "INSERT INTO graphify_branch_revisions "
                "(repository_id, branch, generation, base_commit_sha, head_commit_sha, active) "
                "VALUES (%s, %s, %s, %s, %s, true);",
                (repository_id, branch, new_generation, new_base_commit_sha, head_commit_sha),
            )
            cur.execute(
                "UPDATE graphify_branches SET base_commit_sha = %s, head_commit_sha = %s, "
                "base_snapshot_id = %s, materialized = false, age_graph_name = NULL, "
                "last_push_hash = %s, pushed_by = COALESCE(%s, pushed_by), pushed_at = now() "
                "WHERE repository_id = %s AND branch = %s;",
                (new_base_commit_sha, head_commit_sha, new_base_snapshot_id, head_commit_sha,
                 pushed_by, repository_id, branch),
            )
            _insert_diff_rows(
                cur, repository_id, branch, new_generation,
                new_base_commit_sha, head_commit_sha, rows, start_seq=1,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def push_branch(
    conninfo: str,
    repository_id: str,
    branch: str,
    G: nx.Graph,
    *,
    cwd: Path | str | None = None,
    default_branch: str | None = None,
    graphify_version: str | None,
    schema_version: str | None,
    extraction_config_hash: str | None = None,
) -> dict:
    """Push a non-default branch's graph as a commit-anchored diff chain
    (docs/AGE_PLAN.md Phase 4) -- never a full AGE graph up front. Only
    touches AGE when the branch is already materialized (a prior
    materialize_branch() call), in which case the diff is applied to the
    live branch graph atomically with this push's registry bookkeeping.

    Detects a force-push/rebase (the previous head is no longer an
    ancestor of the new head) and starts a fresh generation from a newly
    resolved merge-base rather than corrupting the existing diff chain;
    the old generation is marked inactive, not deleted.
    """
    import psycopg
    from graphify import age_registry as _reg
    from graphify.analyze import graph_diff

    _reg.ensure_schema(conninfo)
    head_commit_sha = _reg.current_commit_sha(cwd)
    if head_commit_sha is None:
        raise ValueError("could not resolve the current git commit SHA to push this branch")
    pushed_by = _reg.git_user_email(cwd)

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT base_commit_sha, head_commit_sha, base_snapshot_id, "
                "materialized, age_graph_name FROM graphify_branches "
                "WHERE repository_id = %s AND branch = %s;",
                (repository_id, branch),
            )
            branch_row = cur.fetchone()
            revision_row = None
            if branch_row is not None:
                cur.execute(
                    "SELECT generation FROM graphify_branch_revisions "
                    "WHERE repository_id = %s AND branch = %s AND active;",
                    (repository_id, branch),
                )
                revision_row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    if branch_row is None or revision_row is None:
        base_commit_sha = (
            merge_base(cwd, default_branch, head_commit_sha) if default_branch else None
        ) or head_commit_sha
        base_snapshot_id, base_graph = ensure_base_snapshot(
            conninfo, repository_id, base_commit_sha, cwd=cwd,
            graphify_version=graphify_version, schema_version=schema_version,
            extraction_config_hash=extraction_config_hash,
        )
        diff = graph_diff(base_graph, G)
        rows = diff_to_rows(diff)
        _insert_branch_first_push(
            conninfo, repository_id, branch, base_commit_sha, head_commit_sha,
            base_snapshot_id, 1, rows, pushed_by=pushed_by,
        )
        return {
            "kind": "initial", "generation": 1, "rows": len(rows),
            "base_commit_sha": base_commit_sha, "head_commit_sha": head_commit_sha,
        }

    old_base_commit_sha, old_head_commit_sha, base_snapshot_id, materialized, age_graph_name = branch_row
    (old_generation,) = revision_row

    if old_head_commit_sha == head_commit_sha:
        return {
            "kind": "noop", "generation": old_generation, "rows": 0,
            "base_commit_sha": old_base_commit_sha, "head_commit_sha": head_commit_sha,
        }

    if not detect_rebase(cwd, old_head_commit_sha, head_commit_sha):
        old_graph = _replay_branch_to_head(
            conninfo, repository_id, branch, old_generation,
            base_snapshot_id=base_snapshot_id, base_commit_sha=old_base_commit_sha,
            head_commit_sha=old_head_commit_sha,
        )
        diff = graph_diff(old_graph, G)
        rows = diff_to_rows(diff)
        _append_branch_push(
            conninfo, repository_id, branch, old_generation,
            old_head_commit_sha, head_commit_sha, rows,
            G=G, diff=diff,
            age_graph_name=age_graph_name if materialized else None,
            pushed_by=pushed_by,
        )
        return {
            "kind": "incremental", "generation": old_generation, "rows": len(rows),
            "base_commit_sha": old_base_commit_sha, "head_commit_sha": head_commit_sha,
        }

    # Force-push/rebase: the branch's existing materialized graph (if any)
    # reflects the superseded generation's history and would collide with
    # create_graph() on the next materialize, so it's dropped now.
    if materialized and age_graph_name:
        conn = psycopg.connect(conninfo)
        try:
            _drop_age_graph_if_exists(conn, age_graph_name)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    new_base_commit_sha = (
        merge_base(cwd, default_branch, head_commit_sha) if default_branch else None
    ) or head_commit_sha
    new_base_snapshot_id, new_base_graph = ensure_base_snapshot(
        conninfo, repository_id, new_base_commit_sha, cwd=cwd,
        graphify_version=graphify_version, schema_version=schema_version,
        extraction_config_hash=extraction_config_hash,
    )
    diff = graph_diff(new_base_graph, G)
    new_generation = old_generation + 1
    rows = diff_to_rows(diff)
    _insert_branch_new_generation(
        conninfo, repository_id, branch, new_base_commit_sha, head_commit_sha,
        new_base_snapshot_id, old_generation, new_generation, rows, pushed_by=pushed_by,
    )
    return {
        "kind": "rebased", "generation": new_generation, "rows": len(rows),
        "base_commit_sha": new_base_commit_sha, "head_commit_sha": head_commit_sha,
    }


def materialize_branch(conninfo: str, repository_id: str, branch: str, *, default_graph_name: str) -> dict:
    """Materialize a branch's AGE graph on demand (docs/AGE_PLAN.md Phase
    4): create the graph, rehydrate it via a full push_to_age() from the
    replayed base-snapshot-plus-diff-chain graph, and record the result --
    all serialized by a PostgreSQL advisory lock keyed on
    (repository_id, branch), so two concurrent callers do one hydration,
    not two (the second simply finds `already_materialized=True` once the
    lock is released).
    """
    import psycopg
    from graphify import age_snapshots as _snap
    from graphify.exporters.graphdb import push_to_age

    lock_key = _advisory_lock_key(repository_id, branch)
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s);", (lock_key,))
        conn.commit()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT base_commit_sha, head_commit_sha, base_snapshot_id, "
                    "materialized, age_graph_name FROM graphify_branches "
                    "WHERE repository_id = %s AND branch = %s;",
                    (repository_id, branch),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"branch {branch!r} has no recorded push for this repository")
                base_commit_sha, head_commit_sha, base_snapshot_id, materialized, age_graph_name = row
                if materialized and age_graph_name:
                    return {"age_graph_name": age_graph_name, "already_materialized": True}

                cur.execute(
                    "SELECT generation FROM graphify_branch_revisions "
                    "WHERE repository_id = %s AND branch = %s AND active;",
                    (repository_id, branch),
                )
                generation_row = cur.fetchone()
                if generation_row is None:
                    raise ValueError(f"branch {branch!r} has no active revision generation")
                (generation,) = generation_row

            G = _replay_branch_to_head(
                conninfo, repository_id, branch, generation,
                base_snapshot_id=base_snapshot_id, base_commit_sha=base_commit_sha,
                head_commit_sha=head_commit_sha,
            )

            branch_graph_name = sanitize_branch_graph_name(default_graph_name, branch)
            result = push_to_age(G, conninfo=conninfo, graph_name=branch_graph_name, conn=conn)

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE graphify_branches SET materialized = true, age_graph_name = %s "
                    "WHERE repository_id = %s AND branch = %s;",
                    (branch_graph_name, repository_id, branch),
                )
            conn.commit()
            return {
                "age_graph_name": branch_graph_name, "already_materialized": False,
                "nodes": result["nodes"], "edges": result["edges"],
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", (lock_key,))
            conn.commit()
    finally:
        conn.close()


def reap_branch(
    conninfo: str, repository_id: str, branch: str, *, min_idle_seconds: int = 7 * 24 * 3600
) -> dict:
    """Drop a materialized branch's AGE graph once it's gone idle for at
    least `min_idle_seconds` (default: 7 days -- a generous grace period,
    docs/AGE_PLAN.md Phase 4). The diff chain and snapshots are never
    touched, so a reaped branch can always be re-materialized later.
    Serialized by the same advisory lock materialize_branch() uses, so a
    reap can never race an in-flight materialization.
    """
    import psycopg

    lock_key = _advisory_lock_key(repository_id, branch)
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s);", (lock_key,))
        conn.commit()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT materialized, age_graph_name, "
                    "EXTRACT(EPOCH FROM (now() - pushed_at))::bigint "
                    "FROM graphify_branches WHERE repository_id = %s AND branch = %s;",
                    (repository_id, branch),
                )
                row = cur.fetchone()
            if row is None:
                return {"reaped": False, "reason": "branch not found"}
            materialized, age_graph_name, idle_seconds = row
            if not materialized or not age_graph_name:
                return {"reaped": False, "reason": "not materialized"}
            if idle_seconds is None or idle_seconds < min_idle_seconds:
                return {"reaped": False, "reason": "not idle long enough", "idle_seconds": idle_seconds}

            _drop_age_graph_if_exists(conn, age_graph_name)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE graphify_branches SET materialized = false, age_graph_name = NULL, "
                    "bytes_used = NULL WHERE repository_id = %s AND branch = %s;",
                    (repository_id, branch),
                )
            conn.commit()
            return {"reaped": True, "age_graph_name": age_graph_name}
        except Exception:
            conn.rollback()
            raise
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", (lock_key,))
            conn.commit()
    finally:
        conn.close()
