"""REQ-QML-009/011: CMake additions participate in real extraction and safe updates."""
import json

import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.watch import _rebuild_code


def fixture(root):
    """Only source facts admitted by the normal collector may establish a join."""
    sources = {
        "Main.qml": "import Public.Tools 1.0\nService { property int shown: status }\n",
        "Other.qml": "Item { property int other: 2 }\n",
        "backend.h": "#include <QObject>\nclass Backend : public QObject { Q_OBJECT "
                     "QML_NAMED_ELEMENT(Service) Q_PROPERTY(int status READ status) "
                     "public: int status() const { return 1; } };\n",
        "loader.cpp": '#include <QQmlApplicationEngine>\nvoid load() { '
                      'QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Panel.qml")); }\n',
        "CMakeLists.txt": 'set_source_files_properties(Main.qml PROPERTIES QT_RESOURCE_ALIAS Panel.qml)\n'
                          'qt_add_qml_module(app URI Public.Tools VERSION 1.0 '
                          'QML_FILES Main.qml Other.qml)\n'
                          'target_sources(app PRIVATE backend.h loader.cpp)\n'
                          'qt_add_resources(app extras PREFIX /ui FILES Main.qml)\n',
    }
    for name, text in sources.items():
        (root / name).write_bytes(text.encode())
    return root / "CMakeLists.txt"


def published(root):
    return load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))


def normalized(graph):
    """Compare every Qt/QML semantic fact and source-owned edge, not only counts."""
    nodes = {identity: (node.get("source_file"), qml_metadata(node), qt_metadata(node))
             for identity, node in graph.nodes(data=True) if qml_metadata(node) or qt_metadata(node)}
    edges = {(edge.get("_src", source), edge.get("_tgt", target), edge.get("relation"),
              edge.get("context"), edge.get("confidence"),
              json.dumps(qml_metadata(edge), sort_keys=True), json.dumps(qt_metadata(edge), sort_keys=True))
             for source, target, edge in graph.edges(data=True) if qml_metadata(edge) or qt_metadata(edge)}
    return nodes, edges


def compare_clean(root):
    paths = extraction.collect_files(root, root=root)
    clean = extraction.extract(paths, root=root, cache_root=root / "clean-cache", parallel=False)
    assert not clean.get("qml_failures")
    assert normalized(published(root)) == normalized(build_from_json(clean, root=root))


def test_REQ_QML_009_private_source_and_resource_additions_reach_real_producer_and_warm_cache(tmp_path):
    """Added native headers expose the real type and runtime aliases resolve to QML."""
    build = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    reads = [edge for _, _, edge in graph.edges(data=True) if edge.get("context") == "qml_binding_read"
             and qt_metadata(edge).get("native_endpoint")]
    assert len(reads) == 1
    targets = [graph.nodes[edge.get("_tgt", target)] for _, target, edge in graph.edges(data=True)
               if edge.get("context") == "qt_resource_membership"]
    assert len(targets) == 1 and targets[0]["source_file"] == "Main.qml"
    before = normalized(graph)
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    assert normalized(published(tmp_path)) == before
    compare_clean(tmp_path)


def test_REQ_QML_011_metadata_only_retarget_and_source_removal_replace_stale_joins(tmp_path):
    """CMake-only changes invalidate unchanged native/QML consumers and equal a full rebuild."""
    build = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    text = build.read_text(encoding="utf-8")
    text = text.replace("properties(Main.qml", "properties(Other.qml").replace("FILES Main.qml)", "FILES Other.qml)")
    text = text.replace("PRIVATE backend.h loader.cpp", "PRIVATE loader.cpp")
    build.write_text(text, encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False)
    graph = published(tmp_path)
    assert not any(edge.get("context") == "qml_binding_read" and qt_metadata(edge).get("native_endpoint")
                   for _, _, edge in graph.edges(data=True))
    targets = [graph.nodes[edge.get("_tgt", target)] for _, target, edge in graph.edges(data=True)
               if edge.get("context") == "qt_resource_membership"]
    assert len(targets) == 1 and targets[0]["source_file"] == "Other.qml"
    compare_clean(tmp_path)


def test_REQ_QML_011_rejected_addition_preserves_prior_published_graph_manifest_and_report(tmp_path):
    """The expanded accepted subset does not bypass a later dynamic-mutation guard."""
    build = fixture(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    out = tmp_path / "graphify-out"
    # The no-cluster path retains an existing report rather than generating one;
    # seed that separately owned artifact to check the same preservation gate.
    (out / "report.md").write_text("Previously accepted public report\n", encoding="utf-8")
    prior = {name: (out / name).read_bytes() for name in ("graph.json", "manifest.json", "report.md")}
    with build.open("a", encoding="utf-8") as stream:
        stream.write("target_sources(app PRIVATE ${unknown_sources})\n")
    assert not _rebuild_code(tmp_path, changed_paths=[build], no_cluster=True, acquire_lock=False, force=True)
    assert {name: (out / name).read_bytes() for name in prior} == prior
