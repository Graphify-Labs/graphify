"""graphdb — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.analyze import _node_community_map
import json
import networkx as nx
import re


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
        graph.query(
            f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
            f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
            {"src": u, "tgt": v, "props": props},
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
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_"):
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
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_"):
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
        row = {"src": u, "tgt": v}
        for k in field_names:
            val = data.get(k)
            row[k] = val if isinstance(val, (str, int, float, bool)) else None
        groups.setdefault(rel, []).append(row)
    return groups


def _age_batches(rows: list[dict], size: int = 500):
    """Chunk rows into fixed-size batches for UNWIND $rows. Pure, DB-free."""
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


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

    changed_edge_keys = {
        (e["source"], e["target"], e.get("relation", ""))
        for e in diff.get("new_edges", []) + diff.get("changed_edges", [])
    }
    filtered_edge_groups = {
        rel: filtered
        for rel, rows in edge_groups.items()
        if (filtered := [r for r in rows if (r["src"], r["tgt"], rel) in changed_edge_keys])
    }

    stale_by_label: dict[str, list[str]] = {}
    for n in diff.get("removed_nodes", []):
        label = _safe_label(str(n.get("properties", {}).get("file_type", "Entity")).capitalize())
        stale_by_label.setdefault(label, []).append(n["id"])
    for n in diff.get("changed_nodes", []):
        old_label = _safe_label(str(n.get("old", {}).get("file_type", "Entity")).capitalize())
        new_label = _safe_label(str(n.get("new", {}).get("file_type", "Entity")).capitalize())
        if old_label != new_label:
            stale_by_label.setdefault(old_label, []).append(n["id"])

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

    def _cypher(body: str, returns: str = "(result agtype)") -> sql.Composed:
        return sql.SQL("SELECT * FROM cypher({graph}, $${body}$$) AS {returns};").format(
            graph=graph_lit, body=sql.SQL(body), returns=sql.SQL(returns)
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

    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            cur.execute(
                "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = %s;", (graph_name,)
            )
            if not cur.fetchone()[0]:
                cur.execute("SELECT create_graph(%s);", (graph_name,))

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
                            label=sql.SQL(label),
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
                        label=sql.SQL(label),
                        set_clause=sql.SQL(set_clause),
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
                        ).format(name=sql.Identifier(stmt_name), graph=graph_lit, rel=sql.SQL(rel))
                    )
                    _execute_prepared(cur, stmt_name, {"rows": batch})
                    cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

            # --- Upsert edges, grouped by relation type.
            for rel, rows in edge_groups.items():
                set_clause = ", ".join(f"r.{f} = row.{f}" for f in edge_field_names)
                stmt_name = "graphify_upsert_edge"
                cur.execute(
                    sql.SQL(
                        "PREPARE {name}(agtype) AS "
                        "SELECT * FROM cypher({graph}, $$ "
                        "  UNWIND $rows AS row "
                        "  MATCH (a {{id: row.src}}), (b {{id: row.tgt}}) "
                        "  MERGE (a)-[r:{rel}]->(b) "
                        "  SET {set_clause} "
                        "$$, $1) AS (result agtype);"
                    ).format(
                        name=sql.Identifier(stmt_name),
                        graph=graph_lit,
                        rel=sql.SQL(rel),
                        set_clause=sql.SQL(set_clause),
                    )
                )
                for batch in _age_batches(rows, batch_size):
                    _execute_prepared(cur, stmt_name, {"rows": batch})
                cur.execute(sql.SQL("DEALLOCATE {name};").format(name=sql.Identifier(stmt_name)))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"nodes": nodes_pushed, "edges": edges_pushed}
