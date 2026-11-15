"""`graphify query` prints the same answer whatever the string-hash seed.

`_bfs` walked each level as a ``set`` of node ids, so the EDGE lines came out
in string-hash order, which CPython randomizes per process. The same query on
the same graph gave a different answer on every run, and the order also decided
which edges survived the token budget. `query` is not one of the commands that
pin PYTHONHASHSEED, and the MCP server runs the same traversal in a
long-lived process, so the order has to come from the walk itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_graph(tmp_path: Path) -> Path:
    # One seed with 60 neighbours, each with three leaves: the second BFS level
    # is a 60-node frontier, so a hash-ordered walk has 60! orders to pick from.
    G = nx.Graph()
    G.add_node("seed", label="widget", source_file="widget.py", source_location="L1")
    for i in range(60):
        mid = f"mid_{i}"
        G.add_node(mid, label=f"helper_{i}", source_file=f"h{i}.py", source_location="L1")
        G.add_edge("seed", mid, relation="calls", confidence="EXTRACTED")
        for j in range(3):
            leaf = f"leaf_{i}_{j}"
            G.add_node(leaf, label=f"leaf_{i}_{j}", source_file=f"h{i}.py", source_location=f"L{j + 2}")
            G.add_edge(mid, leaf, relation="contains", confidence="EXTRACTED")
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return path


def _query(graph: Path, seed: str, *extra: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO_ROOT)}
    env.pop("PYTEST_CURRENT_TEST", None)
    proc = subprocess.run(
        [sys.executable, "-m", "graphify", "query", "widget", "--graph", str(graph),
         "--budget", "20000", *extra],
        capture_output=True, text=True, env=env, cwd=graph.parent, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "EDGE" in proc.stdout
    return proc.stdout


def test_bfs_query_output_does_not_depend_on_hash_seed(tmp_path):
    graph = _write_graph(tmp_path)
    outputs = {_query(graph, seed) for seed in ("1", "2", "3")}
    assert len(outputs) == 1


def test_dfs_query_output_does_not_depend_on_hash_seed(tmp_path):
    graph = _write_graph(tmp_path)
    outputs = {_query(graph, seed, "--dfs") for seed in ("1", "2", "3")}
    assert len(outputs) == 1
