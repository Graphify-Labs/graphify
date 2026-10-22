"""REQ-QML-009: literal mutations retain provenance without weakening coverage guards."""
import json

import pytest

from graphify.extractors.qml_cmake import parse_cmake
from graphify.qml_resolution_types import qml_metadata
from graphify.security import sanitize_metadata


MODULE = "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml)\n"


def facts(result, kind):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("newline,bom", [("\n", ""), ("\r\n", "\ufeff")])
def test_REQ_QML_009_literal_private_sources_keep_module_and_original_byte_provenance(newline, bom):
    """The formerly rejected augmentation now proves ownership and exact UTF-8 ranges."""
    text = bom + (MODULE + 'target_sources(app PRIVATE worker.cpp "Écran.h")\n').replace("\n", newline)
    result = parse_cmake(text, relative_file="ui/CMakeLists.txt")
    assert not result.get("error")
    module = facts(result, "qt_module")[0]
    sources = facts(result, "qt_source")
    assert [(qml_metadata(node)["value"], qml_metadata(node)["source_kind"]) for node in sources] == [
        ("Main.qml", "qml"), ("worker.cpp", "cpp"), ("Écran.h", "cpp")]
    raw = text.encode()
    for node in sources:
        md = qml_metadata(node)
        span = md["span"]
        assert md["module_key"] == qml_metadata(module)["module_key"]
        assert raw[span["start_byte"]:span["end_byte"]].decode().strip('"') == md["value"]
        assert any(edge["source"] == module["id"] and edge["target"] == node["id"]
                   for edge in result["edges"])
    transported = json.loads(json.dumps(result))
    for node in transported["nodes"]:
        node["metadata"] = sanitize_metadata(node["metadata"])
    assert [qml_metadata(node) for node in facts(transported, "qt_source")] == [
        qml_metadata(node) for node in sources]
    assert [node["id"] for node in sources] == [node["id"] for node in facts(
        parse_cmake(bom + "# comment\n" + text.removeprefix(bom),
                    relative_file="ui/CMakeLists.txt"), "qt_source")]


def test_REQ_QML_009_source_properties_and_explicit_resources_preserve_alias_time_and_tooling_role():
    """Properties precede use, aliases are resources, and IDE files stay non-runtime."""
    source = ('set_source_files_properties(Main.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE '
              'QT_RESOURCE_ALIAS Screen.qml)\n' + MODULE +
              'set_source_files_properties(extra/Panel.qml PROPERTIES QT_RESOURCE_ALIAS Panel.qml)\n'
              'qt6_add_resources(app extras PREFIX /qml FILES extra/Panel.qml icons/action.svg)\n'
              'set_source_files_properties(types/plugins.qmltypes ../tools/generate.py '
              'PROPERTIES HEADER_FILE_ONLY TRUE)\n'
              'target_sources(app PRIVATE types/plugins.qmltypes ../tools/generate.py)\n')
    result = parse_cmake(source, relative_file="ui/CMakeLists.txt")
    assert not result.get("error")
    main = qml_metadata(facts(result, "qt_source")[0])
    assert (main["resource_alias"], main["singleton_type"]) == ("Screen.qml", True)
    assert [(qml_metadata(node)["logical_url"], qml_metadata(node)["target_path"])
            for node in facts(result, "resource_alias")] == [
                ("qrc:/qml/Panel.qml", "ui/extra/Panel.qml"),
                ("qrc:/qml/icons/action.svg", "ui/icons/action.svg")]
    assert [qml_metadata(node)["value"] for node in facts(result, "qt_tooling_source")] == [
        "types/plugins.qmltypes", "../tools/generate.py"]
    assert len(facts(result, "qt_source")) == 1


def test_REQ_QML_009_conditional_native_resource_properties_are_provably_irrelevant():
    """Native RC compiler include paths cannot become QML/resource/module facts."""
    result = parse_cmake(MODULE + 'if(WIN32)\ntarget_sources(app PRIVATE app.rc)\n'
                         'set_source_files_properties(app.rc PROPERTIES '
                         'INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}")\nendif()')
    assert not result.get("error")
    assert [qml_metadata(node)["value"] for node in facts(result, "qt_source")] == ["Main.qml"]
    assert facts(result, "resource_alias") == []


@pytest.mark.parametrize("value,header_only", [("TRUE", True), ("ON", True), ("1", True),
                                             ("FALSE", False), ("OFF", False), ("0", False)])
