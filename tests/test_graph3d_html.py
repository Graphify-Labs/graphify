import json
import subprocess
import sys
from pathlib import Path

from graphify.exporters.base import COMMUNITY_COLORS
from graphify.graph3d_html import build_graph3d_data, write_graph3d_html


def _make_graphify_out(tmp_path: Path) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "api", "label": "ApiClient", "source_file": "src/api.py", "file_type": "code", "community": 0},
            {"id": "run", "label": "run()", "source_file": "src/main.py", "file_type": "code", "community": 0},
            {"id": "exp", "label": "write_html()", "source_file": "src/export.py", "file_type": "code", "community": 1},
            {"id": "evil", "label": "<script>alert(1)</script>", "source_file": "src/evil.py", "file_type": "code", "community": 1},
        ],
        "links": [
            {"source": "run", "target": "api", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "api", "target": "exp", "relation": "uses", "confidence": "INFERRED"},
            # dangling: target not in nodes -> must be dropped
            {"source": "exp", "target": "ghost", "relation": "calls", "confidence": "EXTRACTED"},
        ],
        "hyperedges": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / ".graphify_labels.json").write_text(
        json.dumps({"0": "Runtime", "1": "Export"}), encoding="utf-8"
    )
    return out


def test_build_graph3d_data_drops_dangling_and_maps_labels(tmp_path):
    out = _make_graphify_out(tmp_path)
    graph = json.loads((out / "graph.json").read_text())
    data = build_graph3d_data(graph, labels={0: "Runtime", 1: "Export"})

    assert len(data["nodes"]) == 4
    # the ghost-target link is dropped, the two real links survive
    assert len(data["links"]) == 2
    api = next(n for n in data["nodes"] if n["id"] == "api")
    assert api["community_name"] == "Runtime"
    assert api["degree"] == 2  # run->api and api->exp


def test_write_graph3d_html_renders_and_escapes(tmp_path):
    out = _make_graphify_out(tmp_path)
    dest = out / "GRAPH_3D.html"
    write_graph3d_html(graph_path=out / "graph.json", output_path=dest, project_label="demo")
    html = dest.read_text(encoding="utf-8")

    # the 3D engine, the direction arrows, and the runtime escaper are all present
    assert "ForceGraph3D()" in html
    assert "linkDirectionalArrowLength" in html
    assert "function esc(" in html
    # community palette is embedded for coloring
    assert COMMUNITY_COLORS[0] in html
    # the malicious label cannot break out of the <script> data block
    assert "alert(1)</script>" not in html
    assert "alert(1)<\\/script>" in html


def test_cli_graph3d_creates_file(tmp_path):
    out = _make_graphify_out(tmp_path)
    dest = tmp_path / "viewer.html"
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "graph3d",
         "--graph", str(out / "graph.json"), "--output", str(dest), "--label", "demo"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert dest.is_file()
    assert "ForceGraph3D()" in dest.read_text(encoding="utf-8")
