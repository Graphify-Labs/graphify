"""graphdb — direct push of a graphify graph into Neo4j / FalkorDB.

The FalkorDB writer batches its writes and keys every node on a shared
``:Entity`` label indexed on ``id``, plus the node's file-type label for
display (``:Entity:Python``). That buys two things the previous per-row writer
did not have:

  - edge-endpoint MATCHes resolve through an index instead of scanning every
    node in the graph once per edge (#2258);
  - writes go out as batched ``UNWIND`` statements rather than one round trip
    per node and one per edge.

Convergence (#3057). By default a push only adds and updates, so anything the
source has since pruned survives in the target forever and the two silently
diverge — a `global add` that prunes a repo, followed by any number of full
re-pushes, never removes those nodes. ``prune=True`` makes the push *converge*:
every node and edge this push did not write is deleted, so the target ends up
an exact mirror of the source. Edges need their own sweep, not just the nodes:
``DETACH DELETE`` takes a pruned node's edges with it, but an edge dropped
between two endpoints that both survive would otherwise linger forever.

Because pruning is destructive it is opt-in, and it refuses to run when the
deletion would exceed ``shrink_limit`` of the target unless
``allow_shrink=True`` — the same "refuse to SILENTLY drop nodes" rule as the
#479 build guard.

Pruning deletes by *absence from this push*, not by repo. Point a push at a
graph holding anything you did not push and ``prune=True`` will remove it; use
``graph_name`` to give each source its own target graph.

The Neo4j writer is unchanged. It has the same per-row and unindexed-MATCH
problems, but a fix cannot be verified without a Neo4j instance, so it keeps
its old add-only behaviour and the new options are refused rather than
silently ignored on that path.
"""
from __future__ import annotations

import networkx as nx
import re
import time

from graphify.analyze import _node_community_map

# Rows per UNWIND batch.
_BATCH = 1000
# Rows deleted per convergence page.
_DELETE_PAGE = 10_000
# Refuse a prune that would delete more than this fraction of the target.
_DEFAULT_SHRINK_LIMIT = 0.20
# Stamped on every node and edge a push writes; convergence deletes whatever
# does not carry the current value.
_EPOCH_PROP = "graphify_push_epoch"


def _safe_rel(relation: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"


def _safe_label(label: str) -> str:
    """Sanitize a node label to prevent Cypher injection."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
    return sanitized if sanitized else "Entity"


def _scalar_props(data: dict) -> dict:
    return {
        k: v for k, v in data.items()
        if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
    }


def _new_epoch() -> int:
    """Identifier for one push. Millisecond clock, so two pushes into the same
    target never collide and the value is meaningful when read back."""
    return int(time.time() * 1000)


def _chunked(iterable, size: int):
    """Yield lists of at most `size` items, holding one chunk at a time."""
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def push_to_neo4j(
    G: nx.Graph,
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
) -> dict[str, int]:
    """Push graph directly to a running Neo4j instance via the Python driver.

    Requires: pip install neo4j

    Uses MERGE so re-running is safe - nodes and edges are upserted, not duplicated.
    Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a Neo4j node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        for node_id, data in G.nodes(data=True):
            props = {
                k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
            }
            props["id"] = node_id
            cid = node_community.get(node_id)
            if cid is not None:
                props["community"] = cid
            ftype = _safe_label(data.get("file_type", "Entity").capitalize())
            session.run(
                f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
                id=node_id,
                props=props,
            )
            nodes_pushed += 1

        for u, v, data in G.edges(data=True):
            rel = _safe_rel(data.get("relation", "RELATED_TO"))
            props = {
                k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
            }
            session.run(
                f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=u,
                tgt=v,
                props=props,
            )
            edges_pushed += 1

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}


# ---------------------------------------------------------------------------
# FalkorDB batched writer
# ---------------------------------------------------------------------------

