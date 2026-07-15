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

    Uses a single ``CASE WHEN`` batch statement for all nodes (verified
    working in neug).  NeuG does not support ``UNWIND $param`` or
    ``SET n.prop = $param``, so community IDs and names are inlined.

    If community_labels is provided, community_name is also written in a
    separate per-community pass (inline values, not parameters).
    """
    # Build comm_map: node_id -> community_id (int)
    comm_map: dict[str, int] = {}
    for cid, node_ids in communities.items():
        cid_int = int(cid)
        for nid in node_ids:
            nid_norm = _normalize_id(nid)
            if nid_norm:
                comm_map[nid_norm] = cid_int

    # Batch writeback community IDs via CASE WHEN (neug pattern)
    when_clauses = " ".join(
        f"WHEN n.id = '{nid}' THEN {cid}" for nid, cid in comm_map.items()
    )
    conn.execute(
        f"MATCH (n:node) "
        f"SET n.community = CASE {when_clauses} ELSE n.community END;"
    )

    # Write community_name per-community (inline values, not $param)
    if community_labels:
        for cid, name in community_labels.items():
            cid_int = int(cid)
            safe_name = (name or "").replace("'", "\\'")
            conn.execute(
                f"MATCH (n:node) WHERE n.community = {cid_int} "
                f"SET n.community_name = '{safe_name}'"
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


# ---------------------------------------------------------------------------
# Shared row-based filter functions (mirror of analyze.py NetworkX filters)
# ---------------------------------------------------------------------------
# Used by find_god_nodes and find_surprising_connections to filter Cypher
# query results without depending on NetworkX graph objects.

from graphify.analyze import _BUILTIN_NOISE_LABELS, _JSON_NOISE_LABELS


def _is_file_node_row(label: str, source_file: str, degree: int) -> bool:
    """File hub / method stub — row-based mirror of analyze._is_file_node."""
    if not label:
        return False
    # File-level hub: label matches source filename
    if source_file and label == Path(source_file).name:
        return True
    # Method stub: .method_name() — ALWAYS exclude regardless of degree (analyze.py:74)
    if label.startswith(".") and label.endswith("()"):
        return True
    # Function stub: func() with degree <= 1 (analyze.py:78)
    if label.endswith("()") and degree <= 1:
        return True
    return False


def _is_concept_node_row(source_file: str) -> bool:
    """Concept node — row-based mirror of analyze._is_concept_node."""
    if not source_file:
        return True
    if "." not in source_file.split("/")[-1]:
        return True
    return False


def _is_json_key_node_row(label: str, source_file: str) -> bool:
    """JSON key noise — row-based mirror of analyze._is_json_key_node."""
    src = (source_file or "").lower()
    if not src.endswith(".json"):
        return False
    return (label or "").strip().lower() in _JSON_NOISE_LABELS


# ---------------------------------------------------------------------------
# Community detection via neug GDS Leiden
# ---------------------------------------------------------------------------


def run_leiden(conn: object) -> dict[int, list[str]]:
    """Run neug GDS Leiden community detection.

    Returns ``{community_id: [node_ids]}``.
    neug leiden guarantees stable community IDs — no re-indexing needed.
    """
    # Check for empty graph
    node_rows = list(conn.execute("MATCH (n:node) RETURN n.id"))
    if not node_rows:
        return {}

    edge_rows = list(conn.execute("MATCH ()-[e:edge]->() RETURN count(*)"))
    if edge_rows and edge_rows[0][0] == 0:
        # No edges: each node is its own community
        return {i: [row[0]] for i, row in enumerate(node_rows)}

    # Load GDS extension first (needed for project_graph and leiden)
    try:
        conn.execute("LOAD gds;")
    except RuntimeError:
        conn.execute("INSTALL gds;")
        conn.execute("LOAD gds;")

    # Project graph for GDS algorithms
    conn.execute("CALL project_graph('g', ['node'], {'[node, edge, node]': ''})")

    # Run Leiden
    results = list(conn.execute(
        "CALL leiden('g', {concurrency: 1}) "
        "YIELD node, community "
        "RETURN node.id, community"
    ))

    # Clean up projected graph
    try:
        conn.execute("CALL drop_projected_graph('g')")
    except RuntimeError:
        pass

    communities: dict[int, list[str]] = {}
    for nid, cid in results:
        communities.setdefault(int(cid), []).append(nid)

    return communities


# ---------------------------------------------------------------------------
# Cohesion + community labeling
# ---------------------------------------------------------------------------


def compute_cohesion(
    conn: object, communities: dict[int, list[str]]
) -> dict[int, float]:
    """Per-community cohesion: undirected internal edges / max possible.

    Uses a single edge scan with ``frozenset`` deduplication to convert
    directed edges to undirected, aligning with NetworkX's ``Graph`` semantics.
    """
    node_comm = {n: cid for cid, nodes in communities.items() for n in nodes}
    intra: dict[int, set] = {cid: set() for cid in communities}

    for row in conn.execute("MATCH (a:node)-[:edge]->(b:node) RETURN a.id, b.id"):
        a, b = row[0], row[1]
        if a == b:  # skip self-loops
            continue
        ca = node_comm.get(a)
        if ca is not None and ca == node_comm.get(b):
            intra[ca].add(frozenset((a, b)))  # deduplicate directed edges

    result: dict[int, float] = {}
    for cid, nodes in communities.items():
        n = len(nodes)
        if n <= 1:
            result[cid] = 1.0
            continue
        possible = n * (n - 1) / 2
        result[cid] = len(intra[cid]) / possible if possible > 0 else 1.0

    return result


def label_communities_by_hub(
    conn: object, communities: dict[int, list[str]]
) -> dict[int, str]:
    """Name each community after its highest-degree member.

    Requires community IDs to be written to the db beforehand.
    """
    try:
        rows = list(conn.execute(
            "MATCH (n:node) "
            "WHERE n.community IS NOT NULL "
            "OPTIONAL MATCH (n)-[e:edge]-() "
            "WITH n, n.community AS cid, count(e) AS degree "
            "ORDER BY cid, degree DESC, n.id ASC "
            "WITH cid, collect(n)[0] AS hub "
            "RETURN cid, hub.label, hub.id"
        ))
        labels: dict[int, str] = {}
        for cid, label, nid in rows:
            name = (label or nid or "").strip()
            if name and name.endswith("()"):
                name = name[:-2]
            labels[int(cid)] = name or f"Community {cid}"
    except RuntimeError:
        # Fallback: two-step approach
        deg_rows = list(conn.execute(
            "MATCH (n:node)-[e:edge]-() "
            "WITH n, count(e) AS degree "
            "RETURN n.id, n.community, n.label, degree "
            "ORDER BY n.community, degree DESC, n.id"
        ))
        labels = {}
        seen: set[int] = set()
        for nid, cid, label, degree in deg_rows:
            if cid is not None and int(cid) not in seen:
                seen.add(int(cid))
                name = (label or nid or "").strip()
                if name and name.endswith("()"):
                    name = name[:-2]
                labels[int(cid)] = name or f"Community {cid}"

    # Communities with no nodes in the query result
    for cid in communities:
        if int(cid) not in labels:
            labels[int(cid)] = f"Community {cid}"

    return labels


# ---------------------------------------------------------------------------
# God nodes
# ---------------------------------------------------------------------------


def find_god_nodes(conn: object, top_n: int = 10) -> list[dict]:
    """Top-N most-connected real entities.

    Cypher pre-filters noise labels; Python applies complex filters
    (file hub, concept node, JSON key, method stub) via shared row-based functions.
    """
    # Build inline noise list (neug doesn't support IN $param)
    noise_list = "[" + ", ".join(f"'{l}'" for l in _BUILTIN_NOISE_LABELS) + "]"

    rows = list(conn.execute(
        f"MATCH (n:node)-[e:edge]-() "
        f"WITH n, count(e) AS degree "
        f"WHERE degree > 0 "
        f"  AND NOT (n.label IN {noise_list}) "
        f"RETURN n.id, n.label, n.file_type, n.source_file, degree "
        f"ORDER BY degree DESC, n.id ASC "
        f"LIMIT {top_n * 5}"
    ))

    gods: list[dict] = []
    for nid, label, ft, source_file, degree in rows:
        label = label or ""
        source_file = source_file or ""
        if not label:
            continue
        if _is_file_node_row(label, source_file, degree):
            continue
        if _is_concept_node_row(source_file):
            continue
        if _is_json_key_node_row(label, source_file):
            continue
        if label in _BUILTIN_NOISE_LABELS:  # Cypher already filtered, this is a safety net
            continue
        gods.append({"id": nid, "label": label, "degree": degree})
        if len(gods) >= top_n:
            break

    return gods


# ---------------------------------------------------------------------------
# Surprising connections
# ---------------------------------------------------------------------------


def _surprise_score_row(
    relation: str,
    conf: str,
    u_source: str,
    v_source: str,
    cid_u: int | None,
    cid_v: int | None,
    deg_u: int,
    deg_v: int,
) -> tuple[int, list[str]]:
    """Score how surprising a cross-file edge is (row-based mirror of analyze._surprise_score)."""
    from graphify.analyze import _file_category, _top_level_dir, _cross_language

    score = 0
    reasons: list[str] = []

    # 1. Confidence weight
    conf_bonus = {"AMBIGUOUS": 3, "INFERRED": 2, "EXTRACTED": 1}.get(conf, 1)

    cat_u = _file_category(u_source)
    cat_v = _file_category(v_source)

    # 2. Suppress structural bonuses for INFERRED calls/uses that cross language
    #    boundaries or connect code to doc (resolver pollution)
    _suppress_structural = (
        conf == "INFERRED"
        and relation in ("calls", "uses")
        and (_cross_language(u_source, v_source) or {cat_u, cat_v} == {"code", "doc"})
    )
    if _suppress_structural:
        conf_bonus = 0

    score += conf_bonus
    if conf in ("AMBIGUOUS", "INFERRED"):
        reasons.append(f"{conf.lower()} connection - not explicitly stated in source")

    # 3. Cross file-type bonus
    if cat_u != cat_v and not _suppress_structural:
        score += 2
        reasons.append(f"crosses file types ({cat_u} ↔ {cat_v})")

    # 4. Cross-repo bonus
    if _top_level_dir(u_source) != _top_level_dir(v_source) and not _suppress_structural:
        score += 2
        reasons.append("connects across different repos/directories")

    # 5. Cross-community bonus
    if (cid_u is not None and cid_v is not None and cid_u != cid_v
            and not _suppress_structural):
        score += 1
        reasons.append("bridges separate communities")

    # 6. Semantic similarity bonus
    if relation == "semantically_similar_to":
        score = int(score * 1.5)
        reasons.append("semantically similar concepts with no structural link")

    # 7. Peripheral → hub
    if min(deg_u, deg_v) <= 2 and max(deg_u, deg_v) >= 5:
        score += 1
        reasons.append("peripheral node unexpectedly reaches hub")

    return score, reasons


def find_surprising_connections(
    conn: object,
    communities: dict[int, list[str]],
    top_n: int = 5,
) -> list[dict]:
    """Cross-file or cross-community edges ranked by composite surprise score."""
    # 1. Determine multi-source vs single-source
    source_count = list(conn.execute(
        "MATCH (n:node) WHERE n.source_file <> '' "
        "RETURN count(DISTINCT n.source_file) AS cnt"
    ))
    is_multi_source = source_count[0][0] > 1 if source_count else False

    # 2. Pre-compute degrees
    deg_rows = list(conn.execute(
        "MATCH (n:node)-[e:edge]-() "
        "WITH n, count(e) AS degree "
        "RETURN n.id, degree"
    ))
    degrees = {r[0]: r[1] for r in deg_rows}

    # 3. Get candidate edges
    structural_list = "['imports', 'imports_from', 'contains', 'method']"

    if is_multi_source:
        rows = list(conn.execute(
            f"MATCH (a:node)-[e:edge]->(b:node) "
            f"WHERE a.source_file <> '' AND b.source_file <> '' "
            f"  AND a.source_file <> b.source_file "
            f"  AND NOT (e.relation IN {structural_list}) "
            f"RETURN a.id, a.label, a.source_file, a.community, "
            f"       b.id, b.label, b.source_file, b.community, "
            f"       e.relation, e.confidence"
        ))
    else:
        rows = list(conn.execute(
            f"MATCH (a:node)-[e:edge]->(b:node) "
            f"WHERE a.community IS NOT NULL AND b.community IS NOT NULL "
            f"  AND a.community <> b.community "
            f"  AND NOT (e.relation IN {structural_list}) "
            f"RETURN a.id, a.label, a.source_file, a.community, "
            f"       b.id, b.label, b.source_file, b.community, "
            f"       e.relation, e.confidence"
        ))

    # 4. Python filtering + scoring
    node_comm = {n: cid for cid, nodes in communities.items() for n in nodes}
    candidates: list[dict] = []

    for (a_id, a_label, a_src, a_comm, b_id, b_label, b_src, b_comm,
         relation, conf) in rows:
        a_label = a_label or ""
        a_src = a_src or ""
        b_label = b_label or ""
        b_src = b_src or ""
        relation = relation or ""
        conf = conf or "EXTRACTED"

        deg_a = degrees.get(a_id, 0)
        deg_b = degrees.get(b_id, 0)

        # Filter concept/file-hub nodes
        if _is_concept_node_row(a_src) or _is_concept_node_row(b_src):
            continue
        if _is_file_node_row(a_label, a_src, deg_a) or _is_file_node_row(b_label, b_src, deg_b):
            continue

        cid_u = a_comm if a_comm is not None else node_comm.get(a_id)
        cid_v = b_comm if b_comm is not None else node_comm.get(b_id)

        score, reasons = _surprise_score_row(
            relation, conf, a_src, b_src, cid_u, cid_v, deg_a, deg_b
        )

        candidates.append({
            "_score": score,
            "source": a_label,
            "target": b_label,
            "source_files": [a_src, b_src],
            "confidence": conf,
            "relation": relation,
            "why": "; ".join(reasons) if reasons else "cross-file semantic connection",
            "_pair": tuple(sorted([cid_u or 0, cid_v or 0])) if not is_multi_source else None,
        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["_score"], reverse=True)

    # Single-source: deduplicate by community pair
    if not is_multi_source:
        seen_pairs: set[tuple] = set()
        deduped: list[dict] = []
        for c in candidates:
            pair = c.pop("_pair", None)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                deduped.append(c)
        candidates = deduped
    else:
        for c in candidates:
            c.pop("_pair", None)

    # Strip _score from output
    for c in candidates:
        c.pop("_score", None)

    return candidates[:top_n]


# ---------------------------------------------------------------------------
# Orchestration: neug clustered path
# ---------------------------------------------------------------------------


def cluster_by_neug(
    conn: object,
    *,
    merged: dict,
    graph_json_path: object,
    analysis_path: object,
    stages: object,
    export_fn: object,
    hyperedges: list | None = None,
) -> None:
    """Orchestrate the neug clustered path.

    Steps: leiden → writeback → label → analysis → export.
    cli.py should call this directly instead of inlining the workflow.
    Returns the exported graph data dict (for summary printing).
    """
    import json

    # 1. Leiden community detection
    communities = run_leiden(conn)
    stages.mark("cluster")

    # 2. Batch writeback community IDs (CASE WHEN)
    ingest_communities(conn, communities)

    # 3. Label communities by hub
    labels = label_communities_by_hub(conn, communities)

    # 4. Write community_name (inline values via ingest_communities)
    ingest_communities(conn, communities, community_labels=labels)

    # 5. Analysis
    cohesion = compute_cohesion(conn, communities)
    gods = find_god_nodes(conn)
    surprises = find_surprising_connections(conn, communities)
    stages.mark("analyze")

    # 6. Export graph.json (with community + community_name)
    data = export_fn(conn, hyperedges=hyperedges or [])
    graph_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    stages.mark("export")

    # 7. Write .graphify_analysis.json
    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "tokens": {
            "input": merged["input_tokens"],
            "output": merged["output_tokens"],
        },
    }
    analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    return data
