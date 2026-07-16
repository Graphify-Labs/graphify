#!/usr/bin/env python3
"""Standalone NeuG Leiden test: import CSV → run Leiden → report.

Usage:
    python test_neug_leiden_standalone.py <nodes.csv> <edges.csv> [resolution]

Reproduces the segfault seen during graphify extract clustering step,
using only NeuG APIs (no graphify/NetworkX).
"""
import sys
import os
import tempfile
import time

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <nodes.csv> <edges.csv> [resolution]")
        sys.exit(1)

    nodes_csv = os.path.abspath(sys.argv[1])
    edges_csv = os.path.abspath(sys.argv[2])
    resolution = float(sys.argv[3]) if len(sys.argv) > 3 else 0.7

    print(f"Nodes CSV: {nodes_csv}")
    print(f"Edges CSV: {edges_csv}")
    print(f"Resolution: {resolution}")

    # Count lines in CSVs (rough)
    with open(nodes_csv) as f:
        node_count = sum(1 for _ in f) - 1  # minus header
    with open(edges_csv) as f:
        edge_count = sum(1 for _ in f) - 1
    print(f"Nodes: {node_count}, Edges: {edge_count}")

    import neug

    tmpdir = tempfile.mkdtemp(prefix="neug_leiden_test_")
    db_path = os.path.join(tmpdir, "test.db")
    print(f"DB path: {db_path}")

    t0 = time.time()
    db = neug.Database(db_path, mode="rw")
    conn = db.connect()
    print(f"[{time.time()-t0:.1f}s] DB opened")

    # Create schema — match CSV columns exactly (no leiden_comm in dump CSV)
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS node (
            id STRING PRIMARY KEY, label STRING, type STRING,
            source_file STRING, source_location STRING)
    """)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS edge (
            FROM node TO node,
            relation STRING, confidence STRING,
            confidence_score DOUBLE, source_file STRING, weight DOUBLE)
    """)
    print(f"[{time.time()-t0:.1f}s] Schema created")

    # Import nodes via COPY
    conn.execute(
        f'COPY node (id, label, type, source_file, source_location) '
        f'FROM "{nodes_csv}" (header=true, delim=",", escaping=false)'
    )
    print(f"[{time.time()-t0:.1f}s] Nodes imported")

    # Import edges via COPY
    conn.execute(
        f'COPY edge FROM "{edges_csv}" '
        f'(from="node", to="node", header=true, delim=",", escaping=false)'
    )
    print(f"[{time.time()-t0:.1f}s] Edges imported")

    # Verify
    rows = list(conn.execute("MATCH (n:node) RETURN count(n)"))
    print(f"[{time.time()-t0:.1f}s] Node count in DB: {rows[0][0]}")
    rows = list(conn.execute("MATCH ()-[r:edge]->() RETURN count(r)"))
    print(f"[{time.time()-t0:.1f}s] Edge count in DB: {rows[0][0]}")

    # Load GDS extension (same as graphify _ensure_gds)
    conn.execute("INSTALL gds")
    conn.execute("LOAD gds")
    print(f"[{time.time()-t0:.1f}s] GDS extension loaded")

    # Project graph
    conn.execute(
        "CALL project_graph('graphify_full', ['node'], "
        "{'[node, edge, node]': ''})"
    )
    print(f"[{time.time()-t0:.1f}s] Graph projected")

    # Run Leiden
    print(f"[{time.time()-t0:.1f}s] Running Leiden (resolution={resolution})...")
    sys.stdout.flush()

    t_leiden = time.time()
    rows = list(conn.execute(
        f"CALL leiden('graphify_full', {{resolution: {resolution}}}) "
        f"YIELD node, community RETURN node.id, community"
    ))
    leiden_elapsed = time.time() - t_leiden
    print(f"[{leiden_elapsed:.1f}s] Leiden completed! {len(rows)} nodes assigned")

    # Summarize communities
    communities: dict[int, list[str]] = {}
    for row in rows:
        node_id, community = row[0], int(row[1])
        communities.setdefault(community, []).append(node_id)

    sizes = sorted((len(v) for v in communities.values()), reverse=True)
    print(f"Communities: {len(communities)}")
    print(f"Top 10 sizes: {sizes[:10]}")
    print(f"Singletons: {sum(1 for s in sizes if s == 1)}")

    # Cleanup
    try:
        conn.execute("CALL drop_projected_graph('graphify_full')")
    except Exception:
        pass
    conn.close()
    db.close()

    print(f"\n[{time.time()-t0:.1f}s] Done — no segfault!")
    print(f"\nMemory info: {os.uname()}")


if __name__ == "__main__":
    main()
