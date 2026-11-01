"""QML-013-AC03 Qt event links cannot disappear or look like runtime calls."""
import json

import pytest

from graphify.build import build_from_json
from graphify.callflow_html import preferred_edges, generate_call_table_rows
from graphify.callflow_html import write_callflow_html
from graphify.export import to_json
from graphify.qt_relationship_views import render_relationship_table
from tests.qt_analysis_helpers import analysis
from tests.test_qt_signals_slots import SOURCE


def test_html_keeps_native_connections_and_subscriptions_with_ordinary_calls(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    connection = next(edge for edge in result["edges"] if edge.get("context") == "qt_connect_signal")
    assert connection in preferred_edges(result["edges"])
    table = render_relationship_table(result["nodes"], result["edges"])
    assert 'connection signal' in table and 'signal emission' in table and 'runtime delivery is unverified' in table
    assert 'events.cpp:' in table and 'INFERRED' in table


def test_signal_emission_is_not_rendered_as_a_caller_in_the_call_table(tmp_path):
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    emission = next(edge for edge in result["edges"] if edge.get("context") == "qt_signal_emit")
    target = next(node for node in result["nodes"] if node["id"] == emission["target"])
    rows = generate_call_table_rows([target], [emission], "en", [emission], result["nodes"])
    assert "Qt emission:" not in rows


@pytest.mark.parametrize("directed", [False, True], ids=["default-graph", "directed-graph"])
def test_qml013_ac03_written_html_keeps_source_event_evidence_and_escapes_labels(tmp_path, directed):
    """The saved HTML artifact exposes facts, source spans and uncertainty safely."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    connection = next(edge for edge in result["edges"] if edge.get("context") == "qt_connect_signal")
    for _, node in graph.nodes(data=True):
        node["community"] = 0
    graph.nodes[connection["source"]]["label"] = '<script>alert(1)</script>'
    output = tmp_path / "graphify-out"
    output.mkdir(exist_ok=True)
    assert to_json(graph, {}, str(output / "graph.json"), force=True)
    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps([{"id": "qt", "name": "Qt facts", "communities": [0]}]), encoding="utf-8")
    artifact = write_callflow_html(tmp_path, sections=sections, output="graphify-out/events.html", lang="en")
    html = artifact.read_text(encoding="utf-8")
    assert 'class="qt-qml-relationships"' in html
    assert 'data-source-id="' + connection["source"] + '"' in html
    assert 'data-target-id="' + connection["target"] + '"' in html
    assert "connection signal" in html and "signal emission" in html
    assert "events.cpp:L" in html and "INFERRED" in html
    assert "runtime delivery is unverified" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and '<script>alert(1)</script>' not in html
