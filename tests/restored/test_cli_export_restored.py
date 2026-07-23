"""CLI behaviors not subsumed by the bundled native export/query tests."""
from __future__ import annotations

import os
import subprocess
import sys

from graphify.helix.persistence import load_graph


def _run(cwd, *args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def test_export_html_error_without_graph(tmp_path):
    assert _run(tmp_path, "export", "html").returncode != 0


def test_query_missing_graph_fails(tmp_path):
    assert _run(tmp_path, "query", "anything").returncode != 0


def test_path_missing_graph_fails(tmp_path):
    assert _run(tmp_path, "path", "a", "b").returncode != 0


def test_explain_missing_graph_fails(tmp_path):
    assert _run(tmp_path, "explain", "anything").returncode != 0


def test_export_unknown_format_fails(tmp_path):
    assert _run(tmp_path, "export", "pdf").returncode != 0


def test_extract_writes_to_graphify_out_env(tmp_path):
    (tmp_path / "m.py").write_text("def a():\n    return 1\n")
    env = dict(os.environ, GRAPHIFY_OUT="custom-out")
    result = _run(tmp_path, "extract", ".", "--code-only", "--no-cluster", env=env)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "custom-out" / "graph.helix").is_dir()
    assert not (tmp_path / "graphify-out").exists()


def test_extract_out_does_not_pollute_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("def main():\n    return 1\n")
    output = tmp_path / "scratch"
    result = _run(
        tmp_path,
        "extract",
        str(corpus),
        "--out",
        str(output),
        "--no-cluster",
        "--code-only",
    )
    assert result.returncode == 0, result.stderr
    assert (output / "graphify-out" / "graph.helix").is_dir()
    assert not (corpus / "graphify-out").exists()


def test_update_no_cluster_writes_native_store(tmp_path):
    (tmp_path / "sample.py").write_text("def f():\n    return 1\n")
    result = _run(tmp_path, "update", ".", "--no-cluster")
    assert result.returncode == 0, result.stderr
    loaded = load_graph(tmp_path / "graphify-out" / "graph.helix")
    assert loaded.graph.node_count > 0
