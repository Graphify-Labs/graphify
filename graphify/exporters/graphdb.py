"""graphdb — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.analyze import _node_community_map
import json
import networkx as nx
import re
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    # typing.LiteralString is 3.11+ but requires-python is >=3.10, so the
    # check-time name comes from typing_extensions. It is only referenced
    # via cast("LiteralString", ...) string form, so this never runs at
    # module load.
    from typing_extensions import LiteralString


def _safe_rel(relation: str) -> str:
    """Sanitize a Cypher relationship type; shared across neo4j/falkordb/age
    so the emitted schema stays identical across exporters (docs/AGE_PLAN.md,
    "Cypher-facing schema contract")."""
    return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"


def _safe_label(label: str) -> str:
    """Sanitize a Cypher node label to prevent injection; shared across
    neo4j/falkordb/age exporters (see _safe_rel)."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
    return sanitized if sanitized else "Entity"


def _distinct_node_labels(G: nx.Graph) -> list[str]:
    """Distinct Cypher labels the node-upsert loop will write, sorted.

    The label is derived exactly as the push loops derive it, so the indexes
    created up front cover every label the MERGE statements will match against.
    """
    labels = set()
    for _, data in G.nodes(data=True):
        label = data.get("file_type", "Entity").capitalize()
        labels.add(re.sub(r"[^A-Za-z0-9_]", "", label) or "Entity")
    return sorted(labels)


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

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        # Index (label, id) before any upsert, for the same reason as the
        # FalkorDB path: MERGE matches on (label, id), so an unindexed match
        # pattern scans the whole label and the push degrades to O(n^2)
        # (#3804). IF NOT EXISTS keeps this idempotent across re-pushes.
        for label in _distinct_node_labels(G):
            try:
                session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id)")
            except Exception:
                pass

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
            # An undirected nx.Graph's own (u, v) tuple order reflects node
            # insertion order, not which side was the extracted "source" -
            # build.py stamps _src/_tgt precisely to recover that (see the
            # same idiom in analyze.py/serve.py/exporters/html.py).
            session.run(
                f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=data.get("_src", u),
                tgt=data.get("_tgt", v),
                props=props,
            )
            edges_pushed += 1

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}