def _ensure_schema(graph) -> None:
    """Index the shared label, and adopt nodes written before it existed.

    A graph pushed by an older graphify carries only its file-type label, so
    MERGE on :Entity would create a duplicate beside every one of them. The
    backfill is idempotent and a no-op on a graph this writer already owns.
    """
    try:
        graph.query("CREATE INDEX FOR (n:Entity) ON (n.id)")
    except Exception:
        pass  # already exists, or an engine without the syntax — push still works
    graph.query("MATCH (n) WHERE n.id IS NOT NULL AND NOT n:Entity SET n:Entity")


def _write_nodes(graph, rows, node_community: dict, epoch: int) -> int:
    """Batched node upsert. `rows` yields (node_id, attrs)."""
    pushed = 0
    for chunk in _chunked(rows, _BATCH):
        by_label: dict[str, list[dict]] = {}
        for node_id, data in chunk:
            props = _scalar_props(data)
            props["id"] = node_id
            cid = node_community.get(node_id)
            if cid is not None:
                props["community"] = cid
            props[_EPOCH_PROP] = epoch
            ftype = _safe_label(str(data.get("file_type", "Entity")).capitalize())
            by_label.setdefault(ftype, []).append(props)
        for ftype, batch in by_label.items():
            graph.query(
                f"UNWIND $rows AS row MERGE (n:Entity {{id: row.id}}) "
                f"SET n:{ftype} SET n += row",
                {"rows": batch},
            )
            pushed += len(batch)
    return pushed


def _write_edges(graph, rows, epoch: int) -> int:
    """Batched edge upsert. `rows` yields (u, v, attrs)."""
    pushed = 0
    for chunk in _chunked(rows, _BATCH):
        by_rel: dict[str, list[dict]] = {}
        for u, v, data in chunk:
            rel = _safe_rel(data.get("relation", "RELATED_TO"))
            props = _scalar_props(data)
            props[_EPOCH_PROP] = epoch
            by_rel.setdefault(rel, []).append({"src": u, "tgt": v, "props": props})
        for rel, batch in by_rel.items():
            graph.query(
                f"UNWIND $rows AS row "
                f"MATCH (a:Entity {{id: row.src}}), (b:Entity {{id: row.tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += row.props",
                {"rows": batch},
            )
            pushed += len(batch)
    return pushed


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

_STALE_NODES = f"MATCH (n:Entity) WHERE n.{_EPOCH_PROP} IS NULL OR n.{_EPOCH_PROP} <> $epoch"
_STALE_EDGES = (
    f"MATCH (:Entity)-[r]->(:Entity) "
    f"WHERE r.{_EPOCH_PROP} IS NULL OR r.{_EPOCH_PROP} <> $epoch"
)


def _count(graph, cypher: str, params: dict) -> int:
    return int(graph.query(cypher, params).result_set[0][0])


def _delete_paged(graph, stale_match: str, var: str, params: dict, expected: int) -> int:
    """Delete `stale_match` in pages until none remain. Returns rows deleted.

    LIMIT does not page a DELETE in FalkorDB: its known-limitations doc notes
    LIMIT "does not currently short-circuit eager operations like CREATE, SET,
    or DELETE", so `... DELETE n LIMIT $page` deletes everything matched rather
    than one page. The LIMIT has to sit in a WITH that precedes the DELETE.
    """
    verb = "DETACH DELETE" if var == "n" else "DELETE"
    page = f"{stale_match} WITH {var} LIMIT {_DELETE_PAGE} {verb} {var}"
    remaining = expected
    while remaining > 0:
        graph.query(page, params)
        after = _count(graph, f"{stale_match} RETURN count({var})", params)
        if after >= remaining:
            raise RuntimeError(
                f"graphify: prune stalled with {after} stale rows remaining (no "
                f"progress in one page). Target may be read-only, or the delete "
                f"may be racing another writer."
            )
        remaining = after
    return expected - remaining


