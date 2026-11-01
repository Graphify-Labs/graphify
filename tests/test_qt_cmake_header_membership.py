"""INC-QML-53: HEADER_FILE_ONLY compilation flags do not suppress native Qt headers."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_project_index import QtProjectIndex
from tests.qt_analysis_helpers import analysis


@pytest.mark.parametrize("value", ["TRUE", "ON", "1", "FALSE", "OFF", "0"])
@pytest.mark.parametrize("addition", [False, True], ids=["module_sources", "target_sources"])
def test_req_qml020_ac01_header_only_native_member_keeps_module_and_qml_binding(tmp_path, value, addition):
    """CMake AUTOMOC scans target headers; HEADER_FILE_ONLY controls object compilation.

    Explicit true and false values must retain the same native provider and QML
    property read. The source property is preserved separately from membership.
    """
    module = "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml"
    cmake = f"set_source_files_properties(backend.h PROPERTIES HEADER_FILE_ONLY {value})\n"
    cmake += module + (" SOURCES backend.h)\n" if not addition else ")\ntarget_sources(app PRIVATE backend.h)\n")
    result = analysis(tmp_path, {
        "CMakeLists.txt": cmake,
        "Main.qml": "import Public.Tools 1.0\nService { property int shown: status }\n",
        "backend.h": "#include <QObject>\nclass Backend : public QObject { Q_OBJECT "
                     "QML_NAMED_ELEMENT(Service) Q_PROPERTY(int status READ status) "
                     "public: int status() const { return 1; } };\n",
    })
    declarations = [qml_metadata(node) for node in result["nodes"]
                    if qml_metadata(node).get("kind") == "qt_source"
                    and qml_metadata(node).get("value") == "backend.h"]
    assert len(declarations) == 1 and declarations[0]["source_kind"] == "cpp"
    assert declarations[0]["header_file_only"] == (value in {"TRUE", "ON", "1"})
    properties = [qml_metadata(node) for node in result["nodes"]
                  if qml_metadata(node).get("kind") == "qt_source_property"]
    assert len(properties) == 1 and properties[0]["properties"]["HEADER_FILE_ONLY"] == value
    assert QtProjectIndex(result["nodes"], result["edges"], root=tmp_path).module_context("backend.h").status == "resolved"
    reads = [edge for edge in result["edges"] if edge.get("context") == "qml_binding_read"
             and qt_metadata(edge).get("native_endpoint")]
    assert len(reads) == 1


@pytest.mark.parametrize("addition", [False, True], ids=["module_sources", "target_sources"])
def test_req_qml009_ac01_non_native_header_only_tooling_cannot_provide_module_membership(tmp_path, addition):
    """An explicit IDE-only script stays separate while its native sibling remains admitted."""
    module = "qt_add_qml_module(app URI Public.Tools SOURCES "
    declaration = (module + "tools/generate.py backend.h)\n" if not addition else
                   module + "backend.h)\ntarget_sources(app PRIVATE tools/generate.py)\n")
    result = analysis(tmp_path, {
        "CMakeLists.txt": "set_source_files_properties(tools/generate.py PROPERTIES HEADER_FILE_ONLY TRUE)\n" + declaration,
        "tools/generate.py": "def generate():\n    return 1\n",
        "backend.h": "struct Backend {};\n",
    })
    tooling = [qml_metadata(node) for node in result["nodes"]
               if qml_metadata(node).get("kind") == "qt_tooling_source"]
    assert len(tooling) == 1 and tooling[0]["source_kind"] == "tooling"
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.module_context("tools/generate.py").target_id is None
    assert index.module_context("backend.h").status == "resolved"
