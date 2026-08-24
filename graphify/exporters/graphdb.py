"""graphdb — moved verbatim from graphify/export.py.

The ``stream_push_to_*`` variants at the bottom are the memory-bounded twins
of ``push_to_*``: same Cypher, same row payloads, but fed straight from
``graph.json`` instead of a NetworkX graph.

Index-driven push (all four writers)
------------------------------------
Every pushed node carries the shared label ``:GraphifyNode`` (see
``SHARED_NODE_LABEL``) in addition to its per-file-type label, node MERGEs
merge on the shared label + ``id``, and edge MERGEs MATCH both endpoints as
``(:GraphifyNode {id: ...})``. Before any write each pusher idempotently
creates the ``GraphifyNode`` on ``(id)`` index plus one per-type-label index,
then runs a one-scan adoption query so containers loaded by the previous
unlabeled pusher keep working (contract documented on
``_ADOPT_LEGACY_NODES``).
"""
from __future__ import annotations

from pathlib import Path

from graphify.analyze import _node_community_map
from graphify.exporters.node_link_stream import (
    NodeLinkScan,
    iter_node_link_array,
    scan_node_link,
)
import networkx as nx
import re


def _batch_rows(rows: list[dict], batch_size: int):
    """Yield ``rows`` in chunks of at most ``batch_size``."""
    for start in range(0, len(rows), batch_size):
        yield rows[start:start + batch_size]


# Shared label stamped on every node the pushers write, in addition to the
# per-file-type label (Python, Markdown, ...). Node MERGEs merge on
# (:GraphifyNode {id}) and edge MERGEs MATCH both endpoints as
# (:GraphifyNode {id}), so ONE index — GraphifyNode on (id) — serves every
# lookup on both phases. The previous writers merged nodes per type label and
# matched edge endpoints with NO label at all; per-label indexes cannot serve
# label-less lookups, so on a production 1.87GB graph (1,211,189 nodes) each
# edge MERGE full-scanned all 1.2M nodes twice and the edge phase crawled at
# ~2 edges/sec — days for 1.15M edges. The node phase without indexes ran at
# ~3.6s per 500-row batch (~137 entries/sec); with (label, id) indexes it was
# measured ~60x faster.
SHARED_NODE_LABEL = "GraphifyNode"

# Old-container contract: ADOPT-ON-PUSH. Containers loaded by the previous
# unlabeled pusher hold nodes WITHOUT the shared label, which a MERGE on
# (:GraphifyNode {id}) can never match — without migration every re-push
# would duplicate the whole graph. So every push begins with this one-scan
# adoption query: it stamps :GraphifyNode on any node carrying an `id`
# property, the subsequent MERGEs then match those old nodes in place, and no
# fresh container is required. Re-running it on an already-adopted (or empty)
# graph is a no-op. The push has always assumed the target graph/database
# belongs to graphify — the old edge MATCH bound ANY node with a matching
# `id` — so stamping every id-bearing node adds no new assumption. A node
# whose file_type changes between pushes accumulates type labels; identity is
# the shared label + id, so it still upserts, never duplicates.
_ADOPT_LEGACY_NODES = f"MATCH (n) WHERE n.id IS NOT NULL SET n:{SHARED_NODE_LABEL}"


def _index_cypher(label: str, *, if_not_exists: bool) -> str:
    """The engine's create-index-on-(label, id) statement.

    Neo4j (4.4+) supports ``CREATE INDEX IF NOT EXISTS``; FalkorDB has no
    IF NOT EXISTS form and instead errors with "already indexed", which
    :func:`_create_id_index` tolerates.
    """
    clause = "CREATE INDEX IF NOT EXISTS" if if_not_exists else "CREATE INDEX"
    return f"{clause} FOR (n:{label}) ON (n.id)"


