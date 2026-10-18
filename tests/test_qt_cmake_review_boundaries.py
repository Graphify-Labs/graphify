"""INC-QML-53 review: unsupported argument scopes/empty resources fail closed."""
from __future__ import annotations

import pytest

from graphify.extractors.qml_cmake import parse_cmake
from graphify.qml_resolution_types import qml_metadata


MODULE = "qt_add_qml_module(app URI Public.Tools RESOURCE_PREFIX /ui QML_FILES Main.qml)\n"


@pytest.mark.parametrize("selector", ["DIRECTORY", "TARGET_DIRECTORY"])
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize("native_rc", [False, True])
def test_req_qml009_ac04_source_property_scope_cannot_mutate_local_metadata(selector, quoted, native_rc):
    """CMake scope selectors are arguments, including quoted keyword values.

    A directory-selected property belongs to another source scope; the native
    RC exemption must not bypass this unsupported-scope rejection either.
    """
    scope = f'"{selector}"' if quoted else selector
    path, prop = ("app.rc", "INCLUDE_DIRECTORIES /native") if native_rc else (
        "Main.qml", "QT_RESOURCE_ALIAS Screen.qml")
    result = parse_cmake(f"set_source_files_properties({path} {scope} other PROPERTIES {prop})\n" + MODULE)
    assert result.get("qml_failures")
    assert any(entry["reason"] == "unsupported_source_property_scope" for entry in result["diagnostics"])
    assert not any(qml_metadata(node).get("kind") == "qt_source_property" for node in result["nodes"])
    source = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "qt_source")
    assert "resource_alias" not in qml_metadata(source)


@pytest.mark.parametrize("position", range(8))
@pytest.mark.parametrize("quoted", [False, True])
def test_req_qml009_ac03_discard_file_contents_never_becomes_source_evidence(position, quoted):
    """The unsupported Qt flag cannot become a filename at any argument boundary."""
    values = ["app", "extras", "PREFIX", "/ui", "FILES", "Main.qml", "Other.qml"]
    values.insert(position, '"DISCARD_FILE_CONTENTS"' if quoted else "DISCARD_FILE_CONTENTS")
    result = parse_cmake("qt_add_resources(" + " ".join(values) + ")")
    assert result.get("qml_failures")
    assert not any(qml_metadata(node).get("kind") == "resource_alias" for node in result["nodes"])


def test_req_qml009_ac03_reserved_looking_literal_paths_require_distinct_path_spelling():
    """Quotes do not escape argument keywords; an explicit relative path does.

    The literal supported subset retains filenames such as ./DIRECTORY and
    ./DISCARD_FILE_CONTENTS without interpreting their basename as a selector.
    """
    result = parse_cmake('set_source_files_properties("./DIRECTORY" PROPERTIES HEADER_FILE_ONLY TRUE)\n'
                         + MODULE + 'target_sources(app PRIVATE "./DIRECTORY")\n'
                         'qt_add_resources(app extras PREFIX /ui FILES "./DISCARD_FILE_CONTENTS")\n')
    # The resource URL rejects dot segments by contract. A literal alias makes
    # the filesystem spelling distinct while keeping the resource URL portable.
    assert result.get("qml_failures")
    fixed = parse_cmake('set_source_files_properties("./DIRECTORY" PROPERTIES HEADER_FILE_ONLY TRUE)\n'
                        'set_source_files_properties("./DISCARD_FILE_CONTENTS" PROPERTIES QT_RESOURCE_ALIAS data.bin)\n'
                        + MODULE + 'target_sources(app PRIVATE "./DIRECTORY")\n'
                        'qt_add_resources(app extras PREFIX /ui FILES "./DISCARD_FILE_CONTENTS")\n')
    assert not fixed.get("error")
    tooling = [qml_metadata(node) for node in fixed["nodes"]
               if qml_metadata(node).get("kind") == "qt_tooling_source"]
    assert [entry["value"] for entry in tooling] == ["./DIRECTORY"]
    aliases = [qml_metadata(node) for node in fixed["nodes"]
               if qml_metadata(node).get("kind") == "resource_alias"]
    assert [(entry["logical_url"], entry["target_path"]) for entry in aliases] == [
        ("qrc:/ui/data.bin", "DISCARD_FILE_CONTENTS")]