def _converge(graph, epoch: int, allow_shrink: bool, shrink_limit: float) -> tuple[int, int]:
    """Delete every node and edge this push did not write."""
    params = {"epoch": epoch}
    stale_n = _count(graph, f"{_STALE_NODES} RETURN count(n)", params)
    stale_e = _count(graph, f"{_STALE_EDGES} RETURN count(r)", params)
    if stale_n <= 0 and stale_e <= 0:
        return 0, 0

    total_n = _count(graph, "MATCH (n:Entity) RETURN count(n)", {})
    total_e = _count(graph, "MATCH (:Entity)-[r]->(:Entity) RETURN count(r)", {})
    if not allow_shrink:
        for kind, stale, total in (("nodes", stale_n, total_n), ("edges", stale_e, total_e)):
            if total > 0 and (stale / total) > shrink_limit:
                raise ValueError(
                    f"graphify: push --prune would delete {stale} of {total} "
                    f"{kind} ({stale / total:.0%}) from the target graph, over "
                    f"the {shrink_limit:.0%} safety limit. That usually means "
                    f"the push is aimed at the wrong graph — check --graph-name. "
                    f"Pass --allow-shrink if the removal is intended. Nothing "
                    f"was deleted; the additive part of this push has already "
                    f"been applied."
                )

    # Nodes first: DETACH DELETE takes their edges with them, so the edge sweep
    # has less to do and its count is settled by the time it runs.
    nodes_deleted = _delete_paged(graph, _STALE_NODES, "n", params, stale_n) if stale_n else 0
    remaining_e = _count(graph, f"{_STALE_EDGES} RETURN count(r)", params)
    edges_deleted = (
        _delete_paged(graph, _STALE_EDGES, "r", params, remaining_e) if remaining_e else 0
    )
    return nodes_deleted, edges_deleted


# ---------------------------------------------------------------------------
# Repo-keyed delta
#
# `global add` already treats the repo as the unit of change: it prunes a repo
# whole, re-adds it whole, records a per-repo source_hash in the global
# manifest, and returns skipped=True when that hash has not moved. The delta
# push mirrors that contract instead of inventing one, so a 226-repo global
# graph with one changed repo sends one repo's rows rather than all of them.
#
# The "what did I last push" state lives in the TARGET database, not in a local
# ledger: a ledger cannot notice that the database was wiped or that a run
# half-landed — it still reads clean and the delta never repairs the drift.
# Reading the target's own per-repo node counts and re-pushing any repo whose
# count disagrees with the manifest turns silent permanent drift into automatic
# repair.
# ---------------------------------------------------------------------------

_STATE_LABEL = "GraphifyPushState"


def _read_push_state(graph) -> dict[str, dict]:
    rows = graph.query(
        f"MATCH (s:{_STATE_LABEL}) RETURN s.repo, s.source_hash, s.node_count", {}
    ).result_set or []
    return {r[0]: {"source_hash": r[1], "node_count": int(r[2] or 0)} for r in rows if r[0]}


def _target_repo_counts(graph) -> dict[str, int]:
    """The target's OWN per-repo node counts — the check a ledger cannot do."""
    rows = graph.query(
        "MATCH (n:Entity) WHERE n.repo IS NOT NULL RETURN n.repo, count(n)", {}
    ).result_set or []
    return {r[0]: int(r[1]) for r in rows if r[0]}


def _plan_delta(manifest_repos: dict, state: dict, live_counts: dict):
    """Decide which repos to re-push and which to delete."""
    changed, reasons = [], {}
    for tag, info in manifest_repos.items():
        known = state.get(tag)
        want_count = int(info.get("node_count") or 0)
        live = live_counts.get(tag, 0)
        if known is None:
            changed.append(tag); reasons[tag] = "not present in target"
        elif known.get("source_hash") != info.get("source_hash"):
            changed.append(tag); reasons[tag] = "source changed"
        elif live != want_count:
            changed.append(tag)
            reasons[tag] = f"target drift ({live} nodes in target, manifest says {want_count})"
    removed = list(dict.fromkeys(
        [t for t in list(state) + list(live_counts) if t not in manifest_repos]
    ))
    return changed, removed, reasons