def _create_id_index(run, label: str, *, if_not_exists: bool) -> None:
    """Create the (label, id) index, tolerating an already-exists response.

    ``run`` is the engine's raw-query callable (``session.run`` /
    ``graph.query``). Both engines report an existing index in the error text
    — Neo4j "An equivalent index already exists" (EquivalentSchemaRule...),
    FalkorDB "Attribute 'id' is already indexed" — and the driver exception
    classes are not importable here without hard driver deps, so tolerance
    matches the message; anything else re-raises.
    """
    try:
        run(_index_cypher(label, if_not_exists=if_not_exists))
    except Exception as exc:  # driver-specific classes; matched by message
        message = str(exc).lower()
        if "already" in message and "index" in message:
            return
        raise


def _prepare_push_schema(run, *, if_not_exists: bool) -> None:
    """Shared-label index + legacy adoption — precedes every write."""
    _create_id_index(run, SHARED_NODE_LABEL, if_not_exists=if_not_exists)
    run(_ADOPT_LEGACY_NODES)


def _node_merge_cypher(ftype: str) -> str:
    """UNWIND upsert: merge on the shared label + id, then add the type label."""
    return (
        f"UNWIND $rows AS row "
        f"MERGE (n:{SHARED_NODE_LABEL} {{id: row.id}}) "
        f"SET n:{ftype} SET n += row.props"
    )


def _edge_merge_cypher(rel: str) -> str:
    """UNWIND edge upsert with index-served shared-label endpoint lookups."""
    return (
        f"UNWIND $rows AS row "
        f"MATCH (a:{SHARED_NODE_LABEL} {{id: row.src}}), "
        f"(b:{SHARED_NODE_LABEL} {{id: row.tgt}}) "
        f"MERGE (a)-[r:{rel}]->(b) SET r += row.props"
    )


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

    Index-driven: every node gets the shared ``:GraphifyNode`` label (see
    ``SHARED_NODE_LABEL``) on top of its type label, node MERGEs merge on the
    shared label + id, and edge endpoints MATCH via the shared label so both
    phases are served by the ``GraphifyNode`` on ``(id)`` index. Before any
    write the pusher creates that index plus one per type label
    (``CREATE INDEX IF NOT EXISTS``, already-exists responses tolerated) and
    runs the one-scan legacy adoption query (``_ADOPT_LEGACY_NODES``) so a
    database loaded by the previous unlabeled pusher upserts in place instead
    of duplicating.
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
        def _run(cypher: str):
            return session.run(cypher)

        _prepare_push_schema(_run, if_not_exists=True)
        for ftype in node_rows:
            _create_id_index(_run, ftype, if_not_exists=True)

        for ftype, rows in node_rows.items():
            for batch in _batch_rows(rows, batch_size):
                session.run(_node_merge_cypher(ftype), rows=batch)
                nodes_pushed += len(batch)

        for rel, rows in edge_rows.items():
            for batch in _batch_rows(rows, batch_size):
                session.run(_edge_merge_cypher(rel), rows=batch)
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
      - index DDL has no IF NOT EXISTS: a plain ``CREATE INDEX FOR (n:L) ON
        (n.id)`` is issued via graph.query and the "already indexed" error a
        re-push provokes is tolerated (see ``_create_id_index``).
      - the type label is added with ``SET n:Label``, which FalkorDB supports
        from v2.12.

    Index-driven like push_to_neo4j: shared ``:GraphifyNode`` label on every
    node (``SHARED_NODE_LABEL``), MERGE on shared label + id, edge endpoints
    MATCHed via the shared label, indexes created before any write, and the
    one-scan legacy adoption query run first so graphs loaded by the previous
    unlabeled pusher upsert in place instead of duplicating.

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

    def _run(cypher: str):
        return graph.query(cypher)

    _prepare_push_schema(_run, if_not_exists=False)
    for ftype in node_rows:
        _create_id_index(_run, ftype, if_not_exists=False)

    for ftype, rows in node_rows.items():
        for batch in _batch_rows(rows, batch_size):
            graph.query(_node_merge_cypher(ftype), {"rows": batch})
            nodes_pushed += len(batch)

    for rel, rows in edge_rows.items():
        for batch in _batch_rows(rows, batch_size):
            graph.query(_edge_merge_cypher(rel), {"rows": batch})
            edges_pushed += len(batch)

    return {"nodes": nodes_pushed, "edges": edges_pushed}