def push_to_falkordb(
    G: nx.Graph,
    uri: str,
    user: str | None = None,
    password: str | None = None,
    communities: dict[int, list[str]] | None = None,
    graph_name: str = "graphify",
) -> dict[str, int]:
    """Push graph directly to a running FalkorDB instance via the Python SDK.

    Requires: pip install falkordb

    FalkorDB is OpenCypher-compatible, so the MERGE/SET upsert queries are
    identical to push_to_neo4j. Differences from the Neo4j path:
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

    Uses MERGE so re-running is safe - nodes and edges are upserted, not
    duplicated. Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from falkordb import FalkorDB
    except ImportError as e:
        raise ImportError(
            "falkordb SDK not installed. Run: pip install falkordb"
        ) from e

    from urllib.parse import urlparse

    node_community = _node_community_map(communities) if communities else {}

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
    nodes_pushed = 0
    edges_pushed = 0

    # Index (label, id) before any upsert. The MERGE below matches on
    # (label, id), so with no index FalkorDB scans every existing node carrying
    # that label to decide whether the node is new: each upsert costs
    # O(nodes with that label) and the whole push degrades to O(n^2) (#3804).
    # Measured on a 167k-node / 209k-edge graph, adding these indexes first
    # restored the throughput the push started at. FalkorDB's CREATE INDEX has
    # no IF NOT EXISTS, so a re-run against an already-indexed graph raises —
    # tolerate that rather than failing an otherwise valid push.
    for label in _distinct_node_labels(G):
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception:
            pass

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
        graph.query(
            f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
            {"id": node_id, "props": props},
        )
        nodes_pushed += 1

    for u, v, data in G.edges(data=True):
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        # See push_to_neo4j's matching comment: _src/_tgt recovers the
        # extracted direction an undirected nx.Graph's own tuple order
        # does not preserve.
        graph.query(
            f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
            f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
            {"src": data.get("_src", u), "tgt": data.get("_tgt", v), "props": props},
        )
        edges_pushed += 1

    return {"nodes": nodes_pushed, "edges": edges_pushed}


# ---------------------------------------------------------------------------
# push_to_age — Apache AGE exporter (docs/AGE_PLAN.md Phase 1).
#
# AGE's cypher() has two hard constraints, found live in the Phase 0 spike
# (tests/test_age_integration.py) and load-bearing for everything below:
#   1. The graph name must be a literal at parse time, never a bind
#      parameter.
#   2. ``SET n += <map>`` rejects a map that arrives via a parameter or via
#      UNWIND-bound data ("SET clause expects a map") -- only a literal map
#      written directly in the query text works. So, unlike the
#      neo4j/falkordb pushers above (which spread an arbitrary props dict
#      with ``SET n += $props``), push_to_age() must enumerate every
#      property it sets by name in the query text itself. This is why node
#      property selection is a fixed, pinned schema (docs/AGE_SCHEMA.md)
#      rather than "whatever scalar attributes happen to be on the node".
# ---------------------------------------------------------------------------

_AGE_LEAN_NODE_FIELDS = (
    "id", "label", "source_file", "source_location", "community",
    "degree", "is_god_node", "in_cycle",
)
_AGE_LEAN_EDGE_FIELDS = ("relation", "confidence")


def _is_age_safe_prop_key(key: str) -> bool:
    """Whether an attribute key may be emitted as a Cypher property name.

    In full_props mode discovered field names are interpolated raw into
    the Cypher text (``SET n.{key} = row.{key}``) -- sql.Literal only
    protects the row *values*, not identifiers -- so attribute names must
    be treated as untrusted (CONTRIBUTING.md: source text is untrusted).
    Only keys that are already valid Cypher identifiers are pushed; no
    sanitizing rewrite, because a rewritten name would silently collide
    with or shadow a real property.
    """
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is not None


def _age_node_field_names(G: nx.Graph, full_props: bool) -> tuple[str, ...]:
    """The fixed field list every node row will carry, in a stable order.

    Pure and DB-free (tier-1 testable): this is the "schema pin" for
    push_to_age() -- see docs/AGE_PLAN.md "Testing strategy".  In lean mode
    it is the fixed structural schema; in full mode it is the union of
    scalar attribute keys observed across all nodes (excluding private
    ``_``-prefixed keys), always including the lean fields so structural
    metrics are never dropped.
    """
    if not full_props:
        return _AGE_LEAN_NODE_FIELDS
    keys: set[str] = set(_AGE_LEAN_NODE_FIELDS)
    for _, data in G.nodes(data=True):
        for k, v in data.items():
            if (
                isinstance(v, (str, int, float, bool))
                and not k.startswith("_")
                and _is_age_safe_prop_key(k)
            ):
                keys.add(k)
    # Stable order: lean fields first (fixed position), then the rest sorted.
    rest = sorted(keys - set(_AGE_LEAN_NODE_FIELDS))
    return _AGE_LEAN_NODE_FIELDS + tuple(rest)


def _age_edge_field_names(G: nx.Graph, full_props: bool) -> tuple[str, ...]:
    """Edge counterpart of _age_node_field_names(). Pure and DB-free."""
    if not full_props:
        return _AGE_LEAN_EDGE_FIELDS
    keys: set[str] = set(_AGE_LEAN_EDGE_FIELDS)
    for _, _, data in G.edges(data=True):
        for k, v in data.items():
            if (
                isinstance(v, (str, int, float, bool))
                and not k.startswith("_")
                and _is_age_safe_prop_key(k)
            ):
                keys.add(k)
    rest = sorted(keys - set(_AGE_LEAN_EDGE_FIELDS))
    return _AGE_LEAN_EDGE_FIELDS + tuple(rest)


def _age_node_rows(
    G: nx.Graph,
    field_names: tuple[str, ...],
    node_community: dict[str, int],
    god_ids: set[str],
    cycle_files: set[str],
) -> dict[str, list[dict]]:
    """Group nodes by sanitized AGE label into batch-ready row dicts.

    Pure and DB-free (tier-1 testable). Every row carries exactly
    ``field_names``, filling missing/inapplicable values with None so every
    row in a batch has an identical shape.
    """
    groups: dict[str, list[dict]] = {}
    for node_id, data in G.nodes(data=True):
        label = _safe_label(data.get("file_type", "Entity").capitalize())
        source_file = data.get("source_file")
        row = {
            "id": node_id,
            "label": data.get("label", node_id),
            "source_file": source_file,
            "source_location": data.get("source_location"),
            "community": node_community.get(node_id),
            "degree": G.degree(node_id),
            "is_god_node": node_id in god_ids,
            "in_cycle": bool(source_file) and source_file in cycle_files,
        }
        for k in field_names:
            if k not in row:
                v = data.get(k)
                row[k] = v if isinstance(v, (str, int, float, bool)) else None
        groups.setdefault(label, []).append({k: row.get(k) for k in field_names})
    return groups


def _age_edge_rows(
    G: nx.Graph, field_names: tuple[str, ...]
) -> dict[str, list[dict]]:
    """Group edges by sanitized AGE relation type into batch-ready rows.

    Pure and DB-free (tier-1 testable).
    """
    groups: dict[str, list[dict]] = {}
    for u, v, data in G.edges(data=True):
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        # An undirected nx.Graph's own (u, v) tuple order reflects node
        # insertion order, not which side was the extracted "source" -
        # build.py stamps _src/_tgt precisely to recover that (see the
        # same idiom in analyze.py/serve.py/exporters/html.py). Without
        # this, MERGE (a)-[r]->(b) below can silently push every edge
        # backwards relative to docs/AGE_SCHEMA.md's documented
        # "source -> target" direction contract, found live while
        # validating Phase 5's pinned reverse-dependency-traversal query.
        row = {"src": data.get("_src", u), "tgt": data.get("_tgt", v)}
        for k in field_names:
            val = data.get(k)
            row[k] = val if isinstance(val, (str, int, float, bool)) else None
        groups.setdefault(rel, []).append(row)
    return groups


def _age_batches(rows: list[dict], size: int = 500):
    """Chunk rows into fixed-size batches for UNWIND $rows. Pure, DB-free."""
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


# Vertex properties an agent filters or joins on (docs/AGE_SCHEMA.md "Agent
# contract"). Each gets its own btree expression index -- see
# _ensure_age_property_indexes for why btree *and* GIN are both needed.
_AGE_INDEXED_NODE_PROPS = ("id", "source_file")


def _age_index_name(label: str, suffix: str) -> str:
    """Index name for a vertex label, kept within Postgres's 63-byte identifier
    limit (hash-suffixed when the label is long). Pure, DB-free -- tier-1
    testable."""
    base = f"{label}_{suffix}"
    if len(base) <= 63:
        return base
    import hashlib

    return f"{label[:32]}_{hashlib.sha1(label.encode()).hexdigest()[:12]}_{suffix}"


def _age_gin_index_name(label: str) -> str:
    """Back-compat alias: the ``properties`` GIN index's name."""
    return _age_index_name(label, "props_gin")