def _index_repos(G: nx.Graph, tags):
    """Bucket a global graph's nodes and edges by repo, in two passes.

    Edges are bucketed by *either* endpoint's repo, not by both. `global add`
    remaps external-library nodes onto whichever repo first contributed them,
    so a cross-repo edge B->A is owned by neither B nor A alone. Pruning repo A
    drops that edge with A's node; re-adding only A's internal edges would not
    bring it back and the target would quietly lose cross-repo connectivity on
    every delta.
    """
    wanted = set(tags)
    nodes_by: dict[str, list] = {t: [] for t in wanted}
    for nid, data in G.nodes(data=True):
        tag = data.get("repo")
        if tag in wanted:
            nodes_by[tag].append((nid, data))
    edges_by: dict[str, list] = {t: [] for t in wanted}
    for u, v, data in G.edges(data=True):
        for tag in {G.nodes[u].get("repo"), G.nodes[v].get("repo")} & wanted:
            edges_by[tag].append((u, v, data))
    return nodes_by, edges_by


def _prune_repo_paged(graph, tag: str) -> int:
    """Delete one repo's nodes, paged. Returns the count removed."""
    scoped = "MATCH (n:Entity {repo: $t})"
    params = {"t": tag}
    n = _count(graph, f"{scoped} RETURN count(n)", params)
    if n:
        _delete_paged(graph, scoped, "n", params, n)
    return n


def _push_delta(
    G, graph, node_community: dict, epoch: int, manifest_repos: dict,
    allow_shrink: bool, shrink_limit: float,
) -> dict:
    state = _read_push_state(graph)
    live_counts = _target_repo_counts(graph)
    changed, removed, reasons = _plan_delta(manifest_repos, state, live_counts)

    # Size guard, before anything is deleted: a manifest that does not belong to
    # this database looks exactly like a genuine mass removal. Same rule as the
    # #479 build guard, applied to the push.
    #
    # Only NET removal counts. A re-pushed repo is pruned and immediately
    # re-added, so its nodes are not lost — charging them here would refuse any
    # delta touching more than shrink_limit of a small global graph. A repo that
    # comes back SMALLER is a partial removal, so charge the difference: that is
    # what catches "the manifest says 2 nodes, the target holds 50,000".
    total_nodes = _count(graph, "MATCH (n:Entity) RETURN count(n)", {})
    doomed = sum(live_counts.get(t, 0) for t in removed)
    doomed += sum(
        max(0, live_counts.get(t, 0) - int(manifest_repos.get(t, {}).get("node_count") or 0))
        for t in changed
    )
    if not allow_shrink and total_nodes > 0 and (doomed / total_nodes) > shrink_limit:
        raise ValueError(
            f"graphify: delta push would remove {doomed} of {total_nodes} nodes "
            f"({doomed / total_nodes:.0%}) in the target graph, over the "
            f"{shrink_limit:.0%} safety limit. That usually means this manifest "
            f"does not belong to this database — check --graph-name. Pass "
            f"--allow-shrink if it is intended. Nothing was changed."
        )

    nodes_by, edges_by = _index_repos(G, changed) if changed else ({}, {})

    nodes_pushed = edges_pushed = deleted = 0
    for tag in changed:
        deleted += _prune_repo_paged(graph, tag)
        nodes_pushed += _write_nodes(graph, nodes_by.get(tag, []), node_community, epoch)
        edges_pushed += _write_edges(graph, edges_by.get(tag, []), epoch)
        info = manifest_repos.get(tag, {})
        graph.query(
            f"MERGE (s:{_STATE_LABEL} {{repo: $repo}}) "
            f"SET s.source_hash = $h, s.node_count = $n, s.epoch = $e",
            {"repo": tag, "h": info.get("source_hash"),
             "n": int(info.get("node_count") or 0), "e": epoch},
        )

    for tag in removed:
        deleted += _prune_repo_paged(graph, tag)
        graph.query(f"MATCH (s:{_STATE_LABEL} {{repo: $repo}}) DELETE s", {"repo": tag})

    return {
        "nodes": nodes_pushed,
        "edges": edges_pushed,
        "deleted": deleted,
        "deleted_edges": 0,  # repo prune is DETACH DELETE; edges go with the nodes
        "repos_pushed": changed,
        "repos_removed": removed,
        "repos_skipped": [t for t in manifest_repos if t not in changed],
        "reasons": reasons,
    }


