"""REQ-QML-022-AC06: a graph owns one read-only metaobject validation index."""
from __future__ import annotations

from graphify.build import build_from_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_metaobject import QtMetaobjectIndex
from tests.qt_analysis_helpers import analysis
from tests.qt_metaobject_helpers import sources


def test_graph_assembly_reuses_own_metaobject_context_for_repeated_native_edges(tmp_path, monkeypatch):
    """Twenty real bindings preserve proof without rebuilding the complete index per edge."""
    files = sources()
    files["Main.qml"] = "import Public.Probe 1.0\nService {\n" + "\n".join(
        f"property int result{i}: ownMethod()" for i in range(20)) + "\n}\n"
    result = analysis(tmp_path, files)
    expected = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
    assert len(expected) == 20
    calls, initialize = [], QtMetaobjectIndex.__init__

    def observe(self, *args, **kwargs):
        calls.append(1)
        initialize(self, *args, **kwargs)

    monkeypatch.setattr(QtMetaobjectIndex, "__init__", observe)
    graph = build_from_json(result, root=tmp_path, directed=True)
    retained = [data for _, _, data in graph.edges(data=True) if data.get("context") == "qml_js_call"]
    assert len(retained) == 20
    assert all(qt_metadata(edge)["native_endpoint"]["metaobject_fact_id"] for edge in retained)
    assert len(calls) <= 2, "full source/provenance indexes must not rebuild for each native edge"
