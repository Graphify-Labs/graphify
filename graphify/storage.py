"""NeuG graph database adapter for graphify.

Provides an optional parallel storage engine alongside NetworkX.
NeuG is lazily imported — when not installed, callers should catch
ImportError at the call site and skip silently.

All property values interpolated into Cypher statements use NeuG's native
parameterised queries ($param syntax) to prevent injection.  Table/label
names (which come from a fixed internal set, not user input) are still
interpolated as identifiers.

Single-table schema: one node table + one edge table, with file_type and
relation as properties (not separate tables).  This aligns with graphify's
NetworkX graph model and enables neug GDS algorithms that operate on a
single graph.
"""
from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from .build import _FILE_TYPE_SYNONYMS, _normalize_id, _norm_source_file
from .validate import VALID_FILE_TYPES

# ---------------------------------------------------------------------------
# Single-table schema
# ---------------------------------------------------------------------------

_NODE_DDL = """CREATE NODE TABLE IF NOT EXISTS node (
    id STRING PRIMARY KEY, label STRING, file_type STRING,
    source_file STRING, source_location STRING,
    community INT64, community_name STRING)"""

_NODE_COLUMNS = ["id", "label", "file_type", "source_file", "source_location",
                 "community", "community_name"]

_EDGE_DDL = """CREATE REL TABLE IF NOT EXISTS edge (
    FROM node TO node,
    relation STRING, confidence STRING,
    confidence_score DOUBLE, source_file STRING, weight DOUBLE)"""

_EDGE_COLUMNS = ["from_id", "to_id", "relation", "confidence",
                 "confidence_score", "source_file", "weight"]


# ---------------------------------------------------------------------------
# CSV helpers for bulk COPY FROM
# ---------------------------------------------------------------------------

def _sanitize_csv_value(v: object) -> str:
    if isinstance(v, str):
        return v.replace("\n", "\\n").replace("\r", "")
    return str(v)


def _write_csv(path: str, rows: list[dict], columns: list[str]) -> int:
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore",
                           quoting=csv.QUOTE_ALL)
        w.writeheader()
        for row in rows:
            w.writerow({k: _sanitize_csv_value(row.get(k, "")) for k in columns})
    return len(rows)


def _copy_node_csv(conn: object, csv_path: str) -> None:
    conn.execute(
        f'COPY node FROM "{csv_path}" (header=true, delim=",", escaping=false)'
    )


def _copy_rel_csv(conn: object, csv_path: str) -> None:
    conn.execute(
        f'COPY edge FROM "{csv_path}" '
        f'(from="node", to="node", '
        f'header=true, delim=",", escaping=false)'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: str) -> tuple:
    """Open (or create) a NeuG database and connect.

    Returns (db, conn).  Raises ImportError if neug is not installed.
    """
    import neug
    db = neug.Database(db_path)
    conn = db.connect()
    return db, conn


def ensure_schema(conn: object, *, create_tables: bool = True) -> set[str]:
    """Create the single node + edge tables if needed.

    Returns an empty set (kept for backward-compat with callers that
    pass the return value to ingest_extraction's known_tables).
    """
    if create_tables:
        conn.execute(_NODE_DDL)
        conn.execute(_EDGE_DDL)
    return set()


def _fix_file_type(ft: str | None) -> str:
    """Canonicalize file_type, matching build.py:138-146 logic."""
    if not ft or ft not in VALID_FILE_TYPES:
        return _FILE_TYPE_SYNONYMS.get(ft, "concept") if ft else "concept"
    return ft


def _bulk_ingest(
    conn: object,
    extraction: dict,
    *,
    root: str | None = None,
    known_tables: set[str] | None = None,
) -> dict[str, str]:
    """Full build via COPY FROM — much faster than per-row Cypher CREATE."""
    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []

    # --- collect node rows (single table) ---
    node_types: dict[str, str] = {}
    node_rows: list[dict] = []
    written_ids: set[str] = set()

    for node in nodes:
        nid = _normalize_id(node.get("id", ""))
        if not nid or nid in written_ids:
            continue
        written_ids.add(nid)
        ft = _fix_file_type(node.get("file_type"))
        node_types[nid] = ft
        node_rows.append({
            "id": nid,
            "label": node.get("label", ""),
            "file_type": ft,
            "source_file": _norm_source_file(node.get("source_file"), root) or "",
            "source_location": node.get("source_location") or "",
            "community": 0,
            "community_name": "",
        })

    # --- collect edge rows (single table) ---
    edge_rows: list[dict] = []

    for edge in edges:
        src_id = _normalize_id(edge.get("source") or edge.get("from", ""))
        tgt_id = _normalize_id(edge.get("target") or edge.get("to", ""))
        if not src_id or not tgt_id:
            continue
        if src_id not in node_types or tgt_id not in node_types:
            continue
        edge_rows.append({
            "from_id": src_id,
            "to_id": tgt_id,
            "relation": edge.get("relation", ""),
            "confidence": edge.get("confidence", ""),
            "confidence_score": float(edge.get("confidence_score", 0.0)),
            "source_file": _norm_source_file(edge.get("source_file"), root) or "",
            "weight": float(edge.get("weight", 1.0)),
        })

    # --- write CSV + COPY FROM in a temp dir ---
    tmp_dir = tempfile.mkdtemp(prefix="graphify_bulk_")
    try:
        if node_rows:
            csv_path = os.path.join(tmp_dir, "nodes.csv")
            _write_csv(csv_path, node_rows, _NODE_COLUMNS)
            _copy_node_csv(conn, csv_path)

        if edge_rows:
            csv_path = os.path.join(tmp_dir, "edges.csv")
            _write_csv(csv_path, edge_rows, _EDGE_COLUMNS)
            _copy_rel_csv(conn, csv_path)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return node_types