def push_to_falkordb(
    G: nx.Graph,
    uri: str,
    user: str | None = None,
    password: str | None = None,
    communities: dict[int, list[str]] | None = None,
    graph_name: str = "graphify",
    prune: bool = False,
    allow_shrink: bool = False,
    shrink_limit: float = _DEFAULT_SHRINK_LIMIT,
    repo_manifest: dict | None = None,
) -> dict[str, int]:
    """Push graph directly to a running FalkorDB instance via the Python SDK.

    Requires: pip install falkordb

    FalkorDB is OpenCypher-compatible. Differences from the Neo4j path:
      - connects with FalkorDB(host, port, username, password) instead of a bolt
        driver; only the host/port are read from the URI, so the scheme is
        informational - "falkordb://localhost:6379", "redis://localhost:6379"
        and a bare "localhost:6379" are all equivalent (default port 6379).
      - a named graph is selected via db.select_graph(graph_name) (default
        "graphify"); FalkorDB keys each graph by name in the same instance.
      - queries run via graph.query(cypher, params) - there is no session object.
      - auth is optional (FalkorDB runs without credentials by default), so user
        and password may be None.
      - no APOC: the Neo4j path does not use APOC either, so nothing to port.

    Writes are batched UNWIND upserts against an indexed ``:Entity`` label, so
    re-running is safe - nodes and edges are upserted, not duplicated.

    graph_name: which named graph in the instance to write. FalkorDB keys each
        graph by name, so this is the difference between a staging graph and
        production - set it explicitly for anything that matters.
    prune: delete nodes and edges this push did not write, so the target
        converges on the source instead of accumulating. See the module
        docstring.
    repo_manifest: the global manifest's ``repos`` dict. Switches the push into
        repo-keyed DELTA mode - only repos whose ``source_hash`` moved (or whose
        node count in the target has drifted from the manifest) are re-sent, and
        repos the manifest no longer lists are deleted. Convergence is implied,
        so ``prune`` is not needed with it.

    Returns a dict with counts of nodes and edges pushed, nodes and edges
    deleted, and in delta mode the repos re-pushed / skipped / removed.
    """
    try:
        from falkordb import FalkorDB
    except ImportError as e:
        raise ImportError(
            "falkordb SDK not installed. Run: pip install falkordb"
        ) from e

    from urllib.parse import urlparse

    node_community = _node_community_map(communities) if communities else {}
    epoch = _new_epoch()

    parsed = urlparse(uri if "://" in uri else f"redis://{uri}")
    # FalkorDB auth is optional. Only send credentials when a password is
    # provided; otherwise connect anonymously and ignore any bolt-style default
    # username (e.g. Neo4j's "neo4j"), which FalkorDB rejects as an unknown ACL
    # user. Credentials embedded in the URI take precedence over the args.
    connect_user = parsed.username or (user if password else None)
    connect_password = parsed.password or (password or None)
    db = FalkorDB(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=connect_user,
        password=connect_password,
    )
    graph = db.select_graph(graph_name)
    _ensure_schema(graph)

    if repo_manifest is not None:
        return _push_delta(
            G, graph, node_community, epoch, repo_manifest, allow_shrink, shrink_limit
        )

    nodes_pushed = _write_nodes(graph, G.nodes(data=True), node_community, epoch)
    edges_pushed = _write_edges(graph, G.edges(data=True), epoch)

    deleted = deleted_edges = 0
    surplus = 0
    if prune:
        deleted, deleted_edges = _converge(graph, epoch, allow_shrink, shrink_limit)
    else:
        # An add-only push cannot converge, and #3057's whole point is that the
        # divergence is SILENT. Report it: the same "not stamped by this push"
        # count the prune path would delete tells the caller exactly how far the
        # target has drifted, so a one-line notice can replace the silence.
        surplus = _count(graph, f"{_STALE_NODES} RETURN count(n)", {"epoch": epoch})

    return {
        "nodes": nodes_pushed,
        "edges": edges_pushed,
        "deleted": deleted,
        "deleted_edges": deleted_edges,
        "target_surplus": surplus,
    }
