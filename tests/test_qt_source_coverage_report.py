"""QML-010/013 reports distinguish source resolution coverage from Qt runtime proof."""
import copy
import json

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_coverage import source_coverage
from graphify.report import generate
from tests.qt_analysis_helpers import analysis, sites


def report(graph):
    return generate(graph, {0: list(graph)}, {0: 0.5}, {0: "Source facts"}, [], [],
                    {"total_files": 2, "total_words": 100, "warning": None}, {}, "public-project")


def corpus(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(QUrl computed){{ QQmlApplicationEngine engine;
 engine.load(QUrl("{url}")); engine.load(computed);
 engine.load(QUrl("https://example.test/Main.qml")); engine.load(QUrl("qrc:/missing.qml"));
 engine.load(QUrl("qrc:/duplicate.qml")); }}'''
    qrc = '<RCC><qresource><file alias="duplicate.qml">Main.qml</file><file alias="duplicate.qml">Main.qml</file></qresource></RCC>'
    return analysis(tmp_path, {"Main.qml": 'import QtQml\nQtObject { property int value: unknown }',
                              "use.cpp": source, "resources.qrc": qrc})


def test_report_actual_source_status_counts_survive_json_reload_and_do_not_mutate_graph(tmp_path):
    """Real supported, computed, duplicate and unavailable loads stay distinct."""
    result = corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path)
    states = {qt_metadata(node)["status"] for node in sites(result, "qml_load")}
    assert states == {"resolved", "dynamic", "unsupported", "unavailable", "ambiguous"}
    before = copy.deepcopy((dict(graph.nodes(data=True)), list(graph.edges(data=True))))
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert source_coverage(loaded) == source_coverage(graph)
    summary = report(loaded)
    for state in ("Resolved", "Ambiguous", "Dynamic", "Unsupported", "Unavailable", "Error", "Other / no status"):
        assert state in summary
    row = source_coverage(graph)["qt"]
    assert all(row[status] >= 1 for status in states)
    assert "not a percentage of supported language syntax" in summary
    assert "signal delivery, ordering, or thread safety" in summary
    assert "absence from this graph is not proof" in summary
    assert (dict(graph.nodes(data=True)), list(graph.edges(data=True))) == before


def test_report_invalid_source_transport_counts_as_error_without_exposing_payload(tmp_path):
    """Corrupt accepted-source metadata remains an explicit bounded reporting gap."""
    result = corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path)
    site = sites(result, "qml_load")[0]
    raw = graph.nodes[site["id"]]["metadata"]["qt"]["raw_values"]
    raw["raw_name"] = "<private-payload-not-base64>"
    count = source_coverage(graph)["qt"]
    assert count["error"] == 1 and count["invalid_metadata"] == 1
    summary = report(graph)
    assert "1 source fact(s) have invalid semantic metadata" in summary
    assert "private-payload" not in summary


def test_report_future_or_unowned_metadata_cannot_claim_source_coverage(tmp_path):
    """The new section stays absent for generic graphs and unsupported contracts."""
    result = analysis(tmp_path, {"plain.py": 'def ordinary():\n    return 1\n'})
    graph = build_from_json(result, root=tmp_path)
    assert "Qt/QML source coverage" not in report(graph)
    node = next(iter(graph))
    graph.nodes[node]["metadata"] = {"qt": {"contract_version": 2, "kind": "connect", "status": "resolved",
                                             "span": {"start_byte": 0, "end_byte": 1}}}
    assert not source_coverage(graph)
    graph.nodes[node]["metadata"]["qt"]["contract_version"] = 1
    graph.nodes[node]["metadata"]["qt"].pop("span")
    assert not source_coverage(graph) and "Qt/QML source coverage" not in report(graph)