# ---------------------------------------------------------------------------
# Streaming push - graph.json to the batched UNWIND writers, no NetworkX.
#
# The in-memory push above json.loads the whole graph.json and rebuilds a
# NetworkX graph before iterating it. A push never needs the graph object -
# it only walks nodes, then edges - and on a 1.87GB graph.json that load
# peaked at ~5.3GB RSS and was OOM-killed on a 7.6GB box before a single row
# went out. The stream_push_to_* twins below read the file incrementally
# (graphify.exporters.node_link_stream) and hand rows to the same batched
# UNWIND queries, so peak memory is batch-scale, not graph-scale.
#
# Wire-behaviour parity with push_to_*: identical Cypher text, identical row
# payload shape, per-label/per-relation row order preserved, every node batch
# sent before any edge batch, upserts idempotent. Two intentional
# differences: (1) batch interleaving ACROSS labels/relations - the in-memory
# push groups the whole graph per label first, the streaming push flushes a
# label's batch as soon as it holds batch_size rows; (2) per-type-label index
# timing - the in-memory push knows every label up front and creates all
# indexes before the first write, the streaming push creates each type
# label's index at that label's first batch (still before any write under
# that label). The shared-label index + legacy adoption always precede every
# write in both. MERGE semantics make the database end-state identical
# either way.
# ---------------------------------------------------------------------------

_SAFE_REL = re.compile(r"[^A-Z0-9_]")
_SAFE_LABEL = re.compile(r"[^A-Za-z0-9_]")


