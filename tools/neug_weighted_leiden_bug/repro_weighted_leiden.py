#!/usr/bin/env python3
"""Reproduction script for neug weighted Leiden bug.

Bug summary:
  When `weight` parameter is passed to `CALL leiden(...)`, the algorithm
  produces degenerate results — far more communities than unweighted mode,
  with nearly all high-weight edges split across different communities.

  Lowering `resolution` does NOT help (312 communities at res=1.0 vs 313
  at res=0.001).

Prerequisites:
  pip install neug

Usage:
  python repro_weighted_leiden.py [--csv-dir DIR]

  --csv-dir points to a directory containing file_cluster_nodes.csv and
  file_cluster_edges.csv (produced by graphify --cluster-on-files with
  GRAPHIFY_KEEP_TEMP=./tmp_csvs). If omitted, a small synthetic dataset
  is generated inline.

Expected output (real neug codebase data, 1332 nodes / 2982 edges):

  === Weighted res=1.0 ===
    Communities: 312
    Internal edge ratio: 5.8%
    Top-20 high-weight edges in same community: 0/20

  === Unweighted res=1.0 ===
    Communities: 91
    Internal edge ratio: 60.6%
    Top-20 high-weight edges in same community: 13/20

  === Weighted res=0.001 ===
    Communities: 313
    Internal edge ratio: 6.8%
    Top-20 high-weight edges in same community: 0/20
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile

# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def load_real_data(csv_dir: str):
    """Load nodes/edges from graphify temp CSVs.

    Edges CSV may have integer weights — we rewrite as float to ensure
    DOUBLE type inference by COPY TEMP (neug leiden requires DOUBLE).
    """
    nodes_csv = os.path.join(csv_dir, "file_cluster_nodes.csv")
    edges_csv = os.path.join(csv_dir, "file_cluster_edges.csv")

    # Rewrite edges with float weights
    float_edges = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    with open(edges_csv) as fin:
        reader = csv.DictReader(fin)
        writer = csv.writer(float_edges)
        writer.writerow(["from_file", "to_file", "weight"])
        for r in reader:
            writer.writerow([r["from_file"], r["to_file"], float(r["weight"])])
    float_edges.close()

    return nodes_csv, float_edges.name


def generate_synthetic_data():
    """Generate a small synthetic graph with clear community structure.

    Two groups of 5 nodes each, with strong intra-group edges (weight=10)
    and one weak cross-group edge (weight=1).
    """
    nodes_csv = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    writer = csv.writer(nodes_csv)
    writer.writerow(["id", "label"])
    for i in range(1, 11):
        writer.writerow([f"node{i}", f"node{i}"])
    nodes_csv.close()

    edges_csv = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    writer = csv.writer(edges_csv)
    writer.writerow(["from_file", "to_file", "weight"])

    # Group A: node1-5, strong internal edges
    for i in range(1, 5):
        for j in range(i + 1, 6):
            writer.writerow([f"node{i}", f"node{j}", 10.0])

    # Group B: node6-10, strong internal edges
    for i in range(6, 10):
        for j in range(i + 1, 11):
            writer.writerow([f"node{i}", f"node{j}", 10.0])

    # One weak cross-group edge
    writer.writerow(["node1", "node6", 1.0])
    edges_csv.close()

    return nodes_csv.name, edges_csv.name


# ---------------------------------------------------------------------------
# neug test harness
# ---------------------------------------------------------------------------

def run_test(nodes_csv: str, edges_csv: str):
    """Load data into neug, run weighted vs unweighted leiden, compare."""
    import neug

    db_path = tempfile.mkdtemp() + "/test.db"
    db = neug.Database(db_path)
    conn = db.connect()

    # Load data via COPY TEMP
    conn.execute(
        f"COPY TEMP TempFile FROM '{nodes_csv}' (header=true, delim=',')"
    )
    conn.execute(
        f"COPY TEMP TEMP_FILE_EDGE FROM '{edges_csv}' "
        f"(header=true, delim=',', from='TempFile', to='TempFile')"
    )

    # Verify
    node_count = list(
        conn.execute("MATCH (n:TempFile) RETURN count(n)")
    )[0][0]
    edge_count = list(
        conn.execute("MATCH ()-[e:TEMP_FILE_EDGE]->() RETURN count(e)")
    )[0][0]
    total_weight = list(
        conn.execute(
            "MATCH ()-[e:TEMP_FILE_EDGE]->() RETURN sum(e.weight)"
        )
    )[0][0]
    print(f"Loaded: {node_count} nodes, {edge_count} edges, "
          f"total weight={total_weight}")

    # Collect all edges for analysis
    edges = []
    for row in conn.execute(
        "MATCH (a:TempFile)-[e:TEMP_FILE_EDGE]->(b:TempFile) "
        "RETURN a.id, b.id, e.weight"
    ):
        edges.append((row[0], row[1], row[2]))

    # Project graph
    conn.execute("LOAD gds")
    conn.execute(
        "CALL project_graph('g', ['TempFile'], "
        "{'[TempFile, TEMP_FILE_EDGE, TempFile]': ''})"
    )

    def run_leiden(weighted: bool, resolution: float):
        opts = f"{{concurrency: 1, resolution: {resolution}}}"
        if weighted:
            opts = f"{{concurrency: 1, resolution: {resolution}, " \
                   f"weight: 'weight'}}"
        results = list(conn.execute(
            f"CALL leiden('g', {opts}) "
            "YIELD node, community RETURN node.id, community"
        ))
        communities = {}
        for nid, cid in results:
            communities.setdefault(int(cid), []).append(nid)
        return communities

    def analyze(communities, label):
        node_comm = {
            n: cid for cid, nodes in communities.items() for n in nodes
        }

        internal = 0
        cross = 0
        for a, b, w in edges:
            if node_comm.get(a) == node_comm.get(b):
                internal += 1
            else:
                cross += 1

        # Top-20 high-weight edges: same community?
        top_edges = sorted(edges, key=lambda x: x[2], reverse=True)[:20]
        same = sum(
            1 for a, b, w in top_edges
            if node_comm.get(a) == node_comm.get(b)
        )

        sizes = sorted(
            [len(v) for v in communities.values()], reverse=True
        )

        print(f"\n=== {label} ===")
        print(f"  Communities: {len(communities)}")
        print(f"  Internal edges: {internal} "
              f"({internal * 100 / len(edges):.1f}%)")
        print(f"  Cross edges: {cross} "
              f"({cross * 100 / len(edges):.1f}%)")
        print(f"  Top-20 high-weight edges in same community: "
              f"{same}/{min(20, len(top_edges))}")
        print(f"  Top community sizes: {sizes[:10]}")

        # Show top cross-community edges (should be rare in good clustering)
        if cross > 0:
            cross_edges = [
                (a, b, w, node_comm[a], node_comm[b])
                for a, b, w in edges
                if node_comm.get(a) != node_comm.get(b)
            ]
            cross_edges.sort(key=lambda x: x[2], reverse=True)
            if cross_edges:
                print(f"  Top cross-community edges:")
                for a, b, w, ca, cb in cross_edges[:5]:
                    print(f"    {a} ({ca}) -> {b} ({cb}) weight={w}")

        return communities

    # Run all configurations
    analyze(run_leiden(True, 1.0), "Weighted res=1.0")
    analyze(run_leiden(False, 1.0), "Unweighted res=1.0")
    analyze(run_leiden(True, 0.001), "Weighted res=0.001")
    analyze(run_leiden(False, 0.001), "Unweighted res=0.001")

    # Cleanup
    try:
        conn.execute("CALL drop_projected_graph('g')")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Reproduce neug weighted Leiden bug"
    )
    parser.add_argument(
        "--csv-dir",
        help="Directory with file_cluster_nodes.csv and "
             "file_cluster_edges.csv from graphify --cluster-on-files "
             "GRAPHIFY_KEEP_TEMP=./tmp_csvs",
    )
    args = parser.parse_args()

    if args.csv_dir:
        nodes_csv, edges_csv = load_real_data(args.csv_dir)
        print("Using real graphify data from:", args.csv_dir)
    else:
        nodes_csv, edges_csv = generate_synthetic_data()
        print("Using synthetic data (10 nodes, 2 communities)")

    run_test(nodes_csv, edges_csv)

    # Cleanup temp files
    for f in [nodes_csv, edges_csv]:
        try:
            os.unlink(f)
        except OSError:
            pass


if __name__ == "__main__":
    main()
