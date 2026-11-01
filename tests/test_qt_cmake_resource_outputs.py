"""INC-QML-58: source-local QRC output pairs preserve provenance and reject guesses."""
import json

import pytest

from graphify.extractors.qml_cmake import parse_cmake
from graphify.qml_resolution_types import qml_metadata
from graphify.security import sanitize_metadata

MODULE = "qt_add_qml_module(app URI Public.Tools QML_FILES Main.qml)\n"
PAIR = "qt_add_resources(bundle resources.qrc)\ntarget_sources(app PRIVATE ${bundle})\n"


def records(result, kind):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("command", ["qt_add_resources", "qt6_add_resources"])
@pytest.mark.parametrize("newline,bom", [("\n", ""), ("\r\n", "\ufeff")])
def test_req_qml009_ac01_resource_output_pair_preserves_qrc_and_use_spans(command, newline, bom):
    """Adjacent multi-QRC input/use facts keep original bytes, IDs and module identity."""
    text = bom + ("# α\n" + MODULE + f'{command}(bundle resources.qrc "Écran.qrc")\n'
                  "target_sources(app PRIVATE ${bundle})\n").replace("\n", newline)
    result = parse_cmake(text, relative_file="ui/CMakeLists.txt")
    assert not result.get("error"), result.get("diagnostics")
    module = records(result, "qt_module")[0]
    sources = [node for node in records(result, "qt_source")
               if qml_metadata(node)["source_kind"] == "qrc"]
    assert [qml_metadata(node)["value"] for node in sources] == ["resources.qrc", "Écran.qrc"]
    use, = records(result, "qt_generated_resource_use")
    assert qml_metadata(use)["output_variable"] == "bundle"
    assert qml_metadata(use)["generated"] is True
    assert all(qml_metadata(node)["generated"] is False for node in sources)
    raw = text.encode("utf-8")
    for node in [*sources, use]:
        md, span = qml_metadata(node), qml_metadata(node)["span"]
        assert md["module_key"] == qml_metadata(module)["module_key"]
        assert md["output_variable"] == "bundle"
        token = raw[span["start_byte"]:span["end_byte"]].decode("utf-8")
        assert token.strip('"') == ("${bundle}" if node is use else md["value"])
        for end in ("start", "end"):
            prefix = raw[:span[f"{end}_byte"]]
            assert span[f"{end}_row"] == prefix.count(b"\n")
            assert span[f"{end}_column"] == len(prefix) - prefix.rfind(b"\n") - 1
        assert any(edge["source"] == module["id"] and edge["target"] == node["id"]
                   and edge["relation"] == "contains" for edge in result["edges"])
    assert {edge["target"] for edge in result["edges"]
            if edge["source"] == use["id"] and edge["relation"] == "references"
            and edge["context"] == "qt_generated_resource_input"} == {node["id"] for node in sources}
    assert records(result, "resource_alias") == []
    assert all("qrc_" not in node["label"] and ".cpp" not in node["label"] for node in result["nodes"])
    transported = json.loads(json.dumps(result))
    for item in transported["nodes"] + transported["edges"]:
        item["metadata"] = sanitize_metadata(item["metadata"])
    assert [qml_metadata(node) for node in transported["nodes"]] == [
        qml_metadata(node) for node in result["nodes"]]
    shifted = parse_cmake(bom + "# shifted\n" + text.removeprefix(bom), relative_file="ui/CMakeLists.txt")
    assert [node["id"] for node in shifted["nodes"]] == [node["id"] for node in result["nodes"]]


@pytest.mark.parametrize("executable", ["qt_add_executable", "qt6_add_executable"])
def test_req_qml009_ac03_known_declaration_prefix_and_trailing_opaque_command(executable):
    """Known declarations and prior target resources do not claim variable evaluation."""
    prefix = (f"{executable}(app main.cpp)\nset_target_properties(app PROPERTIES AUTOMOC ON)\n"
              "set_source_files_properties(app.rc PROPERTIES OBJECT_DEPENDS generated.rc)\n")
    source = prefix + MODULE + "qt_add_resources(app extras PREFIX / FILES icon.svg)\n" + PAIR
    result = parse_cmake(source + "unrelated_command(other)\n")
    assert not result.get("error")
    assert len(records(result, "qt_generated_resource_use")) == 1
    assert len(records(result, "resource_alias")) == 1


