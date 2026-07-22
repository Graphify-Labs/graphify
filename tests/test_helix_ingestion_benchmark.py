from benchmarks.helix_vs_networkx import acceptance_gates


def _result(nodes: int, edges: int) -> dict:
    return {
        "nodes": nodes,
        "edges": edges,
        "networkx": {
            "reopen_seconds": 1.0,
            "disk_bytes": 100,
            "community_seconds": 3.0,
            "node_betweenness_seconds": 3.0,
            "edge_betweenness_seconds": 3.0,
            "neighbor_20_queries_seconds": 1.0,
            "bfs_seconds": 1.0,
            "shortest_path_5_queries_seconds": 1.0,
        },
        "helix": {
            "ingest_seconds": 5.0 if nodes == 5_000 else 17.0,
            "mixed_label_ingest_seconds": 5.0 if nodes == 5_000 else 17.0,
            "incremental_1pct_seconds": 1.9,
            "post_delta_store_ratio": 1.2,
            "peak_rss_delta_bytes": 599 * 1024 * 1024,
            "reopen_seconds": 0.1,
            "disk_after_ingest_bytes": 200,
            "disk_after_update_bytes": 210,
            "community_seconds": 1.0,
            "node_betweenness_seconds": 1.0,
            "edge_betweenness_seconds": 1.0,
            "hot_open_seconds": 0.01,
            "neighbor_20_queries_seconds": 0.01,
            "bfs_seconds": 0.01,
            "shortest_path_5_queries_seconds": 0.01,
        },
    }


def test_ingestion_acceptance_uses_absolute_gates_and_keeps_other_gates() -> None:
    results = [_result(5_000, 15_000), _result(20_000, 60_000)]

    accepted = acceptance_gates(results)

    assert accepted["passed"]
    names = {check["name"] for check in accepted["checks"]}
    assert "20000/60000 ingest seconds" in names
    assert "20000/60000 mixed-label ingest seconds" in names
    assert "20000/60000 1% production delta seconds" in names
    assert "20000/60000 peak ingest RSS MiB" in names
    assert "20000/60000 clustering speedup" in names
    assert not any("ingest vs v8" in name or "update vs v8" in name for name in names)

    results[1]["helix"]["ingest_seconds"] = 18.01
    rejected = acceptance_gates(results)

    assert not rejected["passed"]
    failed = [check for check in rejected["checks"] if not check["passed"]]
    assert [check["name"] for check in failed] == ["20000/60000 ingest seconds"]
