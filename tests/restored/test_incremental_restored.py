"""Restored incremental-build tests against durable native generation state."""

from __future__ import annotations

import os
import subprocess
import sys

from graphify.helix.model import edge_attributes
from graphify.helix.persistence import load_graph


_KEYS = {
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL", "AWS_PROFILE",
}


def _run(cwd, *args):
    env = {key: value for key, value in os.environ.items() if key not in _KEYS}
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args], cwd=cwd,
        capture_output=True, text=True, env=env,
    )


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def a():\n    return 1\n")
    return root


def test_manifest_written_after_extract(tmp_path):
    project = _project(tmp_path)
    result = _run(tmp_path, "extract", str(project), "--code-only", "--no-cluster")
    assert result.returncode == 0, result.stderr

    loaded = load_graph(project / "graphify-out" / "graph.helix")
    assert "a.py" in loaded.state["incremental"]["files"]
    assert loaded.state["incremental"]["files"]["a.py"]["content_hash"]
    assert not (project / "graphify-out" / "manifest.json").exists()


def test_incremental_mode_detected_via_manifest(tmp_path):
    project = _project(tmp_path)
    first = _run(tmp_path, "extract", str(project), "--code-only", "--no-cluster")
    assert first.returncode == 0, first.stderr
    store = project / "graphify-out" / "graph.helix"
    before = load_graph(store)

    second = _run(tmp_path, "update", str(project), "--no-cluster")
    assert second.returncode == 0, second.stderr
    after = load_graph(store)

    assert after.state["incremental"]["extractor_state"]["mode"] == "ast"
    assert after.state["incremental"]["extraction_cache"]
    assert (after.graph.node_count, after.graph.edge_count) == (
        before.graph.node_count, before.graph.edge_count,
    )


def test_no_incremental_without_manifest(tmp_path):
    project = _project(tmp_path)
    result = _run(tmp_path, "update", str(project), "--no-cluster")
    assert result.returncode == 0, result.stderr
    loaded = load_graph(project / "graphify-out" / "graph.helix")
    assert loaded.graph.node_count > 0
    assert loaded.state["incremental"]["files"]


def test_extract_no_cluster_incremental_noop_preserves_existing_graph(tmp_path):
    project = _project(tmp_path)
    first = _run(tmp_path, "extract", str(project), "--code-only", "--no-cluster")
    assert first.returncode == 0, first.stderr
    store = project / "graphify-out" / "graph.helix"
    before = load_graph(store)

    second = _run(tmp_path, "extract", str(project), "--code-only", "--no-cluster")
    assert second.returncode == 0, second.stderr
    after = load_graph(store)

    assert (after.graph.node_count, after.graph.edge_count) == (
        before.graph.node_count, before.graph.edge_count,
    )


def test_update_prunes_a_removed_imports_edge(tmp_path):
    project = tmp_path / "project"
    package = project / "pkg"
    package.mkdir(parents=True)
    (package / "b.py").write_text("def helper():\n    return 1\n")
    source = package / "a.py"
    source.write_text("from pkg.b import helper\ndef use():\n    return helper()\n")
    first = _run(tmp_path, "extract", str(project), "--code-only", "--no-cluster")
    assert first.returncode == 0, first.stderr
    store = project / "graphify-out" / "graph.helix"
    before = load_graph(store)
    assert any(
        edge_attributes(edge).get("relation") in {"imports", "imports_from"}
        and str(edge_attributes(edge).get("source_file", "")).endswith("a.py")
        for edge in before.graph.edges()
    )

    source.write_text("def use():\n    return 1\n")
    updated = _run(tmp_path, "update", str(project), "--no-cluster")
    assert updated.returncode == 0, updated.stderr
    after = load_graph(store)
    assert not any(
        edge_attributes(edge).get("relation") in {"imports", "imports_from"}
        and str(edge_attributes(edge).get("source_file", "")).endswith("a.py")
        for edge in after.graph.edges()
    )
