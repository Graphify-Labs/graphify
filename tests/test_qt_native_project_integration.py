"""Production build metadata supplies exact native QML exposure context."""
from __future__ import annotations

import pytest

from graphify.build import build_from_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis


HEADER = '''#include <QObject>
class Backend : public QObject { Q_OBJECT QML_NAMED_ELEMENT(Service)
 Q_PROPERTY(int value READ value)
public: int value() const { return 1; }
 Q_INVOKABLE int fetch() { return 2; }
};'''
QML = '''import Public.Tools 1.0 as Tools
Tools.Service { property int displayed: value; property int called: fetch() }
'''


def native_edges(result):
    return [edge for edge in result["edges"] if qt_metadata(edge).get("native_endpoint")]


@pytest.mark.parametrize("build_name,build", [
    ("CMakeLists.txt", "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.h)"),
    ("app.pro", "CONFIG += qmltypes\nQML_IMPORT_NAME = Public.Tools\nQML_IMPORT_MAJOR_VERSION = 1\nHEADERS += backend.h\nDISTFILES += Main.qml"),
])
def test_actual_macro_provider_uses_cmake_or_qmake_module_and_exact_cpp_endpoints(tmp_path, build_name, build):
    result = analysis(tmp_path, {build_name: build, "backend.h": HEADER, "Main.qml": QML})
    graph = build_from_json(result, root=tmp_path, directed=True)
    edges = native_edges(result)
    calls = [edge for edge in edges if edge["relation"] == "calls"]
    assert len(calls) == 1
    proof = qt_metadata(calls[0])["native_endpoint"]
    assert proof["canonical_target_id"] == calls[0]["target"]
    assert graph.nodes[proof["canonical_target_id"]]["label"].endswith(".fetch()")
    assert graph.nodes[proof["canonical_target_id"]]["source_file"] == "backend.h"
    assert graph.nodes[proof["class_id"]]["source_file"] == "backend.h"
    module_ids = [item for item in proof["evidence"] if qml_metadata(graph.nodes[item]).get("kind") == "qt_module"]
    assert len(module_ids) == 1
    module = qml_metadata(graph.nodes[module_ids[0]])
    assert (module["uri"], module["major"], module["minor"]) == ("Public.Tools", 1, 0)
    assert graph.nodes[module_ids[0]]["source_file"] == build_name
    assert any(edge["context"] == "qml_binding_read" for edge in edges)
    assert all(graph.has_edge(edge["source"], edge["target"]) for edge in edges)


def test_same_directory_without_literal_build_source_membership_does_not_expose_class(tmp_path):
    result = analysis(tmp_path, {"CMakeLists.txt": "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml)",
        "backend.h": HEADER, "Main.qml": QML})
    assert not native_edges(result)
    uses = [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == "type_use"]
    assert uses and all(md["status"] != "resolved" for md in uses)
    assert any(qt_metadata(node).get("kind") == "registration" for node in result["nodes"])


def test_cpp_source_in_two_distinct_build_contexts_has_no_arbitrary_native_provider(tmp_path):
    module = "qt_add_qml_module({target} URI Public.Tools VERSION 1.0 SOURCES backend.h)"
    result = analysis(tmp_path, {"CMakeLists.txt": module.format(target="one"),
        "duplicate.cmake": module.format(target="two"), "backend.h": HEADER, "Main.qml": QML})
    assert not native_edges(result)
    imports = [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == "import_resolution"]
    assert imports and all(md["status"] == "ambiguous" for md in imports)