def _ensure_age_property_indexes(cur, sql, graph_name: str, labels) -> None:
    """Create the property indexes every vertex label needs. AGE indexes only
    its own internal ``id``/``start_id``/``end_id`` columns -- nothing on the
    user-facing ``properties`` agtype -- so both graphify's writes and agents'
    reads seq-scan the whole label table without these.

    Two index kinds are needed because AGE compiles the two idioms differently:

    * ``MATCH (n {{id: ...}})`` / ``MERGE (n:L {{id: ...}})`` (what
      ``push_to_age`` emits) -> ``properties @> '{{"id": ...}}'`` -> needs a
      **GIN** index on ``properties``. Without it a full push is O(nodes x
      edges) -- ~9 min for a ~13k-node / ~27k-edge graph, seconds with it.
    * ``WHERE n.id = ...`` / ``WHERE n.id IN [...]`` / ``WHERE n.source_file
      = ...`` (idiomatic agent Cypher, and docs/AGE_SCHEMA.md's pinned
      queries) -> ``agtype_access_operator(properties, '"id"') = ...`` -> a
      GIN index does NOT serve this; needs a **btree expression** index on
      that access-operator, one per filtered property (``id``,
      ``source_file``).

    AGE creates label tables lazily on first write, so ``create_vlabel`` them
    first (idempotent via ``ag_label``) so the indexes -- and every subsequent
    MERGE -- exist from row one. All validated live (Phase 0 spike + the
    dogfooding pass, docs/AGE_PLAN.md).
    """
    access = (
        "ag_catalog.agtype_access_operator("
        "VARIADIC ARRAY[properties, {key}::agtype])"
    )
    for label in labels:
        cur.execute(
            "SELECT count(*) FROM ag_catalog.ag_label l "
            "JOIN ag_catalog.ag_graph g ON g.graphid = l.graph "
            "WHERE g.name = %s AND l.name = %s;",
            (graph_name, label),
        )
        if not cur.fetchone()[0]:
            cur.execute(
                sql.SQL("SELECT create_vlabel({graph}, {label});").format(
                    graph=sql.Literal(graph_name), label=sql.Literal(label)
                )
            )
        tbl = sql.Identifier(graph_name, label)
        cur.execute(
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} USING gin (properties);"
            ).format(idx=sql.Identifier(_age_gin_index_name(label)), tbl=tbl)
        )
        for prop in _AGE_INDEXED_NODE_PROPS:
            cur.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {idx} ON {tbl} USING btree ("
                    + access
                    + ");"
                ).format(
                    idx=sql.Identifier(_age_index_name(label, f"{prop}_idx")),
                    tbl=tbl,
                    key=sql.Literal(f'"{prop}"'),
                )
            )


