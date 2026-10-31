"""D37: path confidence and actual source evidence survive CLI/MCP agreement."""
from __future__ import annotations

import json

from networkx.readwrite import json_graph
import pytest

from graphify.export import to_json
from graphify.serve import _shortest_path_text
from tests.qt_consumer_helpers import cli, saved_graph
from tests.test_path_confidence import REPORT_SUMMARY, _report_graph


@pytest.mark.parametrize("profile", ["generic-scored", "qml-extracted"])
def test_req_qml010_ac04_path_keeps_sources_before_one_final_confidence(
        tmp_path, monkeypatch, capsys, profile):
    """Persist actual build/QML facts; both text consumers retain the same proof."""
    if profile == "generic-scored":
        graph = _report_graph()
        path = tmp_path / "graph.json"
        assert to_json(graph, {}, str(path), force=True)
        source, target = "report_exporter_run", "report_pdfreport_build"
        summary, location = REPORT_SUMMARY, "Report.cs:L7"
    else:
        path, _, component, prop, _ = saved_graph(tmp_path)
        source, target = component["id"], prop["id"]
        summary = "Path confidence: EXTRACTED (weakest hop 1: contains)"
        location = "Main.qml:L"

    before = path.read_bytes()
    data = json.loads(before)
    # Consumers read the persisted transport, retaining parallel/directed links.
    loaded = json_graph.node_link_graph(
        {**data, "directed": True, "multigraph": True}, edges="links"
    )
    actual = cli(monkeypatch, capsys, path, "path", source, target)
    mcp = _shortest_path_text(loaded, {"source": source, "target": target})
    assert actual == mcp
    lines = actual.splitlines()
    assert lines[0].startswith("Shortest path (")
    assert "Source evidence:" in lines and location in actual
    assert lines[-1] == summary
    assert sum(line.startswith("Path confidence:") for line in lines) == 1
    assert lines.index("Source evidence:") < len(lines) - 1
    assert path.read_bytes() == before
