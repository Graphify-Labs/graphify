"""Production source-state transitions cannot borrow or retain false Qt identity."""
import json

from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_signals_slots import SOURCE


def test_warm_source_results_match_and_reassigned_handle_loses_target(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use() {{ QQuickView view; view.setSource(QUrl("{url}"));
 auto root = view.rootObject(); root->property("value"); }}'''
    sources = {"access.cpp": source, "Main.qml": 'import QtQml\nQtObject { property int value: 1 }'}
    cold = analysis(tmp_path, sources)
    warm = extract([tmp_path / name for name in sources], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert [(node["id"], qt_metadata(node)) for node in cold["nodes"] if qt_metadata(node)] == [(node["id"], qt_metadata(node)) for node in warm["nodes"] if qt_metadata(node)]
    changed = analysis(tmp_path, {**sources, "access.cpp": source.replace('root->property', 'root = factory(); root->property')})
    access = sites(changed, "qml_access")[0]
    assert qt_metadata(access)["status"] == "dynamic"
    assert qt_metadata(access)["reason"] == "conditional_or_reassigned_handle"
    assert not [edge for edge in changed["edges"] if edge["source"] == access["id"] and edge["relation"] in {"uses", "calls"}]


def test_source_scopes_do_not_cross_between_functions_with_same_local_name(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void first() {{ QQuickView view; view.setSource(QUrl("{url}")); auto root = view.rootObject(); }}
void second(QObject *root) {{ root->property("value"); }}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": 'import QtQml\nQtObject { property int value: 1 }'})
    assert qt_metadata(sites(result, "qml_access")[0])["status"] == "unavailable"


def test_fresh_connection_borrows_prior_header_facts_without_mutation(tmp_path):
    header, wire = SOURCE.split('void wire', 1)
    initial = analysis(tmp_path, {"events.h": header, "wire.cpp": 'void wire' + wire})
    borrowed_nodes = [node for node in initial["nodes"] if node["source_file"] == "events.h"]
    borrowed_ids = {node["id"] for node in borrowed_nodes}
    borrowed_edges = [edge for edge in initial["edges"] if edge["source"] in borrowed_ids and edge["target"] in borrowed_ids]
    before = json.dumps([borrowed_nodes, borrowed_edges], sort_keys=True)
    fresh = extract([tmp_path / "wire.cpp"], root=tmp_path, cache_root=tmp_path, parallel=False,
                    resolution_context_nodes=borrowed_nodes, resolution_context_edges=borrowed_edges)
    assert not fresh.get("qml_failures")
    assert all(qt_metadata(node)["status"] == "resolved" for node in sites(fresh, "connect"))
    assert json.dumps([borrowed_nodes, borrowed_edges], sort_keys=True) == before
