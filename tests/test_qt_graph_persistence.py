"""Qt occurrence identities and bridge direction through actual graph/export/reload."""
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_access_providers import BACKEND
from tests.test_qt_signals_slots import SOURCE


@pytest.mark.parametrize("directed", [False, True])
def test_native_repeated_sites_export_with_original_utf8_crlf_spans(tmp_path, directed):
    source = ("// Unicode café\n" + SOURCE).replace("\n", "\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = load_node_link_graph(output)
    for site in [*sites(result, "emission"), *sites(result, "connect"), *sites(result, "disconnect")]:
        assert site["id"] in reloaded
        metadata = qt_metadata(reloaded.nodes[site["id"]])
        span = metadata["span"]
        fragment = source.encode()[span["start_byte"]:span["end_byte"]]
        assert fragment and b"(" in fragment
    endpoints = sites(result, "event_endpoint")
    assert len(endpoints) == 8
    for node in endpoints:
        target = qt_metadata(node)["target_id"]
        assert reloaded.has_edge(node["id"], target)
    assert not any(attrs.get("relation") == "calls" and attrs.get("context", "").startswith("qt_connect") for _, _, attrs in reloaded.edges(data=True))


@pytest.mark.parametrize("directed", [False, True])
def test_cpp_qml_context_calls_and_explicit_access_survive_build_export(tmp_path, directed):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend) {{ QQuickView view;
 view.setInitialProperties({{{{"backend", backend}}}}); view.setSource(QUrl("{url}"));
 auto root = view.rootObject(); QMetaObject::invokeMethod(root, "refresh");
 QObject::connect(root, SIGNAL(closed()), backend, SLOT(close())); }}'''
    qml = 'import QtQml\nQtObject { property var backend; function refresh() { backend.refresh() } signal closed() }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    reloaded = load_node_link_graph(output)
    for node in [*sites(result, "qml_load"), *sites(result, "qml_root"), *sites(result, "qml_access"), *sites(result, "context_access"), *sites(result, "event_endpoint")]:
        metadata = qt_metadata(node)
        assert metadata["status"] == "resolved"
        assert reloaded.has_edge(node["id"], metadata["target_id"]), (metadata["kind"], metadata["target_id"])
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["nodes"]
