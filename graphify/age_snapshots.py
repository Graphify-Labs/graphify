"""Logical base snapshots for the durable default-branch graph
(docs/AGE_PLAN.md Phase 3): periodic full checkpoints plus ordered,
reversible deltas in ``graphify_snapshots`` (plain PostgreSQL, created by
``age_registry.ensure_schema()`` in Phase 2).

This is the immutable base the branch machinery (Phase 4) will pin against
-- it is not an AGE graph copy, and reconstructing it never touches AGE.
Reconstruction/diff-application logic is pure and DB-free (tier-1
testable); only the read/write of ``graphify_snapshots`` rows needs a live
Postgres connection.
"""
from __future__ import annotations

import json
import uuid

import networkx as nx

# Every Nth push (0-indexed count of existing snapshot rows) is stored as a
# full checkpoint; the rest are deltas against the reconstructed prior
# state. Simple and predictable rather than size-based (docs/AGE_PLAN.md
# Open questions) -- revisit if checkpoint payloads turn out to dominate
# storage for very large graphs.
CHECKPOINT_CADENCE = 20


def _scalar_props(data: dict) -> dict:
    return {
        k: v for k, v in data.items()
        if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
    }


def graph_to_payload(G: nx.Graph) -> dict:
    """Full-fidelity, JSON-serializable snapshot of a graph: every scalar
    node/edge property, not just the lean AGE-pushed subset -- this is the
    logical base graphify_snapshots reconstructs from, independent of
    whatever ``--full-props``/lean choice a given AGE push made."""
    nodes = [{"id": n, **_scalar_props(data)} for n, data in G.nodes(data=True)]
    edges = [
        {"source": u, "target": v, **_scalar_props(data)}
        for u, v, data in G.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


def payload_to_graph(payload: dict) -> nx.Graph:
    """Inverse of graph_to_payload(). Always undirected, matching build()'s
    default graph type (the only type graphify actually pushes to AGE)."""
    G = nx.Graph()
    for node in payload.get("nodes", []):
        node = dict(node)
        node_id = node.pop("id")
        G.add_node(node_id, **node)
    for edge in payload.get("edges", []):
        edge = dict(edge)
        source = edge.pop("source")
        target = edge.pop("target")
        G.add_edge(source, target, **edge)
    return G


def apply_diff_to_payload(payload: dict, diff: dict) -> dict:
    """Apply a graph_diff()-shaped dict (as stored in a 'delta' snapshot
    row) to a payload, producing the payload for the diff's "new" side.

    Pure and DB-free. Order of operations per id/edge-key: removal, then
    add, then change -- a given id only ever appears in one of the three
    node buckets (and likewise for edges) for a single diff, so order
    between buckets doesn't actually matter, but removal-before-add avoids
    ever transiently dropping a row that was both removed and re-added by
    a rebuild in between snapshots.
    """
    nodes = {n["id"]: dict(n) for n in payload.get("nodes", [])}
    for n in diff.get("removed_nodes", []):
        nodes.pop(n["id"], None)
    for n in diff.get("new_nodes", []):
        nodes[n["id"]] = {"id": n["id"], **n.get("properties", {})}
    for n in diff.get("changed_nodes", []):
        nodes[n["id"]] = {"id": n["id"], **n.get("new", {})}

    def _edge_key(e: dict) -> tuple:
        return (e["source"], e["target"], e.get("relation", ""))

    edges = {_edge_key(e): dict(e) for e in payload.get("edges", [])}
    for e in diff.get("removed_edges", []):
        edges.pop(_edge_key(e), None)
    for e in diff.get("new_edges", []):
        edges[_edge_key(e)] = {
            "source": e["source"], "target": e["target"], **e.get("properties", {})
        }
    for e in diff.get("changed_edges", []):
        edges[_edge_key(e)] = {
            "source": e["source"], "target": e["target"],
            "relation": e.get("relation", ""), **e.get("new", {}),
        }

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def _reconstruct_payload_from_rows(
    rows: list[tuple],
) -> tuple[dict | None, str | None, str | None]:
    """Replay ordered ``(snapshot_id, commit_sha, kind, payload)`` rows
    (oldest first) into the latest full payload.

    Checkpoint-preferred resolution: walks backward to the most recent
    'checkpoint' row and starts from its payload directly rather than
    replaying deltas through it, since a checkpoint is always a complete,
    authoritative restatement of state as of its commit_sha (this is what
    lets a checkpoint and a delta coexist for the same commit_sha, per the
    graphify_snapshots uniqueness constraint). Rows before that checkpoint
    are never touched. Returns (None, None, None) for no rows at all.

    Pure and DB-free (tier-1 testable) -- the only DB-dependent part is
    fetching `rows` in the first place.
    """
    if not rows:
        return None, None, None

    last_checkpoint_idx = None
    for i in range(len(rows) - 1, -1, -1):
        if rows[i][2] == "checkpoint":
            last_checkpoint_idx = i
            break

    if last_checkpoint_idx is None:
        payload: dict = {"nodes": [], "edges": []}
        start_idx = 0
        last_commit_sha = None
        last_snapshot_id = None
    else:
        raw = rows[last_checkpoint_idx][3]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        start_idx = last_checkpoint_idx + 1
        last_commit_sha = rows[last_checkpoint_idx][1]
        last_snapshot_id = rows[last_checkpoint_idx][0]

    for i in range(start_idx, len(rows)):
        snap_id, commit_sha, kind, raw_payload = rows[i]
        parsed = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        if kind == "checkpoint":
            payload = parsed
        else:
            payload = apply_diff_to_payload(payload, parsed)
        last_commit_sha = commit_sha
        last_snapshot_id = snap_id

    return payload, last_commit_sha, last_snapshot_id


def _reconstruct_payload_up_to(
    rows: list[tuple], target_snapshot_id: str
) -> tuple[dict | None, str | None, str | None]:
    """Like _reconstruct_payload_from_rows, but truncated to (and
    including) a specific snapshot row -- reconstructs "state as of this
    snapshot" rather than "latest state". Returns (None, None, None) if
    `target_snapshot_id` isn't among `rows`. Pure, DB-free."""
    idx = next((i for i, r in enumerate(rows) if r[0] == target_snapshot_id), None)
    if idx is None:
        return None, None, None
    return _reconstruct_payload_from_rows(rows[: idx + 1])


def _diff_payloads(old_payload: dict, new_payload: dict) -> dict:
    from graphify.analyze import graph_diff
    return graph_diff(payload_to_graph(old_payload), payload_to_graph(new_payload))


def latest_snapshot_graph(
    conninfo: str, repository_id: str
) -> tuple[nx.Graph | None, str | None]:
    """Reconstruct the most recently recorded snapshot for a repository as
    an nx.Graph, for diffing the next push against.

    Returns (None, None) when nothing has been recorded yet, or when the
    registry schema doesn't exist at all -- like
    age_registry.resolve_age_graph_name(), a read-only discovery call has
    no business creating tables as a side effect.
    """
    import psycopg

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
                return None, None
        payload, commit_sha, _snapshot_id = _reconstruct_payload_from_rows(rows)
        if payload is None:
            return None, None
        return payload_to_graph(payload), commit_sha
    finally:
        conn.close()


def snapshot_graph_by_id(
    conninfo: str, repository_id: str, snapshot_id: str
) -> tuple[nx.Graph | None, str | None]:
    """Reconstruct the graph as of a *specific* recorded snapshot (not
    necessarily the latest) -- used to resolve a branch's pinned
    `base_snapshot_id` (docs/AGE_PLAN.md Phase 4).

    Returns (None, None) if `snapshot_id` doesn't belong to this
    repository's recorded snapshots, or if the registry schema doesn't
    exist at all yet.
    """
    import psycopg

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
                return None, None
        payload, commit_sha, _snap_id = _reconstruct_payload_up_to(rows, snapshot_id)
        if payload is None:
            return None, None
        return payload_to_graph(payload), commit_sha
    finally:
        conn.close()


def record_historical_checkpoint(
    conninfo: str,
    repository_id: str,
    commit_sha: str,
    G: nx.Graph,
    *,
    graphify_version: str | None,
    schema_version: str | None,
    extraction_config_hash: str | None = None,
) -> dict:
    """Record a *historical* checkpoint reconstructed out-of-band (e.g. via
    a git-worktree extraction, docs/AGE_PLAN.md Phase 4's missing-base-
    snapshot fallback) for a commit older than anything currently
    retained.

    Unlike record_snapshot(), this backdates `created_at` to just before
    the repository's earliest existing snapshot row (or `now()` if there
    are none) instead of using the insert-time default. Reconstruction
    (_reconstruct_payload_from_rows) walks rows in `created_at` order and
    assumes that tracks git history order; inserting this row with a
    normal `now()` timestamp would make it look like the *newest* state
    (since it's created after everything else) when it actually represents
    the *oldest* recorded commit -- silently corrupting every later
    default-branch reconstruction. Always stored as a checkpoint: it's a
    full graph, not a diff against anything retained.
    """
    import psycopg
    from graphify import age_registry as _reg

    _reg.ensure_schema(conninfo)
    payload = graph_to_payload(G)
    snapshot_id = str(uuid.uuid4())

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO graphify_snapshots "
                "(snapshot_id, repository_id, commit_sha, kind, payload, "
                " graphify_version, schema_version, extraction_config_hash, created_at) "
                "SELECT %s, %s, %s, 'checkpoint', %s, %s, %s, %s, "
                "       COALESCE((SELECT MIN(created_at) FROM graphify_snapshots "
                "                 WHERE repository_id = %s), now()) - interval '1 microsecond' "
                "ON CONFLICT (repository_id, commit_sha, kind, schema_version, "
                "             extraction_config_hash, graphify_version) DO NOTHING "
                "RETURNING snapshot_id;",
                (snapshot_id, repository_id, commit_sha, json.dumps(payload),
                 graphify_version, schema_version, extraction_config_hash, repository_id),
            )
            row = cur.fetchone()
            if row is None:
                # Already recorded under this exact key -- look it up.
                cur.execute(
                    "SELECT snapshot_id FROM graphify_snapshots WHERE "
                    "repository_id = %s AND commit_sha = %s AND kind = 'checkpoint' "
                    "AND schema_version IS NOT DISTINCT FROM %s "
                    "AND extraction_config_hash IS NOT DISTINCT FROM %s "
                    "AND graphify_version IS NOT DISTINCT FROM %s;",
                    (repository_id, commit_sha, schema_version,
                     extraction_config_hash, graphify_version),
                )
                row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"kind": "checkpoint", "snapshot_id": str(row[0]) if row else None}