def _age_diff_filter(
    node_groups: dict[str, list[dict]],
    edge_groups: dict[str, list[dict]],
    diff: dict,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict[str, list[str]], dict[str, list[tuple[str, str]]]]:
    """Narrow full-graph node/edge row groups down to only what a
    graph_diff()-shaped ``diff`` says changed, and compute what to delete
    from the diff alone (docs/AGE_PLAN.md Phase 3 incremental sync).

    Pure and DB-free (tier-1 testable) -- push_to_age() calls this instead
    of reading live AGE state when a prior snapshot exists.

    Returns (node_groups, edge_groups, stale_by_label, stale_edges_by_rel).
    """
    changed_node_ids = {n["id"] for n in diff.get("new_nodes", [])}
    changed_node_ids |= {n["id"] for n in diff.get("changed_nodes", [])}
    filtered_node_groups = {
        label: filtered
        for label, rows in node_groups.items()
        if (filtered := [r for r in rows if r["id"] in changed_node_ids])
    }

    # AGE edge groups are keyed by _safe_rel()'s sanitized/uppercased
    # relation type (e.g. "calls" -> "CALLS"), but a graph_diff()-shaped
    # edge's "relation" field is the raw, un-sanitized string -- comparing
    # them directly always misses, silently dropping every changed/new
    # edge for a normal lowercase relation (found via review). Normalize
    # both sides through _safe_rel() the same way edge_groups' keys were
    # built.
    changed_edge_keys = {
        (e["source"], e["target"], _safe_rel(e.get("relation", "RELATED_TO")))
        for e in diff.get("new_edges", []) + diff.get("changed_edges", [])
    }

    stale_by_label: dict[str, list[str]] = {}
    relabeled_node_ids: set[str] = set()
    for n in diff.get("removed_nodes", []):
        label = _safe_label(str(n.get("properties", {}).get("file_type", "Entity")).capitalize())
        stale_by_label.setdefault(label, []).append(n["id"])
    for n in diff.get("changed_nodes", []):
        old_label = _safe_label(str(n.get("old", {}).get("file_type", "Entity")).capitalize())
        new_label = _safe_label(str(n.get("new", {}).get("file_type", "Entity")).capitalize())
        if old_label != new_label:
            stale_by_label.setdefault(old_label, []).append(n["id"])
            relabeled_node_ids.add(n["id"])

    # A node whose label changed is deleted (under its old label) via
    # DETACH DELETE below, which also removes every edge incident to it --
    # but graph_diff() doesn't mark an edge "changed" just because one of
    # its endpoints relabeled, so those otherwise-unchanged edges would
    # never be restored by changed_edge_keys alone (found via review).
    # Re-include every edge touching a relabeled node so it gets re-upserted
    # after the DETACH DELETE.
    filtered_edge_groups = {
        rel: filtered
        for rel, rows in edge_groups.items()
        if (filtered := [
            r for r in rows
            if (r["src"], r["tgt"], rel) in changed_edge_keys
            or r["src"] in relabeled_node_ids or r["tgt"] in relabeled_node_ids
        ])
    }

    stale_edges_by_rel: dict[str, list[tuple[str, str]]] = {}
    for e in diff.get("removed_edges", []):
        rel = _safe_rel(e.get("relation", "RELATED_TO"))
        stale_edges_by_rel.setdefault(rel, []).append((e["source"], e["target"]))

    return filtered_node_groups, filtered_edge_groups, stale_by_label, stale_edges_by_rel


