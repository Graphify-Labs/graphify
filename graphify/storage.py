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
    node_label: str = "node",
) -> None:
    """Write community assignments into NeuG node properties.

    Uses per-community ``SET`` with ``IN`` clauses instead of a single giant
    ``CASE WHEN`` (which is O(N) parse time for large graphs).
    NeuG does not support ``UNWIND $param`` or ``SET n.prop = $param``, so
    community IDs and names are inlined.

    If community_labels is provided, community_name is also written in a
    separate per-community pass (inline values, not parameters).

    Args:
        node_label: Target node table label (default 'node'; use 'TempFile'
            for file-level clustering on temp tables).
    """
    # Bulk writeback via parameterized per-node SET.
    # Uses neug's primary-key index on n.id for O(log N) lookup per node.
    # CASE WHEN is O(N*M) — too slow for large graphs (28K nodes = 63s).
    # Parameterized SET with index lookup: ~27K queries × O(log N) ≈ 2-3s.
    # For symbol-level nodes (label='node'), IDs are normalized during graph
    # building, so we must normalize again to match.  For file-level TempFile
    # nodes, IDs are raw file paths — _normalize_id would corrupt them.
    normalize = node_label == "node"
    comm_map: dict[str, int] = {}
    for cid, node_ids in communities.items():
        cid_int = int(cid)
        for nid in node_ids:
            nid_key = _normalize_id(nid) if normalize else nid
            if nid_key:
                comm_map[nid_key] = cid_int

    for nid, cid in comm_map.items():
        conn.execute(
            f"MATCH (n:{node_label} {{id: '{nid}'}}) SET n.community = {cid}"
        )

    # Write community_name per-community (inline values, not $param)
    if community_labels:
        for cid, name in community_labels.items():
            cid_int = int(cid)
            safe_name = (name or "").replace("'", "\\'")
            conn.execute(
                f"MATCH (n:{node_label}) WHERE n.community = {cid_int} "
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


_GDS_GRAPH_COUNTER = 0


def _next_graph_name() -> str:
    """Return a unique projected-graph name.

    neug has a bug where re-creating a dropped projected graph with the same
    name makes it invisible to subsequent GDS calls on the same connection.
    Using a unique name each time avoids this.
    """
    global _GDS_GRAPH_COUNTER
    _GDS_GRAPH_COUNTER += 1
    return f"g{_GDS_GRAPH_COUNTER}"


def run_leiden(conn: object, *, resolution: float = 1.0) -> dict[int, list[str]]:
    """Run neug GDS Leiden community detection.

    Args:
        resolution: Leiden resolution parameter (gamma).  > 1 favours smaller
            communities, < 1 favours larger communities.  Default 1.0.

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

    # Use a unique projected-graph name to avoid neug's stale-graph bug
    # (re-creating a dropped graph with the same name makes it invisible
    # to subsequent GDS calls on the same connection).
    gname = _next_graph_name()

    # Project graph for GDS algorithms
    conn.execute(
        f"CALL project_graph('{gname}', ['node'], {{'[node, edge, node]': ''}})"
    )

    # Run Leiden
    results = list(conn.execute(
        f"CALL leiden('{gname}', {{concurrency: 1, resolution: {resolution}}}) "
        "YIELD node, community "
        "RETURN node.id, community"
    ))

    # Clean up projected graph
    try:
        conn.execute(f"CALL drop_projected_graph('{gname}')")
    except RuntimeError:
        pass

    communities: dict[int, list[str]] = {}
    for nid, cid in results:
        communities.setdefault(int(cid), []).append(nid)

    return communities


# ---------------------------------------------------------------------------
# File-level clustering (aggregate symbol edges → file graph → leiden)
# ---------------------------------------------------------------------------


def _aggregate_file_edges(conn: object, csv_path: Path) -> set[str]:
    """Aggregate symbol-level edges into file-level edge table, write to CSV.

    Returns the set of all source_file values (for creating temp file nodes).
    Edges where either endpoint has empty source_file (concept/stub nodes)
    or where both endpoints share the same source_file (intra-file edges)
    are excluded.
    """
    import csv

    results = list(conn.execute(
        "MATCH (a:node)-[:edge]->(b:node) "
        "WHERE a.source_file <> '' AND b.source_file <> '' "
        "AND a.source_file <> b.source_file "
        "RETURN a.source_file, b.source_file, count(*) AS weight"
    ))

    all_files: set[str] = set()
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["from_file", "to_file", "weight"])
        for from_file, to_file, weight in results:
            writer.writerow([from_file, to_file, float(weight)])
            all_files.add(from_file)
            all_files.add(to_file)

    return all_files


def run_leiden_subgraph(
    conn: object,
    *,
    node_label: str,
    edge_label: str,
    resolution: float = 1.0,
    weight: str | None = None,
    initial_community_property: str | None = None,
) -> dict[str, int] | dict[str, tuple[int, int | None]]:
    """Run leiden on an existing node/edge label pair (project + leiden + cleanup).

    Does NOT create or drop temp tables — caller is responsible for that.

    Args:
        node_label: Existing node table name in DB (persistent or temporary).
        edge_label: Existing edge table name in DB.
        resolution: Leiden resolution parameter (gamma).
        weight: If set (e.g. 'weight'), run weighted leiden.
        initial_community_property: If set (e.g. 'delta_comm'), run freeze-assign
            leiden.  When set, returns ``{node_id: (new_cid, prev_cid)}`` instead
            of ``{node_id: community_id}``.
    """
    # Load GDS extension
    try:
        conn.execute("LOAD gds;")
    except RuntimeError:
        conn.execute("INSTALL gds;")
        conn.execute("LOAD gds;")

    gname = _next_graph_name()
    conn.execute(
        f"CALL project_graph('{gname}', ['{node_label}'], "
        f"{{'[{node_label}, {edge_label}, {node_label}]': ''}})"
    )

    # Build leiden options
    opts = f"concurrency: 1, resolution: {resolution}"
    if weight:
        opts += f", weight: '{weight}'"
    if initial_community_property:
        opts += f", initial_community_property: '{initial_community_property}'"

    if initial_community_property:
        # Freeze-assign: also return previous_community
        results = list(conn.execute(
            f"CALL leiden('{gname}', {{{opts}}}) "
            "YIELD node, community, previous_community "
            "RETURN node.id, community, previous_community"
        ))
        try:
            conn.execute(f"CALL drop_projected_graph('{gname}')")
        except RuntimeError:
            pass
        return {nid: (int(cid), prev) for nid, cid, prev in results}
    else:
        results = list(conn.execute(
            f"CALL leiden('{gname}', {{{opts}}}) "
            "YIELD node, community RETURN node.id, community"
        ))
        try:
            conn.execute(f"CALL drop_projected_graph('{gname}')")
        except RuntimeError:
            pass
        return {nid: int(cid) for nid, cid in results}


def _maybe_dump_temp_csvs(edge_csv: Path, node_csv: Path, tag: str) -> None:
    """If GRAPHIFY_KEEP_TEMP is set, copy temp CSVs to that directory."""
    import os, shutil
    dest = os.environ.get("GRAPHIFY_KEEP_TEMP")
    if not dest:
        return
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(edge_csv, dest_dir / f"{tag}_edges.csv")
    shutil.copy2(node_csv, dest_dir / f"{tag}_nodes.csv")


def cluster_on_files(
    conn: object, *, resolution: float = 1.0
) -> dict[int, list[str]]:
    """File-level clustering. Returns ``{community_id: [file_paths]}``.

    Creates temp tables (TempFile / TEMP_FILE_EDGE) and keeps them alive
    for subsequent analysis.  Caller is responsible for cleaning up:
    ``DROP TABLE TEMP_FILE_EDGE; DROP TABLE TempFile;``
    """
    import tempfile, csv

    _NODE_LABEL = "TempFile"
    _EDGE_LABEL = "TEMP_FILE_EDGE"

    # Defensive: clean up any leftover temp tables from previous calls
    conn.execute(f"DROP TABLE IF EXISTS {_EDGE_LABEL}")
    conn.execute(f"DROP TABLE IF EXISTS {_NODE_LABEL}")

    with tempfile.TemporaryDirectory() as tmpdir:
        edge_csv = Path(tmpdir) / "file_edges.csv"
        node_csv = Path(tmpdir) / "file_nodes.csv"

        # 1. Aggregate symbol edges → file-level edge CSV
        all_files = _aggregate_file_edges(conn, edge_csv)

        # Guard: if no files with inter-file edges, return empty — COPY TEMP
        # with an empty CSV does not register the table in neug's catalog.
        if not all_files:
            return {}

        # 2. Write file node CSV (id = file path, must match edge CSV from/to)
        #    Include community + community_name columns for ingest_communities writeback
        with open(node_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "label", "community", "community_name"])
            for sf in sorted(all_files):
                writer.writerow([sf, Path(sf).name, 0, ""])

        # Keep temp CSVs for debugging if GRAPHIFY_KEEP_TEMP is set
        _maybe_dump_temp_csvs(edge_csv, node_csv, "file_cluster")

        # 3. COPY TEMP to create temp tables (independent step)
        conn.execute(
            f"COPY TEMP {_NODE_LABEL} FROM '{node_csv}' "
            "(header=true, delim=',')"
        )
        conn.execute(
            f"COPY TEMP {_EDGE_LABEL} FROM '{edge_csv}' "
            f"(header=true, delim=',', from='{_NODE_LABEL}', to='{_NODE_LABEL}')"
        )

    # 4. Run leiden on the temp subgraph
    file_communities = run_leiden_subgraph(
        conn,
        node_label=_NODE_LABEL,
        edge_label=_EDGE_LABEL,
        resolution=resolution,
        weight=None,
    )

    # 5. Write community to TempFile nodes (for analysis queries)
    communities: dict[int, list[str]] = {}
    for file_path, cid in file_communities.items():
        communities.setdefault(cid, []).append(file_path)
    ingest_communities(conn, communities, node_label=_NODE_LABEL)

    # NOTE: temp tables NOT dropped here — caller cleans up after analysis
    return communities


# ---------------------------------------------------------------------------
# Cohesion + community labeling
# ---------------------------------------------------------------------------


def compute_cohesion(
    conn: object, communities: dict[int, list[str]],
    *, node_label: str = "node", edge_label: str = "edge",
) -> dict[int, float]:
    """Per-community cohesion: undirected internal edges / max possible.

    Uses a single edge scan with ``frozenset`` deduplication to convert
    directed edges to undirected, aligning with NetworkX's ``Graph`` semantics.
    """
    node_comm = {n: cid for cid, nodes in communities.items() for n in nodes}
    intra: dict[int, set] = {cid: set() for cid in communities}

    for row in conn.execute(
        f"MATCH (a:{node_label})-[:{edge_label}]->(b:{node_label}) "
        f"RETURN a.id, b.id"
    ):
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
    conn: object, communities: dict[int, list[str]],
    *, node_label: str = "node", edge_label: str = "edge",
) -> dict[int, str]:
    """Name each community after its highest-degree member.

    Requires community IDs to be written to the db beforehand.
    """
    try:
        rows = list(conn.execute(
            f"MATCH (n:{node_label}) "
            f"WHERE n.community IS NOT NULL "
            f"OPTIONAL MATCH (n)-[e:{edge_label}]-() "
            f"WITH n, n.community AS cid, count(e) AS degree "
            f"ORDER BY cid, degree DESC, n.id ASC "
            f"WITH cid, collect(n)[0] AS hub "
            f"RETURN cid, hub.label, hub.id"
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
            f"MATCH (n:{node_label})-[e:{edge_label}]-() "
            f"WITH n, count(e) AS degree "
            f"RETURN n.id, n.community, n.label, degree "
            f"ORDER BY n.community, degree DESC, n.id"
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
    # 0. Guard: skip tiny/edge-less graphs. The undirected degree query below
    #    crashes neug on graphs without edges, and surprising connections are
    #    meaningless without edges anyway.
    edge_count = list(conn.execute(
        "MATCH ()-[e:edge]->() RETURN count(e)"
    ))
    if not edge_count or edge_count[0][0] == 0:
        return []
    if sum(len(v) for v in communities.values()) < 4:
        return []

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
# File-level analysis helpers (operate on TempFile / TEMP_FILE_EDGE)
# ---------------------------------------------------------------------------


def _find_god_files(conn: object, top_n: int = 10) -> list[dict]:
    """File-level god nodes: top-N files by edge degree."""
    rows = list(conn.execute(
        "MATCH (n:TempFile)-[e:TEMP_FILE_EDGE]-() "
        "WITH n, count(e) AS degree "
        "WHERE degree > 0 "
        "RETURN n.id, n.label, degree "
        "ORDER BY degree DESC, n.id ASC "
        f"LIMIT {top_n}"
    ))
    return [{"id": nid, "label": label, "degree": deg} for nid, label, deg in rows]


def _find_surprising_file_connections(
    conn: object,
    communities: dict[int, list[str]],
    top_n: int = 5,
) -> list[dict]:
    """File-level surprising connections: cross-community edges ranked by weight."""
    node_comm = {n: cid for cid, nodes in communities.items() for n in nodes}

    rows = list(conn.execute(
        "MATCH (a:TempFile)-[e:TEMP_FILE_EDGE]->(b:TempFile) "
        "WHERE a.community IS NOT NULL AND b.community IS NOT NULL "
        "  AND a.community <> b.community "
        "RETURN a.id, a.label, a.community, b.id, b.label, b.community, e.weight"
    ))

    candidates: list[dict] = []
    for a_id, a_label, a_comm, b_id, b_label, b_comm, weight in rows:
        candidates.append({
            "source": a_label or a_id,
            "target": b_label or b_id,
            "source_files": [a_id, b_id],
            "weight": int(weight) if weight else 1,
            "why": f"cross-community file edge (weight={int(weight) if weight else 1})",
        })

    candidates.sort(key=lambda x: x["weight"], reverse=True)
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
    resolution: float = 1.0,
    file_level: bool = False,
) -> None:
    """Orchestrate the neug clustered path.

    Steps: leiden → writeback → label → analysis → export.
    cli.py should call this directly instead of inlining the workflow.
    Returns the exported graph data dict (for summary printing).
    """
    import json

    _FILE_NODE = "TempFile"
    _FILE_EDGE = "TEMP_FILE_EDGE"

    # 1. Leiden community detection (symbol-level or file-level)
    if file_level:
        communities = cluster_on_files(conn, resolution=resolution)
        # communities = {cid: [file_paths]}, temp tables still alive
    else:
        communities = run_leiden(conn, resolution=resolution)
    stages.mark("cluster")

    if file_level and communities:
        # 2a. Label + analysis on temp tables (file-level graph)
        labels = label_communities_by_hub(
            conn, communities, node_label=_FILE_NODE, edge_label=_FILE_EDGE
        )
        ingest_communities(
            conn, communities, community_labels=labels, node_label=_FILE_NODE
        )
        cohesion = compute_cohesion(
            conn, communities, node_label=_FILE_NODE, edge_label=_FILE_EDGE
        )
        gods = _find_god_files(conn)
        surprises = _find_surprising_file_connections(conn, communities)
        stages.mark("analyze")

        # 2b. Write community to symbol-level :node by source_file
        #     (so graph.json export includes community info per symbol)
        for cid, file_paths in communities.items():
            if not file_paths:
                continue
            files_inline = ", ".join(f"'{f}'" for f in file_paths)
            safe_name = (labels.get(cid, f"Community {cid}") or "").replace("'", "\\'")
            conn.execute(
                f"MATCH (n:node) WHERE n.source_file IN [{files_inline}] "
                f"SET n.community = {cid}, n.community_name = '{safe_name}'"
            )
        stages.mark("writeback")
    elif file_level and not communities:
        # No inter-file edges — skip file-level analysis (temp tables don't exist)
        labels = {}
        cohesion = {}
        gods = []
        surprises = []
        stages.mark("analyze")
        stages.mark("writeback")
    else:
        # 2. Batch writeback community IDs
        ingest_communities(conn, communities)

        # 3. Label communities by hub
        labels = label_communities_by_hub(conn, communities)

        # 4. Write community_name
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

    # 7. Write .graphify_analysis.json (sorted by community ID)
    analysis = {
        "communities": {str(k): v for k, v in sorted(communities.items())},
        "cohesion": {str(k): v for k, v in sorted(cohesion.items())},
        "gods": gods,
        "surprises": surprises,
        "tokens": {
            "input": merged["input_tokens"],
            "output": merged["output_tokens"],
        },
    }
    analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    # 8. Clean up temp tables (file-level only)
    if file_level:
        conn.execute(f"DROP TABLE IF EXISTS {_FILE_EDGE}")
        conn.execute(f"DROP TABLE IF EXISTS {_FILE_NODE}")

    return data


# ---------------------------------------------------------------------------
# Incremental delta analysis (freeze-assign leiden)
# ---------------------------------------------------------------------------


def run_leiden_freeze_assign(
    conn: object,
    old_communities: dict[str, int],
    *,
    resolution: float = 1.0,
) -> list[tuple[str, int, int | None]]:
    """Run freeze-assign leiden. Old nodes frozen, new nodes assigned.

    Args:
        old_communities: {node_id: old_community_id} from .graphify_analysis.json.
        resolution: Leiden resolution parameter (gamma).  > 1 favours smaller
            communities, < 1 favours larger communities.  Default 1.0.

    Returns [(node_id, new_community, previous_community), ...].
    previous_community is None for new nodes (delta_comm was -1).
    """
    # Add delta_comm property if not exists
    try:
        conn.execute("ALTER TABLE node ADD delta_comm INT64 DEFAULT -1")
    except RuntimeError:
        pass  # Column already exists

    # Optimisation: most nodes already have the correct community in the DB's
    # ``community`` column (written by the full extract).  Instead of a giant
    # CASE WHEN with N clauses (O(N) parse time), we:
    #   1. Copy ``community`` → ``delta_comm`` for ALL nodes (one fast query)
    #   2. Set ``delta_comm = -1`` for new nodes only (small IN clause)
    #   3. Fix re-extracted nodes whose DB community is 0 but old_communities
    #      says different (per-community SET, usually a handful of queries)
    conn.execute("MATCH (n:node) SET n.delta_comm = n.community")

    # Identify new nodes: in DB but not in old_communities
    db_node_ids = {row[0] for row in conn.execute("MATCH (n:node) RETURN n.id")}
    new_node_ids = db_node_ids - set(old_communities.keys())
    if new_node_ids:
        # Batch in chunks of 500 to avoid query-length limits
        new_list = sorted(new_node_ids)
        for i in range(0, len(new_list), 500):
            chunk = new_list[i:i + 500]
            id_list = ", ".join(f"'{nid}'" for nid in chunk)
            conn.execute(
                f"MATCH (n:node) WHERE n.id IN [{id_list}] "
                f"SET n.delta_comm = -1"
            )

    # Fix re-extracted nodes: in old_communities but DB community doesn't match
    # These are nodes whose file was re-extracted (deleted + re-created with community=0)
    re_extracted: dict[int, list[str]] = {}  # {old_cid: [node_ids]}
    for row in conn.execute(
        "MATCH (n:node) WHERE n.community = 0 RETURN n.id"
    ):
        nid = row[0]
        if nid in old_communities and old_communities[nid] != 0:
            old_cid = old_communities[nid]
            re_extracted.setdefault(old_cid, []).append(nid)

    for old_cid, node_ids in re_extracted.items():
        # Batch in chunks of 500
        for i in range(0, len(node_ids), 500):
            chunk = node_ids[i:i + 500]
            id_list = ", ".join(f"'{nid}'" for nid in chunk)
            conn.execute(
                f"MATCH (n:node) WHERE n.id IN [{id_list}] "
                f"SET n.delta_comm = {old_cid}"
            )

    # Load GDS extension
    try:
        conn.execute("LOAD gds;")
    except RuntimeError:
        conn.execute("INSTALL gds;")
        conn.execute("LOAD gds;")

    # Use a unique projected-graph name (see run_leiden for rationale)
    gname = _next_graph_name()

    # Project graph (picks up delta_comm property)
    conn.execute(
        f"CALL project_graph('{gname}', ['node'], {{'[node, edge, node]': ''}})"
    )

    # Run freeze-assign leiden (allow_relocation defaults to false = frozen)
    results = list(conn.execute(
        f"CALL leiden('{gname}', {{concurrency: 1, resolution: {resolution}, "
        "initial_community_property: 'delta_comm'}) "
        "YIELD node, community, previous_community "
        "RETURN node.id, community, previous_community"
    ))

    # Clean up projected graph
    try:
        conn.execute(f"CALL drop_projected_graph('{gname}')")
    except RuntimeError:
        pass

    # Drop delta_comm column to avoid schema mismatch on subsequent extract
    try:
        conn.execute("ALTER TABLE node DROP delta_comm")
    except RuntimeError:
        pass

    return [(nid, int(cid), prev) for nid, cid, prev in results]


def _merge_changed_fragments(
    conn: object,
    leiden_results: list[tuple[str, int, int | None]],
    old_communities: dict[str, int],
    *,
    min_size: int = 5,
) -> list[tuple[str, int, int | None]]:
    """Merge small changed/new communities into their strongest neighbour.

    Only touches communities that are **new** or **changed** (not stable).
    Stable communities may *receive* merged members but are never split.

    Args:
        conn: neug connection (uses node/edge tables).
        leiden_results: [(node_id, new_cid, prev_cid), ...] from freeze-assign.
        old_communities: {node_id: old_cid} from baseline.
        min_size: communities smaller than this get merged.

    Returns updated leiden_results with merged community assignments.
    """
    # Build new_communities and node→prev mapping
    new_communities: dict[int, list[str]] = {}
    node_prev: dict[str, int | None] = {}
    for nid, new_cid, prev_cid in leiden_results:
        new_communities.setdefault(new_cid, []).append(nid)
        node_prev[nid] = prev_cid

    # Build old community membership for comparison
    old_comm_to_nodes: dict[int, set[str]] = {}
    for nid, cid in old_communities.items():
        old_comm_to_nodes.setdefault(cid, set()).add(nid)

    # Identify changed/new CIDs
    changed_cids: set[int] = set()
    for cid, members in new_communities.items():
        if cid not in old_comm_to_nodes:
            changed_cids.add(cid)  # new
        elif set(members) != old_comm_to_nodes[cid]:
            changed_cids.add(cid)  # changed

    if not changed_cids:
        return leiden_results

    # Load edge weights from the database
    edges: dict[tuple[str, str], float] = {}
    try:
        for row in conn.execute(
            "MATCH (a:node)-[e:edge]->(b:node) "
            "RETURN a.id, b.id, e.weight"
        ):
            w = row[2] if row[2] is not None else 1.0
            edges[(row[0], row[1])] = float(w)
    except RuntimeError:
        pass

    node_comm: dict[str, int] = {
        n: cid for cid, nodes in new_communities.items() for n in nodes
    }
    communities = {k: list(v) for k, v in new_communities.items()}

    merged_any = True
    while merged_any:
        merged_any = False
        small_cids = [
            cid for cid in communities
            if cid in changed_cids and len(communities[cid]) < min_size
        ]
        for small_cid in small_cids:
            if small_cid not in communities:
                continue
            members = communities[small_cid]
            if len(members) >= min_size:
                continue

            # Find strongest neighbour community by edge weight
            comm_connections: dict[int, float] = {}
            for node in members:
                for (a, b), w in edges.items():
                    if a == node:
                        other = node_comm.get(b, -1)
                    elif b == node:
                        other = node_comm.get(a, -1)
                    else:
                        continue
                    if other != small_cid and other >= 0:
                        comm_connections[other] = (
                            comm_connections.get(other, 0.0) + w
                        )

            if not comm_connections:
                continue

            best_cid = max(comm_connections, key=lambda k: comm_connections[k])
            if best_cid not in communities:
                continue

            # Merge small_cid → best_cid
            communities[best_cid].extend(members)
            del communities[small_cid]
            for n in members:
                node_comm[n] = best_cid
            # If target was stable, mark it as changed now
            changed_cids.add(best_cid)
            merged_any = True

    # Rebuild leiden_results from merged communities
    result: list[tuple[str, int, int | None]] = []
    for cid, members in communities.items():
        for nid in members:
            result.append((nid, cid, node_prev.get(nid)))
    return result


def analyze_community_changes(
    leiden_results: list[tuple[str, int, int | None]],
    old_communities: dict[str, int],
) -> dict:
    """Classify communities into 4 orthogonal change types.

    Classification matrix:
      Existed before? | Still exists? | Classification
      Yes             | Yes, no change | stable
      Yes             | Yes, changed   | changed
      Yes             | No             | dissolved
      No              | Yes            | new
    """
    # Build new_communities from leiden results
    new_communities: dict[int, list[str]] = {}
    prev_map: dict[str, int | None] = {}
    for nid, new_cid, prev_cid in leiden_results:
        new_communities.setdefault(new_cid, []).append(nid)
        prev_map[nid] = prev_cid

    # Build old_comm_to_nodes from old_communities
    old_comm_to_nodes: dict[int, list[str]] = {}
    for nid, cid in old_communities.items():
        old_comm_to_nodes.setdefault(cid, []).append(nid)

    changed_communities: dict[str, dict] = {}
    new_communities_out: dict[str, dict] = {}
    stable_communities: list[str] = []
    dissolved_communities: list[dict] = []

    # Classify communities in leiden results
    for cid, current_members in new_communities.items():
        if cid not in old_comm_to_nodes:
            # New community
            new_communities_out[str(cid)] = {
                "members": sorted(current_members),
            }
            continue

        # Existing community — compute grow/shrink
        old_members_set = set(old_comm_to_nodes[cid])
        current_set = set(current_members)

        grow_members = sorted(current_set - old_members_set)
        shrink_members = sorted(old_members_set - current_set)

        if not grow_members and not shrink_members:
            stable_communities.append(str(cid))
        else:
            changed_communities[str(cid)] = {
                "grow_members": grow_members,
                "shrink_members": shrink_members,
            }

    # Find dissolved communities (old but not in new results)
    for old_cid, old_members in old_comm_to_nodes.items():
        if old_cid not in new_communities:
            dissolved_communities.append({
                "cid": old_cid,
                "old_size": len(old_members),
            })

    # Build summary
    summary = {
        "total_before": len(old_comm_to_nodes),
        "total_after": len(new_communities),
        "stable": len(stable_communities),
        "changed": len(changed_communities),
        "new": len(new_communities_out),
        "dissolved": len(dissolved_communities),
    }

    return {
        "changed_communities": changed_communities,
        "new_communities": new_communities_out,
        "stable_communities": stable_communities,
        "dissolved_communities": dissolved_communities,
        "summary": summary,
    }


def _delta_analyze_file_level(
    conn: object,
    old_communities: dict[str, int],
    *,
    resolution: float = 1.0,
) -> list[tuple[str, int, int | None]]:
    """File-level freeze-assign leiden for incremental analysis.

    1. Map old file-level communities from prev_analysis (file paths → old_cid)
    2. Aggregate edges → CSV (same as full file-level clustering)
    3. Write file node CSV with delta_comm column (old_cid or -1 for new files)
    4. COPY TEMP → run_leiden_subgraph with freeze-assign
    5. Write community to TempFile (for analysis queries)

    Temp tables are NOT dropped — caller cleans up after analysis.

    Returns [(file_path, new_cid, prev_cid), ...].
    """
    import tempfile, csv

    _NODE_LABEL = "TempFile"
    _EDGE_LABEL = "TEMP_FILE_EDGE"

    # Defensive: clean up any leftover temp tables from previous calls
    conn.execute(f"DROP TABLE IF EXISTS {_EDGE_LABEL}")
    conn.execute(f"DROP TABLE IF EXISTS {_NODE_LABEL}")

    # 1. old_communities is already {file_path: old_cid} in file-level mode
    old_file_communities: dict[str, int] = old_communities

    with tempfile.TemporaryDirectory() as tmpdir:
        edge_csv = Path(tmpdir) / "file_edges.csv"
        node_csv = Path(tmpdir) / "file_nodes.csv"

        # 2. Aggregate edges → CSV
        all_files = _aggregate_file_edges(conn, edge_csv)

        # Guard: if no files with inter-file edges, return empty — COPY TEMP
        # with an empty CSV does not register the table in neug's catalog.
        if not all_files:
            return []

        # 3. Write file node CSV with delta_comm + community columns
        #    id = file path, delta_comm = old community (or -1 for new files)
        #    community = 0 (placeholder, overwritten by ingest_communities)
        with open(node_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "label", "delta_comm", "community", "community_name"])
            for sf in sorted(all_files):
                old_cid = old_file_communities.get(sf, -1)
                writer.writerow([sf, Path(sf).name, old_cid, 0, ""])

        # Keep temp CSVs for debugging if GRAPHIFY_KEEP_TEMP is set
        _maybe_dump_temp_csvs(edge_csv, node_csv, "file_delta")

        # 4. COPY TEMP
        conn.execute(
            f"COPY TEMP {_NODE_LABEL} FROM '{node_csv}' "
            "(header=true, delim=',')"
        )
        conn.execute(
            f"COPY TEMP {_EDGE_LABEL} FROM '{edge_csv}' "
            f"(header=true, delim=',', from='{_NODE_LABEL}', to='{_NODE_LABEL}')"
        )

    # 5. Run freeze-assign leiden on temp subgraph
    file_results = run_leiden_subgraph(
        conn,
        node_label=_NODE_LABEL,
        edge_label=_EDGE_LABEL,
        resolution=resolution,
        weight=None,
        initial_community_property="delta_comm",
    )
    # file_results: {file_path: (new_cid, prev_cid)}

    # 6. Write community to TempFile nodes (for analysis queries)
    new_communities: dict[int, list[str]] = {}
    for file_path, (new_cid, _) in file_results.items():
        new_communities.setdefault(new_cid, []).append(file_path)
    ingest_communities(conn, new_communities, node_label=_NODE_LABEL)

    # 7. Return file-level results (NOT expanded to symbol level)
    return [
        (file_path, new_cid, prev_cid)
        for file_path, (new_cid, prev_cid) in file_results.items()
    ]


def delta_analyze(
    conn: object,
    *,
    prev_analysis: dict,
    delta_analysis_path: object,
    stages: object,
    merged: dict,
    resolution: float = 1.0,
    file_level: bool = False,
) -> dict:
    """Orchestrate incremental delta analysis (preview mode).

    Steps: freeze-assign leiden → community change analysis →
    partial cohesion → full gods/surprises → write delta.
    Does NOT writeback to DB's community property (preview only).
    """
    import json

    # 1. Build old_communities from prev_analysis
    old_communities: dict[str, int] = {}
    for cid_str, node_ids in prev_analysis.get("communities", {}).items():
        cid = int(cid_str)
        for nid in node_ids:
            old_communities[nid] = cid

    # 2. Run freeze-assign leiden (symbol-level or file-level)
    if file_level:
        leiden_results = _delta_analyze_file_level(
            conn, old_communities, resolution=resolution
        )
    else:
        leiden_results = run_leiden_freeze_assign(conn, old_communities, resolution=resolution)
    stages.mark("freeze-assign")

    # 2b. Merge small changed/new communities (only fragments, no split)
    leiden_results = _merge_changed_fragments(
        conn, leiden_results, old_communities, min_size=5,
    )
    stages.mark("merge-fragments")

    # 3. Analyze community changes
    changes = analyze_community_changes(leiden_results, old_communities)
    stages.mark("analyze-changes")

    # 4. Build new_communities dict for cohesion + surprising_connections
    new_communities: dict[int, list[str]] = {}
    for nid, new_cid, _ in leiden_results:
        new_communities.setdefault(new_cid, []).append(nid)

    # 5. Compute cohesion only for changed + new communities
    changed_cids = set()
    for cid_str in changes["changed_communities"]:
        changed_cids.add(int(cid_str))
    for cid_str in changes["new_communities"]:
        changed_cids.add(int(cid_str))

    _FILE_NODE = "TempFile"
    _FILE_EDGE = "TEMP_FILE_EDGE"

    if file_level and new_communities:
        # File-level analysis on temp tables
        all_cohesion = compute_cohesion(
            conn, new_communities, node_label=_FILE_NODE, edge_label=_FILE_EDGE
        )
        delta_cohesion = {cid: score for cid, score in all_cohesion.items() if cid in changed_cids}

        labels = label_communities_by_hub(
            conn, new_communities, node_label=_FILE_NODE, edge_label=_FILE_EDGE
        )
        gods = _find_god_files(conn)
        surprises = _find_surprising_file_connections(conn, new_communities)
    elif file_level and not new_communities:
        # No inter-file edges — temp tables don't exist, skip file-level analysis
        delta_cohesion = {}
        labels = {}
        gods = []
        surprises = []
    else:
        # Symbol-level analysis (existing path)
        all_cohesion = compute_cohesion(conn, new_communities)
        delta_cohesion = {cid: score for cid, score in all_cohesion.items() if cid in changed_cids}

        # 6. Label communities (reuse label_communities_by_hub)
        labels: dict[int, str] = {}
        try:
            node_degree: dict[str, int] = {}
            for row in conn.execute(
                "MATCH (n:node)-[e:edge]-() "
                "WITH n, count(e) AS degree "
                "RETURN n.id, degree"
            ):
                node_degree[row[0]] = row[1]
        except RuntimeError:
            node_degree = {}

        node_label: dict[str, str] = {}
        try:
            for row in conn.execute("MATCH (n:node) RETURN n.id, n.label"):
                node_label[row[0]] = row[1] or row[0]
        except RuntimeError:
            pass

        for cid, members in new_communities.items():
            if cid not in changed_cids:
                continue
            best_nid = members[0]
            best_deg = -1
            for nid in members:
                deg = node_degree.get(nid, 0)
                if deg > best_deg:
                    best_deg = deg
                    best_nid = nid
            name = (node_label.get(best_nid, best_nid) or best_nid).strip()
            if name.endswith("()"):
                name = name[:-2]
            labels[cid] = name or f"Community {cid}"

        gods = find_god_nodes(conn)
        surprises = find_surprising_connections(conn, new_communities)
    stages.mark("analyze-full")

    # 8. Build delta JSON
    # Add cohesion + community_name to changed/new communities
    for cid_str, info in changes["changed_communities"].items():
        cid = int(cid_str)
        info["cohesion"] = delta_cohesion.get(cid, 0.0)
        info["community_name"] = labels.get(cid, f"Community {cid}")
    for cid_str, info in changes["new_communities"].items():
        cid = int(cid_str)
        info["cohesion"] = delta_cohesion.get(cid, 0.0)
        info["community_name"] = labels.get(cid, f"Community {cid}")

    # Sort all community sections by community ID (ascending)
    sorted_changed = dict(sorted(changes["changed_communities"].items(), key=lambda x: int(x[0])))
    sorted_new = dict(sorted(changes["new_communities"].items(), key=lambda x: int(x[0])))
    sorted_stable = sorted(changes["stable_communities"], key=lambda x: int(x))
    sorted_dissolved = sorted(changes["dissolved_communities"], key=lambda x: x["cid"])

    delta = {
        "changed_communities": sorted_changed,
        "new_communities": sorted_new,
        "stable_communities": sorted_stable,
        "dissolved_communities": sorted_dissolved,
        "summary": changes["summary"],
        "gods": gods,
        "surprises": surprises,
        "tokens": {
            "input": merged.get("input_tokens", 0),
            "output": merged.get("output_tokens", 0),
        },
    }

    delta_analysis_path.write_text(json.dumps(delta, indent=2), encoding="utf-8")

    # Clean up temp tables (file-level only)
    if file_level:
        conn.execute(f"DROP TABLE IF EXISTS {_FILE_EDGE}")
        conn.execute(f"DROP TABLE IF EXISTS {_FILE_NODE}")

    return delta
