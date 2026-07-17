"""Native incremental command integration tests."""

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


def test_semantic_failure_does_not_create_native_store(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Introduction\nSystem design.")
    result = _run(tmp_path, "extract", str(docs))
    assert result.returncode != 0
    assert not (docs / "graphify-out" / "graph.helix").exists()


def test_warm_code_extract_preserves_topology_and_uses_native_cache(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def alpha():\n    return 1\n")
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
    assert after.state["incremental"]["extraction_cache"]


def test_update_prunes_removed_import_edge(tmp_path):
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
