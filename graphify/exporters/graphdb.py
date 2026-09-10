"""graphdb — moved verbatim from graphify/export.py."""
from __future__ import annotations

from collections import defaultdict
from graphify.analyze import _node_community_map
import networkx as nx
import re

_BATCH_SIZE = 500


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

    # Group by label/rel-type: Cypher does not support parameterized labels,
    # so UNWIND batches must be homogeneous to keep a fixed query shape.
    # Build id->label map so edge MATCH can include the label and use the index.
    id_to_label: dict[str, str] = {}
    by_label: dict[str, list[dict]] = defaultdict(list)
    for node_id, data in G.nodes(data=True):
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        props["id"] = node_id
        cid = node_community.get(node_id)
        if cid is not None:
            props["community"] = cid
        lbl = _safe_label(data.get("file_type", "Entity").capitalize())
        id_to_label[node_id] = lbl
        by_label[lbl].append(props)

    # Group edges by (src_label, tgt_label, rel) so the MATCH can use label
    # indexes — a label-less MATCH (a {id: ...}) ignores all constraints and
    # scans the full node store, making edge inserts O(N²).
    by_rel: dict[tuple, list[dict]] = defaultdict(list)
    for u, v, data in G.edges(data=True):
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        src_lbl = id_to_label.get(u, "Entity")
        tgt_lbl = id_to_label.get(v, "Entity")
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        by_rel[(src_lbl, tgt_lbl, rel)].append({"src": u, "tgt": v, "props": props})

    total_nodes = sum(len(v) for v in by_label.values())
    total_edges = sum(len(v) for v in by_rel.values())

    import time as _time
    _LOG_INTERVAL = 60  # seconds

    def _log_progress(kind: str, done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 100
        print(f"[graphify] neo4j {kind}: {done}/{total} ({pct}%)", flush=True)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0
    last_node_log = _time.monotonic()
    last_edge_log = _time.monotonic()

    with driver.session() as session:
        for label, rows in by_label.items():
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = rows[i:i + _BATCH_SIZE]
                session.execute_write(
                    lambda tx, b=batch, lbl=label: tx.run(
                        f"UNWIND $batch AS row MERGE (n:{lbl} {{id: row.id}}) SET n += row",
                        batch=b,
                    )
                )
                nodes_pushed += len(batch)
                now = _time.monotonic()
                if now - last_node_log >= _LOG_INTERVAL:
                    _log_progress("nodes", nodes_pushed, total_nodes)
                    last_node_log = now

        _log_progress("nodes", nodes_pushed, total_nodes)

        for (src_lbl, tgt_lbl, rel), rows in by_rel.items():
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = rows[i:i + _BATCH_SIZE]
                session.execute_write(
                    lambda tx, b=batch, sl=src_lbl, tl=tgt_lbl, r=rel: tx.run(
                        f"UNWIND $batch AS row "
                        f"MATCH (a:{sl} {{id: row.src}}), (b:{tl} {{id: row.tgt}}) "
                        f"MERGE (a)-[rr:{r}]->(b) SET rr += row.props",
                        batch=b,
                    )
                )
                edges_pushed += len(batch)
                now = _time.monotonic()
                if now - last_edge_log >= _LOG_INTERVAL:
                    _log_progress("edges", edges_pushed, total_edges)
                    last_edge_log = now

        _log_progress("edges", edges_pushed, total_edges)

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

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a FalkorDB node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

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