def _stream_safe_rel(relation: str) -> str:
    return _SAFE_REL.sub("_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"


def _stream_safe_label(label: str) -> str:
    sanitized = _SAFE_LABEL.sub("", label)
    return sanitized if sanitized else "Entity"


def _iter_node_rows(graph_path: Path, scan: NodeLinkScan, node_community: dict):
    """Yield (label, row) per "nodes" entry - the exact push_to_* row shape."""
    if scan.nodes_offset is None:
        return
    for item in iter_node_link_array(graph_path, scan.nodes_offset):
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(
                f'{graph_path} is not a node-link graph.json: every "nodes" '
                f'entry must be an object with an "id"'
            )
        node_id = item["id"]
        props = {
            k: v for k, v in item.items()
            if k != "id" and isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        props["id"] = node_id
        cid = node_community.get(node_id)
        if cid is not None:
            props["community"] = cid
        ftype = _stream_safe_label(item.get("file_type", "Entity").capitalize())
        yield ftype, {"id": node_id, "props": props}


def _iter_edge_rows(graph_path: Path, scan: NodeLinkScan):
    """Yield (relation, row) per "links"/"edges" entry - the push_to_* row shape.

    ``key`` is a NetworkX edge key, not an attribute, only when the file says
    multigraph - mirroring node_link_graph, which pops it in that case alone.
    """
    offset = scan.edge_array_offset
    if offset is None:
        return
    drop = ("source", "target", "key") if scan.multigraph else ("source", "target")
    for item in iter_node_link_array(graph_path, offset):
        if not isinstance(item, dict) or "source" not in item or "target" not in item:
            raise ValueError(
                f'{graph_path} is not a node-link graph.json: every link '
                f'entry must be an object with "source" and "target"'
            )
        rel = _stream_safe_rel(item.get("relation", "RELATED_TO"))
        props = {
            k: v for k, v in item.items()
            if k not in drop and isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        yield rel, {"src": item["source"], "tgt": item["target"], "props": props}


def _send_grouped(rows_iter, batch_size: int, send) -> int:
    """Buffer (group, row) pairs per group; flush a group at batch_size rows.

    Memory held: at most batch_size rows per distinct group (a handful of
    file types / relation names), never the whole graph. Returns rows sent.
    """
    pending: dict[str, list[dict]] = {}
    sent = 0
    for group, row in rows_iter:
        bucket = pending.setdefault(group, [])
        bucket.append(row)
        if len(bucket) >= batch_size:
            send(group, bucket)
            sent += len(bucket)
            pending[group] = []
    for group, bucket in pending.items():
        if bucket:
            send(group, bucket)
            sent += len(bucket)
    return sent


def stream_push_to_neo4j(
    graph_path: "str | Path",
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
    *,
    batch_size: int = 100,
) -> dict[str, int]:
    """Stream a node-link graph.json straight into the batched Neo4j push.

    Same wire behaviour as :func:`push_to_neo4j` (see the module comment for
    the parity contract; index-driven with the shared ``:GraphifyNode`` label
    and the legacy adoption scan, exactly as documented there) with peak
    memory at batch scale. The graph file is read twice - one fast offset
    scan, one row pass - both with a fixed buffer.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    if batch_size < 1:
        raise ValueError(f"batch_size must be a positive integer, got {batch_size}")

    graph_path = Path(graph_path)
    node_community = _node_community_map(communities) if communities else {}
    scan = scan_node_link(graph_path)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        def _run(cypher: str):
            return session.run(cypher)

        _prepare_push_schema(_run, if_not_exists=True)
        indexed_labels: set[str] = set()

        def _send_nodes(ftype: str, batch: list[dict]) -> None:
            if ftype not in indexed_labels:
                _create_id_index(_run, ftype, if_not_exists=True)
                indexed_labels.add(ftype)
            session.run(_node_merge_cypher(ftype), rows=batch)

        def _send_edges(rel: str, batch: list[dict]) -> None:
            session.run(_edge_merge_cypher(rel), rows=batch)

        nodes_pushed = _send_grouped(
            _iter_node_rows(graph_path, scan, node_community), batch_size, _send_nodes)
        edges_pushed = _send_grouped(
            _iter_edge_rows(graph_path, scan), batch_size, _send_edges)

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}


def stream_push_to_falkordb(
    graph_path: "str | Path",
    uri: str,
    user: str | None = None,
    password: str | None = None,
    communities: dict[int, list[str]] | None = None,
    graph_name: str = "graphify",
    *,
    batch_size: int = 100,
) -> dict[str, int]:
    """Stream a node-link graph.json straight into the batched FalkorDB push.

    Same wire behaviour as :func:`push_to_falkordb` (see the module comment
    for the parity contract, and push_to_falkordb's docstring for the URI /
    auth rules and the index/shared-label/legacy-adoption behaviour, all
    unchanged here) with peak memory at batch scale.
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

    graph_path = Path(graph_path)
    node_community = _node_community_map(communities) if communities else {}
    scan = scan_node_link(graph_path)

    parsed = urlparse(uri if "://" in uri else f"redis://{uri}")
    connect_user = parsed.username or (user if password else None)
    connect_password = parsed.password or (password or None)
    db = FalkorDB(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=connect_user,
        password=connect_password,
    )
    graph = db.select_graph(graph_name)

    def _run(cypher: str):
        return graph.query(cypher)

    _prepare_push_schema(_run, if_not_exists=False)
    indexed_labels: set[str] = set()

    def _send_nodes(ftype: str, batch: list[dict]) -> None:
        if ftype not in indexed_labels:
            _create_id_index(_run, ftype, if_not_exists=False)
            indexed_labels.add(ftype)
        graph.query(_node_merge_cypher(ftype), {"rows": batch})

    def _send_edges(rel: str, batch: list[dict]) -> None:
        graph.query(_edge_merge_cypher(rel), {"rows": batch})

    nodes_pushed = _send_grouped(
        _iter_node_rows(graph_path, scan, node_community), batch_size, _send_nodes)
    edges_pushed = _send_grouped(
        _iter_edge_rows(graph_path, scan), batch_size, _send_edges)

    return {"nodes": nodes_pushed, "edges": edges_pushed}