def _incremental_ingest(
    conn: object,
    extraction: dict,
    *,
    prune_sources: list[str] | None = None,
    root: str | None = None,
    known_tables: set[str] | None = None,
) -> dict[str, str]:
    """Incremental update via DELETE affected source_files + COPY FROM.

    Much faster than per-row MERGE: deletes nodes whose source_file appears
    in the incoming extraction (or in prune_sources), then bulk-inserts the
    new data via COPY FROM.  Incoming cross-file edges (from unchanged files
    into affected nodes) are saved before deletion and restored afterwards.
    """
    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []

    # --- collect affected source_files from the incoming data ---
    affected_sfs: set[str] = set()
    if prune_sources:
        for sf in prune_sources:
            sf_norm = _norm_source_file(sf, root) or sf
            affected_sfs.add(sf_norm)

    node_types: dict[str, str] = {}
    node_rows: list[dict] = []
    written_ids: set[str] = set()

    for node in nodes:
        nid = _normalize_id(node.get("id", ""))
        if not nid or nid in written_ids:
            continue
        written_ids.add(nid)
        ft = _fix_file_type(node.get("file_type"))
        node_types[nid] = ft
        sf = _norm_source_file(node.get("source_file"), root) or ""
        if sf:
            affected_sfs.add(sf)
        node_rows.append({
            "id": nid,
            "label": node.get("label", ""),
            "file_type": ft,
            "source_file": sf,
            "source_location": node.get("source_location") or "",
            "community": 0,
            "community_name": "",
        })

    # --- resolve types for non-delta edge endpoints (before DELETE) ---
    unknown_ids: set[str] = set()
    for edge in edges:
        for key in ("source", "from", "target", "to"):
            eid = _normalize_id(edge.get(key, ""))
            if eid and eid not in node_types:
                unknown_ids.add(eid)
    for nid in unknown_ids:
        try:
            rows = list(conn.execute(
                "MATCH (n:node {id: $nid}) RETURN n.file_type",
                parameters={"nid": nid},
            ))
            if rows:
                node_types[nid] = rows[0][0]
        except RuntimeError:
            pass

    # --- save incoming cross-file edges before DELETE ---
    affected_node_ids: set[str] = set()
    for sf in affected_sfs:
        try:
            for row in conn.execute(
                "MATCH (n:node) WHERE n.source_file = $sf RETURN n.id",
                parameters={"sf": sf},
            ):
                affected_node_ids.add(row[0])
        except RuntimeError:
            pass

    saved_edge_rows: list[dict] = []

    for sf in affected_sfs:
        try:
            rows = list(conn.execute(
                "MATCH (a:node)-[e:edge]->(b:node) "
                "WHERE b.source_file = $sf "
                "RETURN a.id, b.id, e.relation, e.confidence, "
                "e.confidence_score, e.source_file, e.weight",
                parameters={"sf": sf},
            ))
        except RuntimeError:
            continue

        for row in rows:
            if row[0] in affected_node_ids:
                continue
            saved_edge_rows.append({
                "from_id": row[0], "to_id": row[1],
                "relation": row[2] or "",
                "confidence": row[3] or "",
                "confidence_score": float(row[4] or 0.0),
                "source_file": row[5] or "",
                "weight": float(row[6] or 1.0),
            })

    # --- DELETE nodes from affected source_files ---
    for sf in affected_sfs:
        conn.execute(
            "MATCH (n:node) WHERE n.source_file = $sf DETACH DELETE n",
            parameters={"sf": sf},
        )

    # --- collect delta edge rows ---
    edge_rows: list[dict] = []

    for edge in edges:
        src_id = _normalize_id(edge.get("source") or edge.get("from", ""))
        tgt_id = _normalize_id(edge.get("target") or edge.get("to", ""))
        if not src_id or not tgt_id:
            continue
        if src_id not in node_types or tgt_id not in node_types:
            continue
        edge_rows.append({
            "from_id": src_id,
            "to_id": tgt_id,
            "relation": edge.get("relation", ""),
            "confidence": edge.get("confidence", ""),
            "confidence_score": float(edge.get("confidence_score", 0.0)),
            "source_file": _norm_source_file(edge.get("source_file"), root) or "",
            "weight": float(edge.get("weight", 1.0)),
        })

    # --- merge saved incoming edges back ---
    edge_rows.extend(saved_edge_rows)

    # --- COPY FROM bulk insert ---
    tmp_dir = tempfile.mkdtemp(prefix="graphify_inc_")
    try:
        if node_rows:
            csv_path = os.path.join(tmp_dir, "nodes.csv")
            _write_csv(csv_path, node_rows, _NODE_COLUMNS)
            _copy_node_csv(conn, csv_path)

        if edge_rows:
            csv_path = os.path.join(tmp_dir, "edges.csv")
            _write_csv(csv_path, edge_rows, _EDGE_COLUMNS)
            _copy_rel_csv(conn, csv_path)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return node_types


