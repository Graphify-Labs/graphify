import json
import os
import subprocess
import sys
import pytest
import networkx as nx
from pathlib import Path

def test_heal_cli_usage_when_no_args():
    res = subprocess.run(
        [sys.executable, "-m", "graphify", "heal"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 1
    assert "Usage: graphify heal" in res.stderr

def test_heal_cli_dry_run_with_passing_suite(tmp_path):
    test_file = tmp_path / "test_dummy.py"
    test_file.write_text("def test_ok(): pass\n")

    res = subprocess.run(
        [sys.executable, "-m", "graphify", "heal", f"{sys.executable} -m pytest {test_file}"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0
    assert "All tests passed! Nothing to heal." in res.stdout

def test_heal_cli_dry_run_with_failing_suite(tmp_path):
    test_file = tmp_path / "test_broken.py"
    test_file.write_text("def test_fail(): assert False\n")

    G = nx.DiGraph()
    G.add_node(str(test_file), source_file=str(test_file), label="test_broken", node_type="module")
    graph_path = tmp_path / "graph.json"
    data = nx.node_link_data(G)
    graph_path.write_text(json.dumps(data))

    cmd = [
        sys.executable, "-m", "graphify", "heal",
        f"{sys.executable} -m pytest {test_file}",
        "--graph", str(graph_path),
        "--dry-run"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "Detected 1 test failure(s)" in res.stdout
    assert "Dry-run active: diagnostic graph slice complete." in res.stdout

def test_heal_cli_failing_suite_missing_graph(tmp_path):
    test_file = tmp_path / "test_broken.py"
    test_file.write_text("def test_fail(): assert False\n")

    cmd = [
        sys.executable, "-m", "graphify", "heal",
        f"{sys.executable} -m pytest {test_file}",
        "--graph", str(tmp_path / "non_existent_graph.json")
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "error: graph file not found" in res.stderr

def test_heal_cli_missing_backend_fails_gracefully(tmp_path):
    test_file = tmp_path / "test_broken.py"
    test_file.write_text("def test_fail(): assert False\n")

    G = nx.DiGraph()
    G.add_node(str(test_file), source_file=str(test_file), label="test_broken", node_type="module")
    graph_path = tmp_path / "graph.json"
    data = nx.node_link_data(G)
    graph_path.write_text(json.dumps(data))

    env = os.environ.copy()
    env["GRAPHIFY_BACKEND"] = "off"
    # Remove any ambient API keys
    for key in list(env.keys()):
        if any(b in key.lower() for b in ["openai", "anthropic", "gemini", "claude", "bedrock", "azure"]):
            env.pop(key, None)

    cmd = [
        sys.executable, "-m", "graphify", "heal",
        f"{sys.executable} -m pytest {test_file}",
        "--graph", str(graph_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 1
    assert "no LLM backend configured" in res.stderr
