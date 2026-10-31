"""Neutral source-only metaobject fixtures using real accepted CMake membership."""
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_project_index import QtProjectIndex
from graphify.qt_qml_bridge import build_qt_qml_bridge
from tests.qt_analysis_helpers import analysis


def sources(marker="Q_OBJECT", *, name="Service", crlf=False):
    header = ("// Original bytes: café\nclass Backend : public QObject {\n"
              f"{marker}\nQML_NAMED_ELEMENT({name})\npublic:\n"
              "Q_PROPERTY(int count READ count NOTIFY changed)\nint count() const;\n"
              "Q_INVOKABLE int ownMethod();\nQ_SIGNAL void changed();\nvoid ordinary();\n};\n")
    if crlf:
        header = "\ufeff" + header.replace("\n", "\r\n")
    return {"backend.hpp": header,
            "Main.qml": f"import Public.Probe 1.0\n{name} {{ property int methodResult: ownMethod(); "
                        "property int propertyResult: count; onChanged: methodResult=1 }\n",
            "CMakeLists.txt": "qt_add_qml_module(app URI Public.Probe VERSION 1.0 "
                              "QML_FILES Main.qml SOURCES backend.hpp)\n"}


def analyzed(root, marker="Q_OBJECT", **kwargs):
    return analysis(root, sources(marker, **kwargs))


def member_sites(result):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") in {"read", "call", "handler"}
            and qml_metadata(node).get("raw_name") in {"count", "ownMethod", "onChanged"}]


def member_edges(result):
    return [edge for edge in result.get("edges", result.get("links", [])) if edge.get("context") in {
        "qml_js_call", "qml_binding_read", "qml_signal_subscription"}]


def facts(result, kind):
    return [node for node in result["nodes"] if qt_metadata(node).get("kind") == kind]


def bridge(root, result):
    project = QtProjectIndex(result["nodes"], result["edges"], root=root)
    return build_qt_qml_bridge(result["nodes"], result["edges"], root=root, project_index=project)
