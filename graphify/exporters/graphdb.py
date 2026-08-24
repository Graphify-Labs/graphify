"""graphdb — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.analyze import _node_community_map
import networkx as nx
import re


def _batch_rows(rows: list[dict], batch_size: int):
    """Yield ``rows`` in chunks of at most ``batch_size``."""
    for start in range(0, len(rows), batch_size):
        yield rows[start:start + batch_size]


def push_to_neo4j(
    G: nx.Graph,
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
    *,
    batch_size: int = 100,
) -> dict[str, int]:
    """Push graph directly to a running Neo4j instance via the Python driver.

    Requires: pip install neo4j

    Uses MERGE so re-running is safe - nodes and edges are upserted, not duplicated.
    Returns a dict with counts of nodes and edges pushed.

    Rows are sent in UNWIND batches of ``batch_size`` (default 100) instead of
    one query per node/edge - a per-entry push spends nearly all its time on
    round trips once the server is not on localhost. Node labels and
    relationship types are baked into the Cypher text (they cannot be
    parameters), so rows are grouped by sanitized label/relation first and each
    group is batched separately. UNWIND processes rows in order, so duplicates
    inside one batch upsert exactly as the per-entry queries did.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    if batch_size < 1:
        raise ValueError(f"batch_size must be a positive integer, got {batch_size}")

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a Neo4j node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    node_rows: dict[str, list[dict]] = {}
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
        node_rows.setdefault(ftype, []).append({"id": node_id, "props": props})

    edge_rows: dict[str, list[dict]] = {}
    for u, v, data in G.edges(data=True):
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        edge_rows.setdefault(rel, []).append({"src": u, "tgt": v, "props": props})

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        for ftype, rows in node_rows.items():
            for batch in _batch_rows(rows, batch_size):
                session.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{ftype} {{id: row.id}}) SET n += row.props",
                    rows=batch,
                )
                nodes_pushed += len(batch)

        for rel, rows in edge_rows.items():
            for batch in _batch_rows(rows, batch_size):
                session.run(
                    f"UNWIND $rows AS row "
                    f"MATCH (a {{id: row.src}}), (b {{id: row.tgt}}) "
                    f"MERGE (a)-[r:{rel}]->(b) SET r += row.props",
                    rows=batch,
                )
                edges_pushed += len(batch)

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}

def push_to_falkordb(
    G: nx.Graph,
    uri: str,
    user: str | None = None,
    password: str | None = None,
    communities: dict[int, list[str]] | None = None,
    graph_name: str = "graphify",
    *,
    batch_size: int = 100,
) -> dict[str, int]:
    """Push graph directly to a running FalkorDB instance via the Python SDK.

    Requires: pip install falkordb

    FalkorDB is OpenCypher-compatible, so the MERGE/SET upsert queries are
    identical to push_to_neo4j - including the UNWIND batching (``batch_size``
    rows per round trip, grouped by sanitized label/relation because those are
    baked into the Cypher text and cannot be parameters). Differences from the
    Neo4j path:
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

    if batch_size < 1:
        raise ValueError(f"batch_size must be a positive integer, got {batch_size}")

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
    node_rows: dict[str, list[dict]] = {}
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
        node_rows.setdefault(ftype, []).append({"id": node_id, "props": props})

    edge_rows: dict[str, list[dict]] = {}
    for u, v, data in G.edges(data=True):
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        edge_rows.setdefault(rel, []).append({"src": u, "tgt": v, "props": props})

    graph = db.select_graph(graph_name)
    nodes_pushed = 0
    edges_pushed = 0

    for ftype, rows in node_rows.items():
        for batch in _batch_rows(rows, batch_size):
            graph.query(
                f"UNWIND $rows AS row "
                f"MERGE (n:{ftype} {{id: row.id}}) SET n += row.props",
                {"rows": batch},
            )
            nodes_pushed += len(batch)

    for rel, rows in edge_rows.items():
        for batch in _batch_rows(rows, batch_size):
            graph.query(
                f"UNWIND $rows AS row "
                f"MATCH (a {{id: row.src}}), (b {{id: row.tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += row.props",
                {"rows": batch},
            )
            edges_pushed += len(batch)

    return {"nodes": nodes_pushed, "edges": edges_pushed}
