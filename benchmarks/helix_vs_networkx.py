#!/usr/bin/env python3
"""Reproducible Helix comparison against the current v8 NetworkX/JSON baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

try:
    import resource
except ImportError:  # Native Windows has no resource module; RSS is informational.
    resource = None

from graphify.helix.model import EdgeData, GraphBuildData, NodeData
from graphify.helix.persistence import HelixEmbeddedStore, HelixGraphReader
from graphify.helix.state import new_state


SIZES = ((5_000, 15_000), (20_000, 60_000))


def _peak_rss_bytes() -> int:
    if resource is None:
        return 0
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system() == "Darwin" else value * 1024


def measure(call: Callable[[], Any]) -> tuple[Any, float, int]:
    before = _peak_rss_bytes()
    started = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - started
    after = _peak_rss_bytes()
    return result, elapsed, max(0, after - before)


def median_measure(call: Callable[[], Any], runs: int) -> tuple[Any, float, list[float]]:
    samples: list[float] = []
    result: Any = None
    for _ in range(runs):
        result, elapsed, _ = measure(call)
        samples.append(elapsed)
    return result, statistics.median(samples), samples


def isolated_ingest_memory(backend: str, nodes: int, edges: int) -> int:
    """Measure each backend in a fresh process so peak RSS cannot leak across runs."""
    output = subprocess.check_output(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--memory-backend",
            backend,
            "--memory-nodes",
            str(nodes),
            "--memory-edges",
            str(edges),
        ],
        text=True,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", ".")},
    )
    return int(output.strip())


def memory_only(backend: str, nodes: int, edges: int) -> int:
    root = Path(tempfile.mkdtemp(prefix="graphify-memory-benchmark-"))
    try:
        if backend == "networkx":
            import networkx as networkx

            before = _peak_rss_bytes()
            graph = topology(networkx.Graph, nodes, edges, 42)
            payload = networkx.node_link_data(graph, edges="links")
            (root / "graph.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return max(0, _peak_rss_bytes() - before)
        before = _peak_rss_bytes()
        graph = helix_topology(nodes, edges, 42)
        with HelixEmbeddedStore(root / "graph.helix") as store:
            store.save_generation(graph, new_state(build={"benchmark": True}))
        return max(0, _peak_rss_bytes() - before)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def topology(graph_type: type, nodes: int, edges: int, seed: int):
    graph = graph_type()
    graph.add_nodes_from((index, {"label": f"node-{index}"}) for index in range(nodes))
    rng = random.Random(seed)
    seen: set[tuple[int, int]] = set()
    while len(seen) < edges:
        source, target = rng.randrange(nodes), rng.randrange(nodes)
        pair = (min(source, target), max(source, target))
        if source != target and pair not in seen:
            seen.add(pair)
            graph.add_edge(source, target, weight=1.0)
    return graph


def helix_topology(
    nodes: int, edges: int, seed: int, *, mixed_labels: bool = False
) -> GraphBuildData:
    rng = random.Random(seed)
    seen: set[tuple[int, int]] = set()
    while len(seen) < edges:
        source, target = rng.randrange(nodes), rng.randrange(nodes)
        pair = (min(source, target), max(source, target))
        if source != target:
            seen.add(pair)
    return GraphBuildData(
        nodes=[NodeData(index, {"label": f"node-{index}"}) for index in range(nodes)],
        edges=[
            EdgeData(
                source,
                target,
                {
                    "relation": (
                        ("CALLS", "IMPORTS", "INHERITS")[index % 3]
                        if mixed_labels
                        else "RELATED_TO"
                    ),
                    **({"weight": 1.0} if index % 2 == 0 or not mixed_labels else {}),
                    **({"context": "code"} if mixed_labels and index % 5 == 0 else {}),
                },
            )
            for index, (source, target) in enumerate(sorted(seen))
        ],
    )


def directory_size(path: Path) -> int:
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def run_size(nodes: int, edges: int, root: Path) -> dict[str, Any]:
    import networkx as networkx  # benchmark-only dependency

    result: dict[str, Any] = {"nodes": nodes, "edges": edges}
    nx_path = root / f"{nodes}-{edges}.networkx.json"

    def persist_networkx(graph: Any) -> None:
        payload = networkx.node_link_data(graph, edges="links")
        nx_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def networkx_ingest():
        graph = topology(networkx.Graph, nodes, edges, 42)
        persist_networkx(graph)
        return graph

    nx_graph, nx_ingest, _ = measure(networkx_ingest)
    _, nx_reopen, nx_reopen_samples = median_measure(
        lambda: networkx.node_link_graph(
            json.loads(nx_path.read_text(encoding="utf-8")), edges="links"
        ),
        3,
    )

    def ingest_fixture(mixed_labels: bool, *, retain_last: bool):
        samples: list[float] = []
        retained_graph = None
        retained_path = None
        for run in range(3):
            sample_path = root / (
                f"{nodes}-{edges}.{'mixed' if mixed_labels else 'homogeneous'}-{run}.helix"
            )

            def ingest():
                graph = helix_topology(nodes, edges, 42, mixed_labels=mixed_labels)
                with HelixEmbeddedStore(sample_path) as store:
                    store.save_generation(graph, new_state(build={"benchmark": True}))
                return graph

            graph, elapsed, _ = measure(ingest)
            samples.append(elapsed)
            if retain_last and run == 2:
                retained_graph, retained_path = graph, sample_path
            else:
                shutil.rmtree(sample_path, ignore_errors=True)
        return retained_graph, retained_path, statistics.median(samples), samples

    helix_graph, store_path, helix_ingest, helix_ingest_samples = ingest_fixture(
        False, retain_last=True
    )
    _, _, helix_mixed_ingest, helix_mixed_ingest_samples = ingest_fixture(True, retain_last=False)
    assert helix_graph is not None and store_path is not None

    def reopen():
        with HelixEmbeddedStore(store_path, read_only=True) as store:
            return store.load()

    loaded, helix_reopen, helix_reopen_samples = median_measure(reopen, 3)
    durable = loaded.graph
    if durable.node_count != nodes or durable.edge_count != edges:
        raise RuntimeError("Helix reopen count verification failed")
    helix_ingest_disk = directory_size(store_path)

    update_count = max(1, nodes // 100)

    def networkx_incremental():
        for index in range(update_count):
            nx_graph.nodes[index]["label"] = f"updated-node-{index}"
        persist_networkx(nx_graph)

    _, nx_incremental, _ = measure(networkx_incremental)

    helix_incremental_samples: list[float] = []
    with HelixEmbeddedStore(store_path) as store:
        for run in range(3):
            changed = GraphBuildData(
                nodes=[
                    NodeData(
                        node.id,
                        {
                            **node.attributes,
                            **(
                                {"label": f"updated-{run}-node-{node.id}"}
                                if isinstance(node.id, int) and node.id < update_count
                                else {}
                            ),
                        },
                    )
                    for node in helix_graph.nodes
                ],
                edges=list(helix_graph.edges),
            )
            _, elapsed, _ = measure(
                lambda: store.save_generation(
                    changed,
                    new_state(build={"benchmark": True, "incremental_percent": 1}),
                )
            )
            helix_incremental_samples.append(elapsed)
    helix_incremental = statistics.median(helix_incremental_samples)
    loaded = reopen()
    durable = loaded.graph

    reader = HelixGraphReader(store_path)
    reader.get()
    _, helix_hot_open, helix_hot_open_samples = median_measure(reader.get, 5)
    probes = [index * (nodes // 20) for index in range(20)]
    _, nx_neighbors, nx_neighbor_samples = median_measure(
        lambda: [tuple(nx_graph.neighbors(node)) for node in probes], 5
    )
    _, helix_neighbors, helix_neighbor_samples = median_measure(
        lambda: [durable.neighbors(node) for node in probes], 5
    )
    _, nx_bfs, nx_bfs_samples = median_measure(
        lambda: list(networkx.bfs_tree(nx_graph, 0, depth_limit=4)), 5
    )
    _, helix_bfs, helix_bfs_samples = median_measure(lambda: _bounded_bfs(durable, 0, 4), 5)
    _, nx_shortest, nx_shortest_samples = median_measure(
        lambda: [networkx.shortest_path(nx_graph, 0, 4) for _ in range(5)], 5
    )
    _, helix_shortest, helix_shortest_samples = median_measure(
        lambda: [durable.shortest_path(0, 4) for _ in range(5)], 5
    )
    _, nx_louvain, nx_louvain_samples = median_measure(
        lambda: networkx.community.louvain_communities(nx_graph, seed=42), 3
    )
    _, helix_leiden, helix_leiden_samples = median_measure(
        lambda: durable.to_undirected().leiden().communities, 3
    )
    _, nx_centrality, nx_centrality_samples = median_measure(
        lambda: networkx.betweenness_centrality(nx_graph, k=min(100, nodes), seed=42), 1
    )
    _, helix_centrality, helix_centrality_samples = median_measure(
        lambda: durable.betweenness_centrality(
            __import__("helixdb").BetweennessOptions(
                mode="sampled", sample_count=min(100, nodes), seed=42
            )
        ),
        1,
    )
    _, nx_edge_centrality, nx_edge_centrality_samples = median_measure(
        lambda: networkx.edge_betweenness_centrality(nx_graph, k=min(100, nodes), seed=42), 1
    )
    _, helix_edge_centrality, helix_edge_centrality_samples = median_measure(
        lambda: durable.edge_betweenness_centrality(
            __import__("helixdb").BetweennessOptions(
                mode="sampled", sample_count=min(100, nodes), seed=42
            )
        ),
        1,
    )

    nx_export_path = root / f"{nodes}-{edges}.networkx.graphml"
    helix_export_path = root / f"{nodes}-{edges}.helix.graphml"
    _, nx_export, _ = measure(lambda: networkx.write_graphml(nx_graph, nx_export_path))

    def helix_export_graphml():
        from graphify.export import to_graphml

        to_graphml(durable, {}, str(helix_export_path))

    _, helix_export, _ = measure(helix_export_graphml)

    def concurrent_readers():
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(lambda _: reopen().graph.node_count, range(8)))

    _, helix_concurrency, _ = measure(concurrent_readers)
    nx_memory = isolated_ingest_memory("networkx", nodes, edges)
    helix_memory = isolated_ingest_memory("helix", nodes, edges)
    result["networkx"] = {
        "ingest_seconds": nx_ingest,
        "ingest_runs": 1,
        "reopen_seconds": nx_reopen,
        "reopen_samples_seconds": nx_reopen_samples,
        "neighbor_20_queries_seconds": nx_neighbors,
        "neighbor_samples_seconds": nx_neighbor_samples,
        "bfs_seconds": nx_bfs,
        "bfs_samples_seconds": nx_bfs_samples,
        "shortest_path_5_queries_seconds": nx_shortest,
        "shortest_path_samples_seconds": nx_shortest_samples,
        "community_detection": "Louvain (production NetworkX comparator)",
        "community_seconds": nx_louvain,
        "community_samples_seconds": nx_louvain_samples,
        "node_betweenness_seconds": nx_centrality,
        "node_betweenness_samples_seconds": nx_centrality_samples,
        "edge_betweenness_seconds": nx_edge_centrality,
        "edge_betweenness_samples_seconds": nx_edge_centrality_samples,
        "betweenness_mode": f"sampled ({min(100, nodes)} sources, seed 42)",
        "incremental_1pct_seconds": nx_incremental,
        "graphml_export_seconds": nx_export,
        "peak_rss_delta_bytes": nx_memory,
        "disk_bytes": nx_path.stat().st_size,
    }
    result["helix"] = {
        "ingest_seconds": helix_ingest,
        "ingest_runs": 3,
        "ingest_samples_seconds": helix_ingest_samples,
        "mixed_label_ingest_seconds": helix_mixed_ingest,
        "mixed_label_ingest_samples_seconds": helix_mixed_ingest_samples,
        "reopen_seconds": helix_reopen,
        "reopen_samples_seconds": helix_reopen_samples,
        "hot_open_seconds": helix_hot_open,
        "hot_open_samples_seconds": helix_hot_open_samples,
        "neighbor_20_queries_seconds": helix_neighbors,
        "neighbor_samples_seconds": helix_neighbor_samples,
        "bfs_seconds": helix_bfs,
        "bfs_samples_seconds": helix_bfs_samples,
        "shortest_path_5_queries_seconds": helix_shortest,
        "shortest_path_samples_seconds": helix_shortest_samples,
        "community_detection": "weighted Leiden (Graphify production)",
        "community_seconds": helix_leiden,
        "community_samples_seconds": helix_leiden_samples,
        "node_betweenness_seconds": helix_centrality,
        "node_betweenness_samples_seconds": helix_centrality_samples,
        "edge_betweenness_seconds": helix_edge_centrality,
        "edge_betweenness_samples_seconds": helix_edge_centrality_samples,
        "betweenness_mode": f"sampled ({min(100, nodes)} sources, seed 42)",
        "incremental_1pct_seconds": helix_incremental,
        "incremental_1pct_samples_seconds": helix_incremental_samples,
        "graphml_export_seconds": helix_export,
        "eight_concurrent_reopens_seconds": helix_concurrency,
        "peak_rss_delta_bytes": helix_memory,
        "disk_after_ingest_bytes": helix_ingest_disk,
        "disk_after_update_bytes": directory_size(store_path),
        "post_delta_store_ratio": directory_size(store_path) / helix_ingest_disk,
    }
    result["comparisons"] = {
        "ingest_vs_networkx": helix_ingest / nx_ingest,
        "mixed_label_ingest_vs_networkx": helix_mixed_ingest / nx_ingest,
        "incremental_1pct_vs_networkx": helix_incremental / nx_incremental,
        "preferred_20k_ingest_seconds": 5.0 if nodes == 20_000 else None,
    }
    return result


def acceptance_gates(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the release thresholds and retain every measured comparison."""
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: float, limit: float, comparison: str = "<=") -> None:
        passed = actual <= limit if comparison == "<=" else actual >= limit
        checks.append(
            {
                "name": name,
                "actual": actual,
                "limit": limit,
                "comparison": comparison,
                "passed": passed,
            }
        )

    for row in results:
        label = f"{row['nodes']}/{row['edges']}"
        helix = row["helix"]
        networkx = row["networkx"]
        cold_limit = 0.5 if row["nodes"] == 5_000 else 3.0
        hot_limit = 0.100 if row["nodes"] == 5_000 else 0.500
        ingest_limit = 3.0 if row["nodes"] == 5_000 else 5.0
        check(f"{label} ingest seconds", helix["ingest_seconds"], ingest_limit)
        check(
            f"{label} mixed-label ingest seconds",
            helix["mixed_label_ingest_seconds"],
            ingest_limit,
        )
        check(
            f"{label} 1% production delta seconds",
            helix["incremental_1pct_seconds"],
            2.0,
        )
        check(
            f"{label} post-delta store growth",
            helix["post_delta_store_ratio"],
            1.3,
        )
        if row["nodes"] == 20_000:
            check(
                f"{label} peak ingest RSS MiB",
                helix["peak_rss_delta_bytes"] / (1024 * 1024),
                600.0,
            )
        check(f"{label} cold open seconds", helix["reopen_seconds"], cold_limit)
        check(
            f"{label} cold open vs v8",
            helix["reopen_seconds"] / networkx["reopen_seconds"],
            5.0,
        )
        check(
            f"{label} active store vs v8",
            helix["disk_after_ingest_bytes"] / networkx["disk_bytes"],
            3.0,
        )
        check(
            f"{label} post-update store vs v8",
            helix["disk_after_update_bytes"] / networkx["disk_bytes"],
            3.0,
        )
        if row["nodes"] == 20_000:
            check(
                f"{label} clustering speedup",
                networkx["community_seconds"] / helix["community_seconds"],
                3.0,
                ">=",
            )
            check(
                f"{label} node centrality speedup",
                networkx["node_betweenness_seconds"] / helix["node_betweenness_seconds"],
                3.0,
                ">=",
            )
            check(
                f"{label} edge centrality speedup",
                networkx["edge_betweenness_seconds"] / helix["edge_betweenness_seconds"],
                3.0,
                ">=",
            )
        check(f"{label} hot_open_seconds", helix["hot_open_seconds"], hot_limit)
        for metric, baseline_metric in (
            ("neighbor_20_queries_seconds", "neighbor_20_queries_seconds"),
            ("bfs_seconds", "bfs_seconds"),
            ("shortest_path_5_queries_seconds", "shortest_path_5_queries_seconds"),
        ):
            check(f"{label} {metric}", helix[metric], hot_limit)
            check(
                f"{label} {metric} vs v8",
                helix[metric] / networkx[baseline_metric],
                2.0,
            )
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def _bounded_bfs(graph, start: Any, depth: int) -> list[Any]:
    visited = {start}
    frontier = {start}
    for _ in range(depth):
        frontier = {neighbor for node in frontier for neighbor in graph.neighbors(node)} - visited
        visited.update(frontier)
    return list(visited)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("benchmarks/helix-vs-networkx.json"))
    parser.add_argument("--memory-backend", choices=("networkx", "helix"))
    parser.add_argument("--memory-nodes", type=int)
    parser.add_argument("--memory-edges", type=int)
    parser.add_argument("--check-gates", action="store_true")
    args = parser.parse_args()
    if args.memory_backend:
        if args.memory_nodes is None or args.memory_edges is None:
            parser.error("--memory-backend requires --memory-nodes and --memory-edges")
        print(memory_only(args.memory_backend, args.memory_nodes, args.memory_edges))
        return
    root = Path(tempfile.mkdtemp(prefix="graphify-benchmark-"))
    try:
        results = [run_size(nodes, edges, root) for nodes, edges in SIZES]
        report = {
            "helix_revision": "0.2.0b3",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "results": results,
            "acceptance": acceptance_gates(results),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        if args.check_gates and not report["acceptance"]["passed"]:
            raise SystemExit(1)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