def record_snapshot(
    conninfo: str,
    repository_id: str,
    commit_sha: str,
    G: nx.Graph,
    *,
    graphify_version: str | None,
    schema_version: str | None,
    extraction_config_hash: str | None = None,
    cadence: int = CHECKPOINT_CADENCE,
) -> dict:
    """Record this push's state as a checkpoint (every `cadence`th push) or
    a delta against the reconstructed prior state, in one transaction.

    Idempotent by the graphify_snapshots uniqueness constraint
    (repository_id, commit_sha, kind, schema_version,
    extraction_config_hash, graphify_version): re-recording the same
    commit under the same config is a silent no-op, not a duplicate row.
    """
    import psycopg
    from graphify import age_registry as _reg

    _reg.ensure_schema(conninfo)
    new_payload = graph_to_payload(G)

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT snapshot_id, commit_sha, kind, payload FROM graphify_snapshots "
                "WHERE repository_id = %s ORDER BY created_at ASC;",
                (repository_id,),
            )
            rows = cur.fetchall()

            # True idempotency by commit_sha: the uniqueness constraint
            # alone doesn't guarantee this, since which `kind` a re-push of
            # the same commit would compute depends on how many rows exist
            # *now* (cadence is a function of push count, not commit_sha) --
            # a repeat call could otherwise insert a second, different-kind
            # row for a commit already recorded.
            for existing_id, existing_commit, existing_kind, _payload in rows:
                if existing_commit == commit_sha:
                    conn.commit()
                    return {"kind": existing_kind, "snapshot_id": str(existing_id)}

            parent_snapshot_id = rows[-1][0] if rows else None

            if len(rows) % cadence == 0:
                kind = "checkpoint"
                payload = new_payload
            else:
                kind = "delta"
                old_payload, _old_commit, _old_snap = _reconstruct_payload_from_rows(rows)
                if old_payload is None:
                    old_payload = {"nodes": [], "edges": []}
                payload = _diff_payloads(old_payload, new_payload)

            snapshot_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO graphify_snapshots "
                "(snapshot_id, repository_id, commit_sha, kind, parent_snapshot_id, "
                " payload, graphify_version, schema_version, extraction_config_hash) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (repository_id, commit_sha, kind, schema_version, "
                "             extraction_config_hash, graphify_version) DO NOTHING "
                "RETURNING snapshot_id;",
                (snapshot_id, repository_id, commit_sha, kind, parent_snapshot_id,
                 json.dumps(payload), graphify_version, schema_version, extraction_config_hash),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"kind": kind, "snapshot_id": str(row[0]) if row else None}
