"""INC-QML-53: source-property aliases replace the module's physical URL."""
from __future__ import annotations

import copy

import pytest

from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.qt_project_index import QtProjectIndex
from tests.qt_analysis_helpers import analysis


@pytest.mark.parametrize("alias", [None, "Entry.qml", "views/Écran.qml"])
@pytest.mark.parametrize("no_target_path", [False, True])
def test_req_qml009_ac03_cmake_source_alias_replaces_only_its_resource_url(
    tmp_path, alias, no_target_path
):
    # Use the real producer so the source property, module ownership and accepted
    # QML component must agree before the index can expose a resource endpoint.
    option = "NO_RESOURCE_TARGET_PATH" if no_target_path else ""
    prop = (f'set_source_files_properties(pages/Main.qml PROPERTIES QT_RESOURCE_ALIAS "{alias}")\n'
            if alias else "")
    result = analysis(tmp_path, {
        "CMakeLists.txt": prop + "qt_add_qml_module(demo URI Public.Tools VERSION 1.2 "
                         f"RESOURCE_PREFIX /ui {option} QML_FILES pages/Main.qml)\n",
        "pages/Main.qml": "import QtQuick\nItem { property int count: 2 }\n",
    })
    before = copy.deepcopy((result["nodes"], result["edges"]))
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    component = next(node for node in result["nodes"]
                     if qml_metadata(node).get("kind") == "component")
    prefix = "qrc:/ui/" + ("" if no_target_path else "Public/Tools/")
    actual = alias or "pages/Main.qml"
    assert index.resolve_url(prefix + actual).target_id == component["id"]
    assert index.resolve_url(actual, prefix + "Other.qml").target_id == component["id"]
    if alias:
        assert index.resolve_url(prefix + "pages/Main.qml").target_id is None
    assert (result["nodes"], result["edges"]) == before


def test_req_qml009_ac03_invalid_source_alias_cannot_restore_physical_fallback(tmp_path):
    # Defensive index validation also protects transported fact dictionaries:
    # malformed overrides do not silently fall back to an invented physical URL.
    result = analysis(tmp_path, {
        "CMakeLists.txt": "qt_add_qml_module(demo URI Public.Tools "
                         "RESOURCE_PREFIX /ui QML_FILES Main.qml)\n",
        "Main.qml": "Item {}\n",
    })
    source = next(node for node in result["nodes"]
                  if qml_metadata(node).get("kind") == "qt_source")
    metadata = qml_metadata(source)
    for invalid in (None, 7, "../Main.qml", "/Main.qml", "Main.qml?variant=1"):
        metadata["resource_alias"] = invalid
        source["metadata"]["qml"] = encode_metadata(metadata)
        index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
        assert index.resolve_url("qrc:/ui/Public/Tools/Main.qml").target_id is None
