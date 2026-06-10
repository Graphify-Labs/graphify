"""NeuG graph database adapter for graphify.

Provides an optional parallel storage engine alongside NetworkX.
NeuG is lazily imported — when not installed, callers should catch
ImportError at the call site and skip silently.

All property values interpolated into Cypher statements use NeuG's native
parameterised queries ($param syntax) to prevent injection.  Table/label
names (which come from a fixed internal set, not user input) are still
interpolated as identifiers.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from pathlib import Path

from .build import _FILE_TYPE_SYNONYMS, _normalize_id, _norm_source_file
from .validate import VALID_FILE_TYPES

# ---------------------------------------------------------------------------
# Node tables (one per file_type)
# ---------------------------------------------------------------------------

_NODE_TABLES = {
    "code": """CREATE NODE TABLE IF NOT EXISTS code (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, source_location STRING, community INT64)""",
    "document": """CREATE NODE TABLE IF NOT EXISTS document (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "paper": """CREATE NODE TABLE IF NOT EXISTS paper (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "image": """CREATE NODE TABLE IF NOT EXISTS image (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "concept": """CREATE NODE TABLE IF NOT EXISTS concept (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
    "rationale": """CREATE NODE TABLE IF NOT EXISTS rationale (
        id STRING PRIMARY KEY, label STRING,
        source_file STRING, community INT64)""",
}

_NODE_COLUMNS = {
    "code": ["id", "label", "source_file", "source_location", "community"],
    "document": ["id", "label", "source_file", "community"],
    "paper": ["id", "label", "source_file", "community"],
    "image": ["id", "label", "source_file", "community"],
    "concept": ["id", "label", "source_file", "community"],
    "rationale": ["id", "label", "source_file", "community"],
}

_EDGE_COLUMNS = ["from_id", "to_id", "relation", "confidence",
                 "confidence_score", "source_file", "weight"]

# ---------------------------------------------------------------------------
# Edge tables — split by (src_type, tgt_type, relation).
# ---------------------------------------------------------------------------

_EDGE_DDL_TEMPLATE = """CREATE REL TABLE IF NOT EXISTS {tbl}(
    FROM {src} TO {tgt},
    relation STRING, confidence STRING,
    confidence_score DOUBLE, source_file STRING, weight DOUBLE)"""

# Known relation types per (src, tgt) pair — pre-built at init time.
_KNOWN_RELATIONS: dict[tuple[str, str], list[str]] = {
    ("code", "code"): [
        "calls", "contains", "method", "uses", "inherits", "defines",
        "references", "imports", "imports_from", "listened_by", "case_of",
        "references_constant", "bound_to", "uses_static_prop", "uses_config",
    ],
    ("rationale", "code"): ["rationale_for"],
}


def _sanitize_rel_name(relation: str) -> str:
    """Normalize a relation string into a safe table-name suffix."""
    r = relation.lower().strip()
    r = re.sub(r"[^a-z0-9_]", "_", r)
    r = re.sub(r"_+", "_", r).strip("_")
    return r or "rel"


def _edge_table_name(src_type: str, tgt_type: str, relation: str) -> str:
    return f"edge_{src_type}_{tgt_type}_{_sanitize_rel_name(relation)}"


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


def _copy_node_csv(conn: object, csv_path: str, table: str) -> None:
    conn.execute(
        f'COPY {table} FROM "{csv_path}" (header=true, delim=",", escaping=false)'
    )


def _copy_rel_csv(conn: object, csv_path: str, tbl: str,
                  src_table: str, tgt_table: str) -> None:
    conn.execute(
        f'COPY {tbl} FROM "{csv_path}" '
        f'(from="{src_table}", to="{tgt_table}", '
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
    """Populate known table registry; optionally execute DDL.

    create_tables=True  (first build): run CREATE TABLE statements.
    create_tables=False (incremental): only build the registry set
                        so _ensure_rel_table() knows what exists.

    Returns the set of known rel table names (per-connection registry).
    """
    created: set[str] = set()

    if create_tables:
        for ddl in _NODE_TABLES.values():
            conn.execute(ddl)

    for (src, tgt), rels in _KNOWN_RELATIONS.items():
        for rel in rels:
            tbl = _edge_table_name(src, tgt, rel)
            if create_tables:
                conn.execute(_EDGE_DDL_TEMPLATE.format(tbl=tbl, src=src, tgt=tgt))
            created.add(tbl)

    return created


def _ensure_rel_table(
    conn: object, src_type: str, tgt_type: str, relation: str,
    known: set[str],
) -> str:
    """Resolve edge table name, creating on-the-fly if needed. Returns table name."""
    tbl = _edge_table_name(src_type, tgt_type, relation)
    if tbl in known:
        return tbl
    conn.execute(_EDGE_DDL_TEMPLATE.format(tbl=tbl, src=src_type, tgt=tgt_type))
    known.add(tbl)
    return tbl


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
    _known = known_tables if known_tables is not None else set()
    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []

    # --- collect node rows grouped by file_type ---
    node_types: dict[str, str] = {}
    node_buckets: dict[str, list[dict]] = {ft: [] for ft in _NODE_TABLES}
    written_ids: set[str] = set()

    for node in nodes:
        nid = _normalize_id(node.get("id", ""))
        if not nid or nid in written_ids:
            continue
        written_ids.add(nid)
        ft = _fix_file_type(node.get("file_type"))
        node_types[nid] = ft
        row: dict = {
            "id": nid,
            "label": node.get("label", ""),
            "source_file": _norm_source_file(node.get("source_file"), root) or "",
            "community": 0,
        }
        if ft == "code":
            row["source_location"] = node.get("source_location") or ""
        node_buckets.setdefault(ft, []).append(row)

    # --- collect edge rows grouped by rel table ---
    edge_buckets: dict[str, list[dict]] = {}
    edge_table_types: dict[str, tuple[str, str]] = {}

    for edge in edges:
        src_id = _normalize_id(edge.get("source") or edge.get("from", ""))
        tgt_id = _normalize_id(edge.get("target") or edge.get("to", ""))
        if not src_id or not tgt_id:
            continue
        src_ft = node_types.get(src_id)
        tgt_ft = node_types.get(tgt_id)
        if not src_ft or not tgt_ft:
            continue

        rel_raw = edge.get("relation", "")
        tbl = _ensure_rel_table(conn, src_ft, tgt_ft, rel_raw, _known)
        edge_table_types[tbl] = (src_ft, tgt_ft)
        edge_buckets.setdefault(tbl, []).append({
            "from_id": src_id,
            "to_id": tgt_id,
            "relation": rel_raw,
            "confidence": edge.get("confidence", ""),
            "confidence_score": float(edge.get("confidence_score", 0.0)),
            "source_file": _norm_source_file(edge.get("source_file"), root) or "",
            "weight": float(edge.get("weight", 1.0)),
        })

    # --- write CSV + COPY FROM in a temp dir ---
    tmp_dir = tempfile.mkdtemp(prefix="graphify_bulk_")
    try:
        for ft, rows in node_buckets.items():
            if not rows:
                continue
            csv_path = os.path.join(tmp_dir, f"node_{ft}.csv")
            _write_csv(csv_path, rows, _NODE_COLUMNS[ft])
            _copy_node_csv(conn, csv_path, ft)

        for tbl, rows in edge_buckets.items():
            if not rows:
                continue
            csv_path = os.path.join(tmp_dir, f"edge_{tbl}.csv")
            _write_csv(csv_path, rows, _EDGE_COLUMNS)
            src_ft, tgt_ft = edge_table_types[tbl]
            _copy_rel_csv(conn, csv_path, tbl, src_ft, tgt_ft)
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
    _known = known_tables if known_tables is not None else set()
    nodes = extraction.get("nodes") or []
    edges = extraction.get("edges") or []

    # --- collect affected source_files from the incoming data ---
    affected_sfs: set[str] = set()
    if prune_sources:
        for sf in prune_sources:
            sf_norm = _norm_source_file(sf, root) or sf
            affected_sfs.add(sf_norm)

    node_types: dict[str, str] = {}
    node_buckets: dict[str, list[dict]] = {ft: [] for ft in _NODE_TABLES}
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
        row: dict = {
            "id": nid,
            "label": node.get("label", ""),
            "source_file": sf,
            "community": 0,
        }
        if ft == "code":
            row["source_location"] = node.get("source_location") or ""
        node_buckets.setdefault(ft, []).append(row)

    # --- resolve types for non-delta edge endpoints (before DELETE) ---
    unknown_ids: set[str] = set()
    for edge in edges:
        for key in ("source", "from", "target", "to"):
            eid = _normalize_id(edge.get(key, ""))
            if eid and eid not in node_types:
                unknown_ids.add(eid)
    for nid in unknown_ids:
        for tbl in _NODE_TABLES:
            try:
                rows = list(conn.execute(
                    f"MATCH (n:{tbl} {{id: $nid}}) RETURN 1",
                    parameters={"nid": nid},
                ))
                if rows:
                    node_types[nid] = tbl
                    break
            except RuntimeError:
                pass

    # --- save incoming cross-file edges before DELETE ---
    # Collect IDs of nodes that will be deleted.
    affected_node_ids: set[str] = set()
    for sf in affected_sfs:
        for tbl in _NODE_TABLES:
            try:
                for row in conn.execute(
                    f"MATCH (n:{tbl}) WHERE n.source_file = $sf RETURN n.id",
                    parameters={"sf": sf},
                ):
                    affected_node_ids.add(row[0])
            except RuntimeError:
                pass

    # For each known edge table, find edges where the target is in an affected
    # source_file but the source is NOT (incoming from unchanged files).
    saved_edge_buckets: dict[str, list[dict]] = {}
    saved_edge_types: dict[str, tuple[str, str]] = {}

    for tbl in list(_known):
        parts = tbl.split("_", 3)
        if len(parts) < 4 or parts[0] != "edge":
            continue
        src_type, tgt_type = parts[1], parts[2]

        for sf in affected_sfs:
            try:
                rows = list(conn.execute(
                    f"MATCH (a:{src_type})-[e:{tbl}]->(b:{tgt_type}) "
                    f"WHERE b.source_file = $sf "
                    f"RETURN a.id, b.id, e.relation, e.confidence, "
                    f"e.confidence_score, e.source_file, e.weight",
                    parameters={"sf": sf},
                ))
            except RuntimeError:
                continue

            for row in rows:
                if row[0] in affected_node_ids:
                    continue
                saved_edge_types[tbl] = (src_type, tgt_type)
                saved_edge_buckets.setdefault(tbl, []).append({
                    "from_id": row[0], "to_id": row[1],
                    "relation": row[2] or "",
                    "confidence": row[3] or "",
                    "confidence_score": float(row[4] or 0.0),
                    "source_file": row[5] or "",
                    "weight": float(row[6] or 1.0),
                })

    # --- DELETE nodes from affected source_files ---
    for sf in affected_sfs:
        for tbl in _NODE_TABLES:
            conn.execute(
                f"MATCH (n:{tbl}) WHERE n.source_file = $sf DETACH DELETE n",
                parameters={"sf": sf},
            )

    # --- collect delta edge rows ---
    edge_buckets: dict[str, list[dict]] = {}
    edge_table_types: dict[str, tuple[str, str]] = {}

    for edge in edges:
        src_id = _normalize_id(edge.get("source") or edge.get("from", ""))
        tgt_id = _normalize_id(edge.get("target") or edge.get("to", ""))
        if not src_id or not tgt_id:
            continue
        src_ft = node_types.get(src_id)
        tgt_ft = node_types.get(tgt_id)
        if not src_ft or not tgt_ft:
            continue

        rel_raw = edge.get("relation", "")
        tbl = _ensure_rel_table(conn, src_ft, tgt_ft, rel_raw, _known)
        edge_table_types[tbl] = (src_ft, tgt_ft)
        edge_buckets.setdefault(tbl, []).append({
            "from_id": src_id,
            "to_id": tgt_id,
            "relation": rel_raw,
            "confidence": edge.get("confidence", ""),
            "confidence_score": float(edge.get("confidence_score", 0.0)),
            "source_file": _norm_source_file(edge.get("source_file"), root) or "",
            "weight": float(edge.get("weight", 1.0)),
        })

    # --- merge saved incoming edges back ---
    for tbl, rows in saved_edge_buckets.items():
        edge_buckets.setdefault(tbl, []).extend(rows)
        if tbl not in edge_table_types:
            edge_table_types[tbl] = saved_edge_types[tbl]

    # --- COPY FROM bulk insert ---
    tmp_dir = tempfile.mkdtemp(prefix="graphify_inc_")
    try:
        for ft, rows in node_buckets.items():
            if not rows:
                continue
            csv_path = os.path.join(tmp_dir, f"node_{ft}.csv")
            _write_csv(csv_path, rows, _NODE_COLUMNS[ft])
            _copy_node_csv(conn, csv_path, ft)

        for tbl, rows in edge_buckets.items():
            if not rows:
                continue
            csv_path = os.path.join(tmp_dir, f"edge_{tbl}.csv")
            _write_csv(csv_path, rows, _EDGE_COLUMNS)
            src_ft, tgt_ft = edge_table_types[tbl]
            _copy_rel_csv(conn, csv_path, tbl, src_ft, tgt_ft)
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
    incremental=True:  update — uses MERGE (upsert) per row.

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

    If node_types is provided (id -> file_type mapping from ingest_extraction),
    each node is looked up in its specific table directly.  Otherwise falls
    back to probing all 6 tables (slower).

    Note: NeuG does not support parameterised SET for non-string values,
    so community ID is interpolated as an integer literal.  The id value
    uses a parameterised query.
    """
    for cid, node_ids in communities.items():
        cid_int = int(cid)
        for nid in node_ids:
            nid_norm = _normalize_id(nid)
            if not nid_norm:
                continue
            if node_types and nid_norm in node_types:
                tbl = node_types[nid_norm]
                conn.execute(
                    f"MATCH (n:{tbl}) WHERE n.id = $nid "
                    f"SET n.community = {cid_int}",
                    parameters={"nid": nid_norm},
                )
            else:
                for tbl in _NODE_TABLES:
                    conn.execute(
                        f"MATCH (n:{tbl}) WHERE n.id = $nid "
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