def test_REQ_QML_009_explicit_header_only_property_preserves_native_header_membership(value, header_only):
    """HEADER_FILE_ONLY does not exclude headers from CMake AUTOMOC processing."""
    source = (f"set_source_files_properties(backend.h worker.h PROPERTIES HEADER_FILE_ONLY {value})\n"
              "qt_add_qml_module(app URI Public.Tools SOURCES backend.h)\n"
              "target_sources(app PRIVATE worker.h)")
    result = parse_cmake(source)
    assert not result.get("error")
    assert facts(result, "qt_tooling_source") == []
    assert len(facts(result, "qt_source")) == 2
    assert all(qml_metadata(node)["source_kind"] == "cpp"
               and qml_metadata(node)["header_file_only"] == header_only
               for node in facts(result, "qt_source"))


@pytest.mark.parametrize("mutation", [
    "target_sources(app PUBLIC worker.cpp)",
    "target_sources(app PRIVATE ${sources})",
    "target_sources(app PRIVATE $<TARGET_OBJECTS:worker>)",
    "target_sources(other PRIVATE worker.cpp)",
    "target_sources(app PRIVATE generated.qml)",
    "if(WIN32)\ntarget_sources(app PRIVATE worker.cpp)\nendif()",
    "if(WIN32)\nset_source_files_properties(Main.qml PROPERTIES QT_RESOURCE_ALIAS X.qml)\nendif()",
    "set_source_files_properties(Main.qml PROPERTIES QT_RESOURCE_ALIAS New.qml)",
    "set_source_files_properties(worker.cpp PROPERTIES INCLUDE_DIRECTORIES /anywhere)",
    "if(WIN32)\nset_source_files_properties(app.rc PROPERTIES QT_RESOURCE_ALIAS X.qml)\nendif()",
    "set_source_files_properties(worker.cpp PROPERTIES HEADER_FILE_ONLY ${mode})",
    "set_source_files_properties(worker.cpp PROPERTIES HEADER_FILE_ONLY MAYBE)",
    "set_source_files_properties(worker.cpp PROPERTIES GENERATED TRUE)",
    "set_source_files_properties(worker.cpp HEADER_FILE_ONLY TRUE)",
    "set_source_files_properties(worker.cpp PROPERTIES)",
    "set_source_files_properties(worker.cpp PROPERTIES HEADER_FILE_ONLY)",
    "set_source_files_properties(${source} PROPERTIES HEADER_FILE_ONLY TRUE)",
    "set_source_files_properties(worker.cpp PROPERTIES HEADER_FILE_ONLY TRUE HEADER_FILE_ONLY FALSE)",
    "set_property(SOURCE Main.qml PROPERTY QT_RESOURCE_ALIAS X.qml)",
    "qt_target_qml_sources(app QML_FILES Extra.qml)",
    "qt_add_resources(app extras FILES Main.qml)",
    "qt_add_resources(output resources.qrc)",
    "qt_add_resources(app extras PREFIX / FILES ${files})",
    "qt_add_resources(app extras PREFIX / FILES ../Outside.qml)",
    "qt_add_resources(app extras PREFIX / FILES Main.qml OPTIONS -compress 9)",
    "qt_add_resources(app extras PREFIX / FILES Main.qml OUTPUT_TARGETS output)",
    "if(WIN32)\nqt_add_resources(app extras PREFIX / FILES Main.qml)\nendif()",
])
def test_REQ_QML_009_unsupported_mutations_preserve_closed_coverage_guard(mutation):
    """Dynamic, conditional, generated, escaping or ambiguous forms never pass silently."""
    result = parse_cmake(MODULE + mutation)
    assert result["partial"] and result["qml_failures"]
    assert all(entry["severity"] == "error" and entry["source_file"] == "CMakeLists.txt"
               for entry in result["diagnostics"])


@pytest.mark.parametrize("source", [
    "target_sources(app PRIVATE worker.cpp)\n" + MODULE,
    MODULE + MODULE + "target_sources(app PRIVATE worker.cpp)",
    MODULE + "target_sources(app PRIVATE worker.cpp)\n"
             "set_source_files_properties(worker.cpp PROPERTIES HEADER_FILE_ONLY TRUE)",
    "qt_add_resources(app extras PREFIX / FILES Main.qml)\n"
    "set_source_files_properties(Main.qml PROPERTIES QT_RESOURCE_ALIAS Other.qml)",
    "set_source_files_properties(Main.qml PROPERTIES QT_RESOURCE_ALIAS ../Escaped.qml)\n" + MODULE,
])
def test_REQ_QML_009_ordering_duplicate_targets_and_late_properties_are_rejected(source):
    """No deferred target guess or later property rewrite may rewrite existing authority."""
    assert parse_cmake(source)["qml_failures"]
