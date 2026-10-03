"""QML-008/009/017 public build providers join through the actual facade."""
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_project_index import QtProjectIndex
from tests.qt_analysis_helpers import analysis, sites

HEADER = '''class Backend : public QObject {
 Q_OBJECT
 QML_ELEMENT
 Q_PROPERTY(int count READ count)
public:
 int count() { return 1; }
 Q_INVOKABLE int next(int value) { return value; }
};
'''
QML = '''import Public.Tools 1.0
Backend { property int copied: count; function run() { next(1) } }
'''
QRC = '<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file></qresource></RCC>'
BUILDS = {
    "CMakeLists.txt": 'qt_add_qml_module(tools URI Public.Tools VERSION 1.2 RESOURCE_PREFIX /ui '
                      'QML_FILES Main.qml SOURCES backend.h loader.cpp)\n',
    "tools.pro": 'TARGET = tools\nQML_IMPORT_NAME = Public.Tools\nQML_IMPORT_VERSION = 1.2\n'
                 'HEADERS += backend.h\nSOURCES += loader.cpp\nQML_FILES += Main.qml\nRESOURCES += resources.qrc\n',
}


def facts(result, kind, reference=None):
    return [node for node in result["nodes"] if (md := qml_metadata(node)).get("kind") == kind
            and (reference is None or md.get("reference") == reference)]


@pytest.mark.parametrize("build_file", list(BUILDS))
def test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints(tmp_path, build_file):
    """CMake and qmake provide the same URI/version and canonical C++ members."""
    result = analysis(tmp_path, {"backend.h": HEADER, "Main.qml": QML,
        build_file: BUILDS[build_file], "resources.qrc": QRC})
    project = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    module = project.module_context("backend.h")
    assert module.status == "resolved"
    assert project.module_metadata(module.target_id)["uri"] == "Public.Tools"
    for kind, name in (("read", "count"), ("call", "next")):
        site = facts(result, kind, name)[0]
        md = qml_metadata(site)
        assert md["status"] == "resolved", md
        target = next(node for node in result["nodes"] if node["id"] == md["resolved_target_id"])
        assert target["source_file"] == "backend.h"
        outgoing = [edge for edge in result["edges"] if edge["source"] == site["id"] and edge["target"] == target["id"]]
        assert len(outgoing) == 1 and qt_metadata(outgoing[0])["native_endpoint"]
        if kind == "call":
            assert target.get("_callable") and not qt_metadata(target)


@pytest.mark.parametrize("build_file", list(BUILDS))
def test_qml009_ac03_public_metadata_qrc_load_build_export_reload(tmp_path, build_file):
    """Literal resources and module loads preserve endpoints through persisted graphs."""
    source = '''void use() { QQmlApplicationEngine engine;
 engine.load(QUrl("qrc:/ui/Main.qml")); }
'''
    result = analysis(tmp_path, {"backend.h": HEADER, "Main.qml": QML, "loader.cpp": source,
        build_file: BUILDS[build_file], "resources.qrc": QRC})
    loader = sites(result, "qml_load")[0]
    assert qt_metadata(loader)["status"] == "resolved"
    component = facts(result, "component")[0]
    assert qt_metadata(loader)["target_id"] == component["id"]
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "roundtrip.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert restored.has_edge(loader["id"], component["id"])
    edge = restored.edges[loader["id"], component["id"]]
    assert edge["context"] == "qt_cpp_qml_load" and edge["confidence"] == "INFERRED"
    assert edge["source_file"] == "loader.cpp" and qt_metadata(edge)["target_id"] == component["id"]


def test_qml008_ac03_macro_without_membership_or_wrong_module_does_not_guess(tmp_path):
    """A class name or neighboring module is insufficient provider provenance."""
    no_build = analysis(tmp_path, {"backend.h": HEADER, "Main.qml": QML})
    assert qml_metadata(facts(no_build, "read", "count")[0])["status"] != "resolved"
    wrong = analysis(tmp_path, {"backend.h": HEADER, "Main.qml": QML,
        "CMakeLists.txt": 'qt_add_qml_module(tools URI Other.Tools VERSION 1.2 SOURCES backend.h)\n'})
    assert qml_metadata(facts(wrong, "read", "count")[0])["status"] != "resolved"


def test_qml009_ac03_build_sources_do_not_expand_accepted_cpp_corpus(tmp_path):
    """A disk-only header listed by CMake cannot create a native endpoint."""
    (tmp_path / "backend.h").write_text(HEADER, encoding="utf-8")
    result = analysis(tmp_path, {"Main.qml": QML, "CMakeLists.txt": BUILDS["CMakeLists.txt"]})
    assert not sites(result, "class")
    assert qml_metadata(facts(result, "read", "count")[0])["status"] != "resolved"


@pytest.mark.parametrize("build_file", list(BUILDS))
def test_qml017_ac01_literal_module_load_reaches_declared_component_and_property(tmp_path, build_file):
    """Both build profiles supply the exact module/type loader provenance."""
    source = '''void use(){ QQmlApplicationEngine engine;
 engine.loadFromModule("Public.Tools", "Main"); auto root = engine.rootObjects().first();
 root->setProperty("count", 2); }'''
    result = analysis(tmp_path, {"Main.qml": 'import QtQml\nQtObject { property int count: 1 }',
        "loader.cpp": source, build_file: BUILDS[build_file], "resources.qrc": QRC})
    for kind in ("qml_load", "qml_root", "qml_access"):
        assert qt_metadata(sites(result, kind)[0])["status"] == "resolved"
    loader = qt_metadata(sites(result, "qml_load")[0])
    assert loader["target_id"] == facts(result, "component")[0]["id"]


def test_qml009_ac03_generated_resource_path_requires_explicit_prefix(tmp_path):
    """A literal CMake prefix creates aliases; unevaluated policy defaults do not."""
    source = 'void use(){ QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Public/Tools/Main.qml")); }'
    files = {"Main.qml": 'import QtQml\nQtObject {}', "loader.cpp": source,
             "CMakeLists.txt": BUILDS["CMakeLists.txt"]}
    result = analysis(tmp_path, files)
    assert qt_metadata(sites(result, "qml_load")[0])["status"] == "resolved"
    files["CMakeLists.txt"] = files["CMakeLists.txt"].replace("RESOURCE_PREFIX /ui ", "")
    result2 = analysis(tmp_path, files)
    md = qt_metadata(sites(result2, "qml_load")[0])
    assert (md["status"], md["reason"]) == ("unavailable", "resource_alias_unavailable")


def test_qml017_ac01_resource_duplicate_and_unaccepted_targets_remain_unresolved(tmp_path):
    """A duplicate alias and a disk-only target cannot authorize a C++ load edge."""
    source = 'void use(){ QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Main.qml")); }'
    duplicate = QRC.replace('</qresource>', '<file alias="Main.qml">Main.qml</file></qresource>')
    result = analysis(tmp_path, {"loader.cpp": source, "Main.qml": 'import QtQml\nQtObject {}', "resources.qrc": duplicate})
    md = qt_metadata(sites(result, "qml_load")[0])
    assert (md["status"], md["reason"]) == ("ambiguous", "duplicate_resource_alias")
    hidden = tmp_path / "Hidden.qml"
    hidden.write_text('import QtQml\nQtObject {}', encoding="utf-8")
    result2 = analysis(tmp_path, {"loader.cpp": source,
        "resources.qrc": QRC.replace('>Main.qml<', '>Hidden.qml<')})
    md2 = qt_metadata(sites(result2, "qml_load")[0])
    assert (md2["status"], md2["reason"]) == ("unavailable", "resource_target_outside_corpus")