def ingest_extraction(
    conn: object,
    extraction: dict,
    *,
    incremental: bool = False,
    prune_sources: list[str] | None = None,
    root: str | Path | None = None,
    known_tables: set[str] | None = None,
) -> dict[str, str]:
    """Write an extraction dict into NeuG.

    incremental=False: first build — uses COPY FROM bulk loading.
    incremental=True:  update — uses DELETE + COPY FROM.

    Returns node_types dict (id -> file_type) for use by ingest_communities.
    """
    _root = str(Path(root).resolve()) if root else None

    if incremental:
        return _incremental_ingest(
            conn, extraction,
            prune_sources=prune_sources, root=_root,
            known_tables=known_tables,
        )
    else:
        return _bulk_ingest(
            conn, extraction,
            root=_root, known_tables=known_tables,
        )


def ingest_communities(
    conn: object,
    communities: dict[int, list[str]],
    community_labels: dict[int, str] | None = None,
    node_types: dict[str, str] | None = None,
) -> None:
    """Write community assignments into NeuG node properties.

    Single-table schema: all nodes are in the ``node`` table, so a single
    MATCH per node suffices regardless of file_type.

    If community_labels is provided, community_name is also written.

    Note: NeuG does not support parameterised SET for non-string values,
    so community ID is interpolated as an integer literal.  The id value
    uses a parameterised query.
    """
    _labels = community_labels or {}
    for cid, node_ids in communities.items():
        cid_int = int(cid)
        cname = _labels.get(cid_int, _labels.get(cid, ""))
        for nid in node_ids:
            nid_norm = _normalize_id(nid)
            if not nid_norm:
                continue
            if cname:
                conn.execute(
                    f"MATCH (n:node) WHERE n.id = $nid "
                    f"SET n.community = {cid_int}, n.community_name = $cname",
                    parameters={"nid": nid_norm, "cname": cname},
                )
            else:
                conn.execute(
                    f"MATCH (n:node) WHERE n.id = $nid "
                    f"SET n.community = {cid_int}",
                    parameters={"nid": nid_norm},
                )


def execute_cypher(conn: object, query: str) -> list[list]:
    """Execute a Cypher query and return results as list of lists."""
    try:
        return list(conn.execute(query))
    except RuntimeError as exc:
        raise RuntimeError(f"Cypher query failed: {exc}") from exc


def close_db(db: object, conn: object) -> None:
    """Close the NeuG connection and database."""
    conn.close()
    db.close()


def export_to_json(conn: object, *, hyperedges: list | None = None) -> dict:
    """Export the NeuG graph to a NetworkX ``node_link_data``-compatible dict.

    This avoids any dependency on NetworkX — the dict is assembled directly
    from Cypher query results and can be consumed by ``json_graph.node_link_graph``.
    """
    from graphify.export import _strip_diacritics, _git_head

    nodes: list[dict] = []
    for row in conn.execute(
        "MATCH (n:node) RETURN n.id, n.label, n.file_type, "
        "n.source_file, n.source_location, n.community, n.community_name"
    ):
        nodes.append({
            "id": row[0],
            "label": row[1] or "",
            "file_type": row[2] or "concept",
            "source_file": row[3] or "",
            "source_location": row[4] or "",
            "community": row[5] if row[5] is not None else 0,
            "community_name": row[6] or "",
            "norm_label": _strip_diacritics(row[1] or "").lower(),
        })

    links: list[dict] = []
    for row in conn.execute(
        "MATCH (a:node)-[e:edge]->(b:node) "
        "RETURN a.id, b.id, e.relation, e.confidence, "
        "e.confidence_score, e.source_file, e.weight"
    ):
        links.append({
            "source": row[0],
            "target": row[1],
            "relation": row[2] or "",
            "confidence": row[3] or "EXTRACTED",
            "confidence_score": float(row[4]) if row[4] is not None else 1.0,
            "source_file": row[5] or "",
            "weight": float(row[6]) if row[6] is not None else 1.0,
        })

    commit = _git_head()
    data: dict = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": nodes,
        "links": links,
        "hyperedges": hyperedges or [],
    }
    if commit:
        data["built_at_commit"] = commit
    return data
