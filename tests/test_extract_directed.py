"""Regression tests for Graphify issue #3495: opt-in --directed flag for extract."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

PYTHON = sys.executable

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _create_sample_code_repo(tmp_path: Path) -> Path:
    proj = tmp_path / "sample_repo"
    proj.mkdir(parents=True, exist_ok=True)
    # Caller calls callee
    (proj / "callee.py").write_text(
        "def helper():\n    return 42\n",
        encoding="utf-8",
    )
    (proj / "caller.py").write_text(
        "from callee import helper\n\n"
        "def main():\n    return helper()\n",
        encoding="utf-8",
    )
    return proj


def test_extract_help_mentions_directed():
    """`graphify extract --help` should describe --directed."""
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "extract", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "--directed" in r.stdout
    assert "DiGraph" in r.stdout or "directed" in r.stdout.lower()


def test_extract_without_directed_is_undirected(tmp_path):
    """By default, extract preserves existing behavior: directed=false, nx.Graph."""
    proj = _create_sample_code_repo(tmp_path)
    r = _run(["extract", str(proj), "--code-only"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data.get("directed") is False, f"Expected directed: false, got {data.get('directed')}"

    # Links should have source -> target preserved
    links = data.get("links", data.get("edges", []))
    call_links = [l for l in links if l.get("relation") == "calls"]
    assert len(call_links) > 0
    # caller should be source, helper/callee should be target
    for link in call_links:
        assert "caller" in link["source"]
        assert "helper" in link["target"] or "callee" in link["target"]


def test_extract_with_directed_flag(tmp_path):
    """With --directed, graph.json has directed=true, built as DiGraph."""
    proj = _create_sample_code_repo(tmp_path)
    r = _run(["extract", str(proj), "--code-only", "--directed"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data.get("directed") is True, f"Expected directed: true, got {data.get('directed')}"

    links = data.get("links", data.get("edges", []))
    call_links = [l for l in links if l.get("relation") == "calls"]
    assert len(call_links) > 0
    for link in call_links:
        assert "caller" in link["source"]
        assert "helper" in link["target"] or "callee" in link["target"]


def test_extract_no_cluster_with_directed(tmp_path):
    """`--no-cluster --directed` persists directed: true in graph.json."""
    proj = _create_sample_code_repo(tmp_path)
    r = _run(["extract", str(proj), "--code-only", "--no-cluster", "--directed"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data.get("directed") is True, f"Expected directed: true, got {data.get('directed')}"

    links = data.get("links", data.get("edges", []))
    call_links = [l for l in links if l.get("relation") == "calls"]
    assert len(call_links) > 0
    for link in call_links:
        assert "caller" in link["source"]
        assert "helper" in link["target"] or "callee" in link["target"]


def test_extract_no_cluster_without_directed(tmp_path):
    """`--no-cluster` without `--directed` preserves current output behavior (no directed key)."""
    proj = _create_sample_code_repo(tmp_path)
    r = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "directed" not in data, f"Expected no directed key, got {data.get('directed')}"


def test_incremental_preserves_directed_clustered(tmp_path):
    """An incremental extract without --directed does not silently downgrade a directed graph."""
    proj = _create_sample_code_repo(tmp_path)
    # First run with --directed
    r1 = _run(["extract", str(proj), "--code-only", "--directed"], tmp_path)
    assert r1.returncode == 0, r1.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    data1 = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data1.get("directed") is True

    # Modify caller.py slightly
    (proj / "caller.py").write_text(
        "from callee import helper\n\n"
        "def main():\n    # touched\n    return helper()\n",
        encoding="utf-8",
    )

    # Re-run extract WITHOUT --directed
    r2 = _run(["extract", str(proj), "--code-only"], tmp_path)
    assert r2.returncode == 0, r2.stderr

    data2 = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data2.get("directed") is True, (
        "Incremental run must not downgrade directed graph to undirected"
    )


def test_incremental_preserves_directed_no_cluster(tmp_path):
    """An incremental --no-cluster extract without --directed does not downgrade directed graph."""
    proj = _create_sample_code_repo(tmp_path)
    # First run with --no-cluster --directed
    r1 = _run(["extract", str(proj), "--code-only", "--no-cluster", "--directed"], tmp_path)
    assert r1.returncode == 0, r1.stderr

    graph_path = proj / "graphify-out" / "graph.json"
    data1 = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data1.get("directed") is True

    # Modify caller.py slightly
    (proj / "caller.py").write_text(
        "from callee import helper\n\n"
        "def main():\n    # touched\n    return helper()\n",
        encoding="utf-8",
    )

    # Re-run extract --no-cluster WITHOUT --directed
    r2 = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert r2.returncode == 0, r2.stderr

    data2 = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data2.get("directed") is True, (
        "Incremental --no-cluster run must not downgrade directed graph to undirected"
    )


def test_query_traversal_on_directed_graph(monkeypatch, tmp_path, capsys):
    """`graphify query` on a directed graph still traverses bidirectionally (finds callers when querying callee)."""
    import graphify.__main__ as mainmod

    # Create a directed graph on disk
    G = nx.DiGraph()
    G.add_node("caller", label="caller_fn", source_file="a.py", source_location="L1", community=0)
    G.add_node("callee", label="callee_fn", source_file="b.py", source_location="L1", community=0)
    G.add_edge("caller", "callee", relation="calls", confidence="EXTRACTED", context="call")

    from networkx.readwrite import json_graph
    data = json_graph.node_link_data(G, edges="links")
    assert data.get("directed") is True

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "callee_fn", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    # Traversing backwards to caller must succeed even though graph on disk is directed
    assert "caller_fn" in out
    assert "caller_fn --calls" in out