@pytest.mark.parametrize("prefix", [
    "set(bundle old.cpp)", "unset(bundle)", "list(APPEND bundle old.cpp)",
    "include(other.cmake)", "add_subdirectory(other)", "unknown_command(other)",
    "find_package(Other)", "function(make)\nendfunction()", "macro(make)\nendmacro()",
    "if(OFF)\nendif()", "foreach(item x)\nendforeach()", "while(OFF)\nendwhile()",
    "block()\nendblock()", "set_target_properties(app PROPERTIES OUTPUT_NAME bundle)",
    "qt_add_executable(bundle main.cpp)",
    "qt_add_executable(app ${bundle})", "qt_add_executable(app path/bundle.cpp)",
])
def test_req_qml009_ac04_prefix_barriers_and_any_prior_identifier_prevent_binding(prefix):
    """Unknown execution/writers and earlier literal/reference names cannot lend output authority."""
    result = parse_cmake(prefix + "\n" + MODULE + PAIR)
    assert result.get("partial") and result.get("qml_failures")
    assert records(result, "qt_generated_resource_use") == []
    assert not [node for node in records(result, "qt_source")
                if qml_metadata(node)["source_kind"] == "qrc"]


@pytest.mark.parametrize("source", [
    MODULE + "qt_add_resources(bundle resources.qrc)",
    PAIR + MODULE,
    MODULE + MODULE + PAIR,
    MODULE.replace("URI Public.Tools", "URI ${module}") + PAIR,
    MODULE + PAIR.replace("app PRIVATE", "other PRIVATE"),
    MODULE + PAIR.replace("PRIVATE", "PUBLIC"),
    MODULE + PAIR.replace("${bundle}", "${bundle} worker.cpp"),
    MODULE + PAIR.replace("${bundle}", '"${bundle}"'),
    MODULE + PAIR.replace("${bundle}", "${bundle}_suffix"),
    MODULE + PAIR.replace("${bundle}", "$<TARGET_OBJECTS:bundle>"),
    MODULE + PAIR.replace("\ntarget_sources", "\nproject(Other)\ntarget_sources"),
    MODULE + PAIR + "target_sources(app PRIVATE ${bundle})",
    MODULE + PAIR + "set(bundle other.cpp)",
    MODULE + PAIR + PAIR,
    MODULE + "if(ON)\n" + PAIR + "endif()",
    MODULE + PAIR.replace("resources.qrc", "${files}"),
    MODULE + PAIR.replace("resources.qrc", "../escape.qrc"),
    MODULE + PAIR.replace("resources.qrc", "/outside.qrc"),
    MODULE + PAIR.replace("resources.qrc", "C:/outside.qrc"),
    MODULE + PAIR.replace("resources.qrc", "resources.qml"),
    MODULE + PAIR.replace("resources.qrc", "resources.qrc OPTIONS -compress 9"),
    MODULE + PAIR.replace("resources.qrc", "resources.qrc BIG_RESOURCES"),
    MODULE + PAIR.replace("resources.qrc", "resources.qrc OUTPUT_TARGETS extras"),
    MODULE + PAIR.replace("resources.qrc", "resources.qrc resources.qrc"),
    "set_source_files_properties(resources.qrc PROPERTIES QT_RESOURCE_ALIAS other.qrc)\n" + MODULE + PAIR,
    MODULE + PAIR + "set_source_files_properties(resources.qrc PROPERTIES HEADER_FILE_ONLY TRUE)",
])
def test_req_qml009_ac04_unsupported_pair_shapes_never_emit_generated_use(source):
    """Orphans, scopes, ambiguous/mutated identities, options and unsafe QRC inputs stay incomplete."""
    result = parse_cmake(source)
    assert result.get("partial") and result.get("qml_failures")
    assert records(result, "qt_generated_resource_use") == []


def test_req_qml012_ac04_command_inventory_boundary_is_typed_and_bounded():
    """Exactly 10,000 commands may parse; a 10,001st rejects before pair analysis."""
    accepted = "project(Public)\n" * 9_997 + MODULE + PAIR
    assert not parse_cmake(accepted).get("error")
    rejected = parse_cmake("project(Public)\n" + accepted)
    assert rejected["nodes"] == [] and rejected["edges"] == []
    assert rejected["diagnostics"][0]["code"] == "QML_PROJECT_LIMIT"
    assert rejected["diagnostics"][0]["reason"] == "cmake_command_limit"