def push_to_age(
    G: nx.Graph,
    conninfo: str,
    graph_name: str = "graphify",
    communities: dict[int, list[str]] | None = None,
    full_props: bool = False,
    batch_size: int = 500,
    diff: dict | None = None,
    conn=None,
) -> dict[str, int]:
    """Push graph to a running Apache AGE (Postgres extension) instance.

    Requires: pip install "graphifyy[age]" (psycopg[binary]).

    Deletion-safe: after upserting, deletes nodes/edges absent from the
    incoming graph in the *same transaction* as the upserts, so readers
    never see a partially-reconciled graph (docs/AGE_PLAN.md Phase 1). A
    node whose label changed is deleted under its old label as part of
    this same reconcile.

    ``diff`` (docs/AGE_PLAN.md Phase 3, ``graphify.analyze.graph_diff()``'s
    shape, computed by the caller against the reconstructed last-pushed
    snapshot -- see ``graphify.age_snapshots``): when given, skips the
    full-graph read-existing-state-from-AGE reconcile entirely and instead
    upserts only new/changed nodes and edges and deletes only what the diff
    reports removed (or relabeled). O(changed) instead of O(graph) once a
    prior snapshot exists. When ``None`` (the default), behavior is
    unchanged: a full deletion-safe push against live AGE state.

    ``conn`` (docs/AGE_PLAN.md Phase 4): pass an already-open psycopg
    connection to fold this push into a caller-managed transaction (e.g.
    branch materialization, which must commit the AGE mutation and its
    registry bookkeeping atomically) -- this function then neither commits
    nor closes it, leaving that to the caller. When ``None`` (the
    default), behavior is unchanged: this function opens its own
    connection and commits/closes it itself.

    See the module-level comment above for the two AGE constraints
    (literal graph name; enumerated SET fields) this function is built
    around, found live in the Phase 0 compatibility spike.
    """
    try:
        import psycopg
        from psycopg import sql
    except ImportError as e:
        raise ImportError(
            'psycopg not installed. Run: pip install "graphifyy[age]"'
        ) from e

    from graphify.analyze import god_nodes as _god_nodes_fn, find_import_cycles as _find_cycles_fn

    node_community = _node_community_map(communities) if communities else {}
    god_ids = {n["id"] for n in _god_nodes_fn(G, top_n=G.number_of_nodes() or 1)}
    cycle_files: set[str] = set()
    for rec in _find_cycles_fn(G):
        cycle_files.update(rec.get("cycle", []))

    node_field_names = _age_node_field_names(G, full_props)
    edge_field_names = _age_edge_field_names(G, full_props)
    node_groups = _age_node_rows(G, node_field_names, node_community, god_ids, cycle_files)
    edge_groups = _age_edge_rows(G, edge_field_names)

    diff_stale_by_label: dict[str, list[str]] | None = None
    diff_stale_edges_by_rel: dict[str, list[tuple[str, str]]] | None = None
    if diff is not None:
        # Incremental mode: only upsert rows the diff says are new/changed,
        # and delete only what the diff says was removed or relabeled --
        # no read of live AGE state needed (docs/AGE_PLAN.md Phase 3).
        node_groups, edge_groups, diff_stale_by_label, diff_stale_edges_by_rel = (
            _age_diff_filter(node_groups, edge_groups, diff)
        )

    graph_lit = sql.Literal(graph_name)

    def _sql_text(fragment: str) -> sql.SQL:
        """Wrap an internally-built SQL fragment for sql.format().

        psycopg's sql.SQL() takes a LiteralString so dynamic interpolation
        cannot sneak in unchecked; every fragment passed through here is
        safe by construction -- labels/relation types are whitelisted by
        _safe_label()/_safe_rel() ([A-Za-z0-9_]/[A-Z0-9_] only), SET
        clauses are built from whitelisted field names, and a_pat/b_pat
        are fixed ``a``/``b`` prefixes over those same whitelisted labels.
        """
        return sql.SQL(cast("LiteralString", fragment))

    def _cypher(body: str, returns: str = "(result agtype)") -> sql.Composed:
        return sql.SQL("SELECT * FROM cypher({graph}, $${body}$$) AS {returns};").format(
            graph=graph_lit, body=_sql_text(body), returns=_sql_text(returns)
        )

    def _execute_prepared(cur, stmt_name: str, payload: dict) -> None:
        # EXECUTE's argument can't be a normal bind parameter here
        # (psycopg.errors.IndeterminateDatatype) -- see the Phase 0 spike.
        stmt = sql.SQL("EXECUTE {name}({payload});").format(
            name=sql.Identifier(stmt_name), payload=sql.Literal(json.dumps(payload))
        )
        cur.execute(stmt)

    nodes_pushed = sum(len(rows) for rows in node_groups.values())
    edges_pushed = sum(len(rows) for rows in edge_groups.values())

    owns_conn = conn is None
    if owns_conn:
        conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            cur.execute(
                "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (graph_name,)
            )
            graph_count = cur.fetchone()
            if graph_count is None or not graph_count[0]:
                cur.execute("SELECT create_graph(%s);", (graph_name,))

            # Index properties->id before any MATCH/MERGE: without it every
            # id lookup is a per-row seq scan and a full push takes minutes.
            _ensure_age_property_indexes(cur, sql, graph_name, node_groups.keys())

            if diff_stale_by_label is not None:
                stale_by_label = diff_stale_by_label
            else:
                # --- Deletion-safe reconcile: snapshot existing (id, label)
                # pairs before upserting, so nodes absent from the incoming
                # graph -- or that changed label -- are deleted under their
                # *old* label, in the same transaction as the upserts.
                cur.execute(_cypher("MATCH (n) RETURN n.id, label(n)", "(id agtype, lbl agtype)"))
                existing = cur.fetchall()
                incoming_by_label = {
                    label: {row["id"] for row in rows} for label, rows in node_groups.items()
                }
                stale_by_label = {}
                for existing_id_raw, existing_label_raw in existing:
                    existing_id = json.loads(existing_id_raw) if isinstance(existing_id_raw, str) else existing_id_raw
                    existing_label = str(existing_label_raw).strip('"')
                    if existing_id not in incoming_by_label.get(existing_label, set()):
                        stale_by_label.setdefault(existing_label, []).append(existing_id)

            for label, stale_ids in stale_by_label.items():
                for batch in _age_batches([{"id": i} for i in stale_ids], batch_size):
                    stmt_name = "graphify_del_node"
                    cur.execute(
                        sql.SQL(
                            "PREPARE {name}(agtype) AS "
                            "SELECT * FROM cypher({graph}, $$ "
                            # $ids is a plain list; UNWIND yields each id
                            # scalar itself as `row`, not a map.
                            "  UNWIND $ids AS row "
                            "  MATCH (n:{label} {{id: row}}) "
                            "  DETACH DELETE n "
                            "$$, $1) AS (result agtype);"
                        ).format(
                            name=sql.Identifier(stmt_name),
                            graph=graph_lit,
                            label=_sql_text(label),
                        )
                    )
                    _execute_prepared(cur, stmt_name, {"ids": [r["id"] for r in batch]})
                    cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

            # --- Upsert nodes, grouped by label, explicit per-field SET
            # (AGE rejects a parameterized/UNWIND-derived map in SET).
            for label, rows in node_groups.items():
                set_clause = ", ".join(f"n.{f} = row.{f}" for f in node_field_names)
                stmt_name = "graphify_upsert_node"
                cur.execute(
                    sql.SQL(
                        "PREPARE {name}(agtype) AS "
                        "SELECT * FROM cypher({graph}, $$ "
                        "  UNWIND $rows AS row "
                        "  MERGE (n:{label} {{id: row.id}}) "
                        "  SET {set_clause} "
                        "$$, $1) AS (result agtype);"
                    ).format(
                        name=sql.Identifier(stmt_name),
                        graph=graph_lit,
                        label=_sql_text(label),
                        set_clause=_sql_text(set_clause),
                    )
                )
                for batch in _age_batches(rows, batch_size):
                    _execute_prepared(cur, stmt_name, {"rows": batch})
                cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

            if diff_stale_edges_by_rel is not None:
                stale_edges_by_rel = diff_stale_edges_by_rel
            else:
                # --- Delete stale edges: same snapshot-then-diff approach,
                # keyed on (src id, tgt id, relation type).
                cur.execute(
                    _cypher(
                        "MATCH (a)-[r]->(b) RETURN a.id, b.id, label(r)",
                        "(src agtype, tgt agtype, lbl agtype)",
                    )
                )
                existing_edges = cur.fetchall()
                incoming_edge_keys = {
                    (rel, row["src"], row["tgt"]) for rel, rows in edge_groups.items() for row in rows
                }
                stale_edges_by_rel = {}
                for src_raw, tgt_raw, rel_raw in existing_edges:
                    src = json.loads(src_raw) if isinstance(src_raw, str) else src_raw
                    tgt = json.loads(tgt_raw) if isinstance(tgt_raw, str) else tgt_raw
                    rel = str(rel_raw).strip('"')
                    if (rel, src, tgt) not in incoming_edge_keys:
                        stale_edges_by_rel.setdefault(rel, []).append((src, tgt))

            for rel, pairs in stale_edges_by_rel.items():
                for batch in _age_batches([{"src": s, "tgt": t} for s, t in pairs], batch_size):
                    stmt_name = "graphify_del_edge"
                    cur.execute(
                        sql.SQL(
                            "PREPARE {name}(agtype) AS "
                            "SELECT * FROM cypher({graph}, $$ "
                            "  UNWIND $rows AS row "
                            "  MATCH (a {{id: row.src}})-[r:{rel}]->(b {{id: row.tgt}}) "
                            "  DELETE r "
                            "$$, $1) AS (result agtype);"
                        ).format(name=sql.Identifier(stmt_name), graph=graph_lit, rel=_sql_text(rel))
                    )
                    _execute_prepared(cur, stmt_name, {"rows": batch})
                    cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

            # --- Upsert edges. Sub-group each relation's rows by the AGE
            # labels of its endpoints so the endpoint MATCH can name them
            # (`MATCH (a:Code {id: ...})`): a labelled match hits one label
            # table's GIN index instead of probing all of them, ~2.5x faster
            # on a large push. Endpoint label comes from the same rule
            # `_age_node_rows` uses; unknown ids (shouldn't happen) fall back
            # to a labelless match.
            node_label_by_id = {
                nid: _safe_label(data.get("file_type", "Entity").capitalize())
                for nid, data in G.nodes(data=True)
            }
            set_clause = ", ".join(f"r.{f} = row.{f}" for f in edge_field_names)
            for rel, rows in edge_groups.items():
                by_endpoint_labels: dict[tuple[str | None, str | None], list[dict]] = {}
                for row in rows:
                    key = (node_label_by_id.get(row["src"]), node_label_by_id.get(row["tgt"]))
                    by_endpoint_labels.setdefault(key, []).append(row)
                for (src_label, tgt_label), sub_rows in by_endpoint_labels.items():
                    a_pat = f"a:{src_label}" if src_label else "a"
                    b_pat = f"b:{tgt_label}" if tgt_label else "b"
                    stmt_name = "graphify_upsert_edge"
                    cur.execute(
                        sql.SQL(
                            "PREPARE {name}(agtype) AS "
                            "SELECT * FROM cypher({graph}, $$ "
                            "  UNWIND $rows AS row "
                            "  MATCH ({a_pat} {{id: row.src}}), ({b_pat} {{id: row.tgt}}) "
                            "  MERGE (a)-[r:{rel}]->(b) "
                            "  SET {set_clause} "
                            "$$, $1) AS (result agtype);"
                        ).format(
                            name=sql.Identifier(stmt_name),
                            graph=graph_lit,
                            a_pat=_sql_text(a_pat),
                            b_pat=_sql_text(b_pat),
                            rel=_sql_text(rel),
                            set_clause=_sql_text(set_clause),
                        )
                    )
                    for batch in _age_batches(sub_rows, batch_size):
                        _execute_prepared(cur, stmt_name, {"rows": batch})
                    cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

        if owns_conn:
            conn.commit()
    except Exception:
        if owns_conn:
            conn.rollback()
        raise
    finally:
        if owns_conn:
            conn.close()

    return {"nodes": nodes_pushed, "edges": edges_pushed}
