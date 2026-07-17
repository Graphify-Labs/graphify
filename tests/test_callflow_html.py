import subprocess
import sys
from pathlib import Path

import pytest

from graphify.callflow_html import derive_sections_from_communities, load_graph, write_callflow_html
from graphify.helix.state import new_state
from tests.native_helpers import make_loaded


def _make_graphify_out(root: Path, *, external: bool = False) -> Path:
    out = root / "graphify-out"
    out.mkdir(parents=True)
    prefix = "External" if external else ""
    nodes = [
        {"id": "api", "label": prefix + "ApiClient", "source_file": "src/api.py", "file_type": "code"},
        {"id": "run", "label": prefix + "run()", "source_file": "src/main.py", "file_type": "code"},
        {"id": "export", "label": prefix + "write_html()", "source_file": "src/export.py", "file_type": "code"},
        {"id": "evil", "label": "<script>alert(1)</script>", "source_file": "src/evil.py", "file_type": "code"},
    ]
    state = new_state(communities=[
        {"id": 0, "members": ["api", "run"], "name": prefix + "Runtime", "cohesion": 0.8},
        {"id": 1, "members": ["export", "evil"], "name": prefix + "Export", "cohesion": 0.7},
    ])
    make_loaded(
        out,
        nodes=nodes,
        edges=[
            {"source": "run", "target": "api", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "api", "target": "export", "relation": "uses", "confidence": "EXTRACTED"},
            {"source": "export", "target": "evil", "relation": "calls", "confidence": "EXTRACTED"},
        ],
        state=state,
    )
    (out / "GRAPH_REPORT.md").write_text(
        "# Graph Report\n\n## God Nodes\n1. `Transformer` - 2 edges\n",
        encoding="utf-8",
    )
    return out


def test_write_callflow_html_uses_native_store_and_report(tmp_path):
    out = _make_graphify_out(tmp_path)
    path = write_callflow_html(tmp_path, output=out / "callflow.html", max_sections=4)
    content = path.read_text(encoding="utf-8")
    assert "mermaid" in content and "Transformer" in content and "ApiClient" in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content


def test_export_callflow_cli_accepts_default_and_positional_native_store(tmp_path):
    out = _make_graphify_out(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "export", "callflow-html", "--output", str(out / "default.html")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    external = _make_graphify_out(tmp_path / "external", external=True)
    positional = subprocess.run(
        [sys.executable, "-m", "graphify", "export", "callflow-html", str(external / "graph.helix"), "--output", str(tmp_path / "positional.html")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert positional.returncode == 0, positional.stderr
    html = (tmp_path / "positional.html").read_text()
    assert "ExternalApiClient" in html and "ApiClient" in html


def test_derive_sections_groups_by_architecture_keywords():
    nodes = [
        {"id": "extract", "label": "extract_python", "source_file": "graphify/extract.py", "community": 0},
        {"id": "html", "label": "to_html", "source_file": "graphify/export.py", "community": 1},
        {"id": "test", "label": "test_export_html", "source_file": "tests/test_export.py", "community": 2},
    ]
    ids = {section["id"] for section in derive_sections_from_communities(nodes, {}, "en", 6)}
    assert {"extract-pipeline", "outputs-docs", "tests-fixtures"} <= ids


def test_load_graph_rejects_legacy_json(tmp_path):
    legacy = tmp_path / "graph.json"
    legacy.write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        load_graph(legacy)
