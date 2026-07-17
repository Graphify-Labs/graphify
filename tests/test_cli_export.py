"""End-to-end native CLI query and presentation export tests."""

import os
import subprocess
import sys
from pathlib import Path

from graphify.helix.state import new_state
from tests.native_helpers import make_loaded


def _project(tmp_path: Path) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True)
    state = new_state(communities=[
        {"id": 0, "members": ["a", "b"], "name": "Runtime", "cohesion": 0.9},
        {"id": 1, "members": ["c"], "name": "Storage", "cohesion": 1.0},
    ])
    make_loaded(
        out,
        nodes=[
            {"id": "a", "label": "App", "source_file": "app.py", "file_type": "code"},
            {"id": "b", "label": "Service", "source_file": "service.py", "file_type": "code"},
            {"id": "c", "label": "Database", "source_file": "db.py", "file_type": "code"},
        ],
        edges=[
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "b", "target": "c", "relation": "uses", "confidence": "INFERRED"},
        ],
        state=state,
    )
    return tmp_path


def _run(project: Path, *args: str, env=None):
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args], cwd=project,
        capture_output=True, text=True, env=env,
    )


def test_html_and_no_viz(tmp_path):
    project = _project(tmp_path)
    html = tmp_path / "custom.html"
    result = _run(project, "export", "html", "--output", str(html))
    assert result.returncode == 0, result.stderr
    assert "App" in html.read_text()
    result = _run(project, "export", "html", "--output", str(html), "--no-viz")
    assert result.returncode == 0 and not html.exists()


def test_obsidian_wiki_graphml_and_cypher(tmp_path):
    project = _project(tmp_path)
    targets = {
        "obsidian": tmp_path / "vault",
        "wiki": tmp_path / "wiki",
        "graphml": tmp_path / "graph.graphml",
        "neo4j": tmp_path / "cypher.txt",
    }
    for kind, target in targets.items():
        result = _run(project, "export", kind, "--output", str(target))
        assert result.returncode == 0, f"{kind}: {result.stderr}"
    assert (targets["vault"] if "vault" in targets else targets["obsidian"]).exists()
    assert (targets["wiki"] / "index.md").exists()
    assert "graphml" in targets["graphml"].read_text()
    assert "MERGE" in targets["neo4j"].read_text()


def test_query_path_and_explain_read_native_store(tmp_path):
    project = _project(tmp_path)
    query = _run(project, "query", "Service")
    path = _run(project, "path", "App", "Database")
    explain = _run(project, "explain", "Service")
    assert query.returncode == 0 and "Service" in query.stdout
    assert path.returncode == 0 and "App --calls [EXTRACTED]--> Service --uses [INFERRED]--> Database" in path.stdout
    assert explain.returncode == 0 and "Node: Service" in explain.stdout


def test_positional_native_store_for_export(tmp_path):
    project = _project(tmp_path)
    output = tmp_path / "positional.graphml"
    result = _run(
        project, "export", "graphml", str(project / "graphify-out" / "graph.helix"),
        "--output", str(output),
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()


def test_graphify_out_absolute_override(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    configured = tmp_path / "shared-output"
    configured.mkdir()
    make_loaded(
        configured,
        nodes=[{"id": "x", "label": "OverrideNode", "source_file": "x.py"}],
    )
    env = dict(os.environ, GRAPHIFY_OUT=str(configured))
    result = _run(project, "query", "OverrideNode", env=env)
    assert result.returncode == 0, result.stderr
    assert "OverrideNode" in result.stdout
