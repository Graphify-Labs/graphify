"""QML-009-AC01/04: literal build provenance and fail-closed scope boundaries."""
import json

import pytest

from graphify.extractors.qml_cmake import extract_cmake, parse_cmake
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_project_read import MAX_PROJECT_BYTES
from graphify.extractors.qml_qmake import extract_qmake, parse_qmake
from graphify.security import sanitize_metadata


def records(result, kind):
    return [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_literal_cmake_records_original_bytes_and_transport(tmp_path, newline, bom):
    """Both Qt command names preserve URI/version, Unicode paths and exact ranges."""
    source = bom + newline.join([
        "# α", "cmake_minimum_required(VERSION 3.21)", "project(PublicTools)",
        "qt6_add_qml_module(tools", " URI Public.Tools VERSION 1.2 RESOURCE_PREFIX /ui",
        ' QML_FILES Main.qml "Écran.qml" SOURCES service.h service.cpp',
        " RESOURCES icon.svg IMPORTS Public.Base/1.0 QtQuick/auto",
        " DEPENDENCIES Public.Core/1 OPTIONAL_IMPORTS Public.Optional",
        " IMPORT_PATH imports NO_PLUGIN)", "",])
    path = tmp_path / "CMakeLists.txt"
    path.write_bytes(source.encode("utf-8"))
    result = extract_cmake(path, root=tmp_path)
    assert not result.get("error")
    module = records(result, "qt_module")[0]
    assert (module["uri"], module["major"], module["minor"], module["resource_prefix"]) == (
        "Public.Tools", 1, 2, "/ui")
    assert [md["value"] for md in records(result, "qt_source")] == [
        "Main.qml", "Écran.qml", "service.h", "service.cpp", "icon.svg"]
    imports = records(result, "qt_module_import")
    assert [(md["uri"], md["visibility"]) for md in imports] == [
        ("Public.Base", "import"), ("QtQuick", "import"),
        ("Public.Core", "dependencies"), ("Public.Optional", "optional_imports")]
    assert imports[1]["auto"] is True
    raw = source.encode("utf-8")
    for node in result["nodes"]:
        md = qml_metadata(node)
        span = md["span"]
        for end in ("start", "end"):
            prefix = raw[:span[f"{end}_byte"]]
            assert span[f"{end}_row"] == prefix.count(b"\n")
            assert span[f"{end}_column"] == len(prefix) - prefix.rfind(b"\n") - 1
        if md["kind"] == "qt_source":
            assert raw[span["start_byte"]:span["end_byte"]].decode().strip('"') == md["value"]
    sanitized = json.loads(json.dumps(result))
    for item in sanitized["nodes"] + sanitized["edges"]:
        item["metadata"] = sanitize_metadata(item["metadata"])
    assert records(sanitized, "qt_source") == records(result, "qt_source")
    assert {edge["source"] for edge in result["edges"]} <= {node["id"] for node in result["nodes"]}


@pytest.mark.parametrize("source,reason", [
    ("if(WIN32)\nqt_add_qml_module(app URI Hidden VERSION 1.0 QML_FILES A.qml)\nendif()", "conditional_or_expanded_qml_module"),
    ("function(build)\nqt_add_qml_module(app URI Hidden VERSION 1.0)\nendfunction()", "conditional_or_expanded_qml_module"),
    ("qt_add_qml_module(app URI Public.Tools VERSION ${VERSION})", "conditional_or_expanded_qml_module"),
    ("qt_add_qml_module(app URI Public.Tools SOURCES $<TARGET_OBJECTS:x>)", "conditional_or_expanded_qml_module"),
    ("qt_add_qml_module(app URI Public.Tools VERSION 1.0 IMPORTS TARGET Other)", "target_import_requires_policy_and_target_resolution"),
    ("qt_add_qml_module(app URI Public.Tools UNKNOWN feature)", "unsupported_qml_module_arguments"),
    ("qt_add_qml_module(app URI Public.Tools VERSION 1.0)\ntarget_sources(app PRIVATE generated.h)", "source_mutation_outside_literal_subset"),
])
def test_cmake_conditional_and_expanded_metadata_is_not_authoritative(source, reason):
    result = parse_cmake(source)
    assert result["partial"] is True
    assert reason in {item["reason"] for item in result["diagnostics"]}
    assert result["qml_failures"]
    if "Hidden" in source:
        assert records(result, "qt_module") == []


def test_comments_strings_and_unknown_builds_do_not_make_modules():
    source = '# qt_add_qml_module(fake URI Fake)\nmessage("qt_add_qml_module(fake URI Fake)")\n'
    source += '#[[ qt_add_qml_module(fake URI Fake) ]]\nproject(Ordinary)\n'
    result = parse_cmake(source)
    assert not result.get("error")
    assert records(result, "qt_module") == []
    assert parse_cmake("if(WIN32)\nproject(Ordinary)")["qml_failures"]


def test_qmake_literal_module_sources_resource_and_tooling_paths(tmp_path):
    source = '\ufeff# α\r\nQT += qml quick\r\nCONFIG += qmltypes\r\nTARGET = tools\r\n'
    source += 'QML_IMPORT_NAME = Public.Tools\r\nQML_IMPORT_VERSION = 1.2\r\n'
    source += 'SOURCES += service.cpp \\\r\n worker.cpp\r\nHEADERS += service.h\r\n'
    source += 'RESOURCES += ui.qrc\r\nQML_IMPORT_PATH += imports\r\nDISTFILES += "Écran.qml"\r\n'
    path = tmp_path / "tools.pro"
    path.write_bytes(source.encode())
    result = extract_qmake(path, root=tmp_path)
    assert not result.get("error")
    module = records(result, "qt_module")[0]
    assert (module["uri"], module["major"], module["minor"]) == ("Public.Tools", 1, 2)
    assert [md["value"] for md in records(result, "qt_source")] == [
        "service.cpp", "worker.cpp", "service.h", "Écran.qml", "ui.qrc"]
    assert records(result, "qt_import_path")[0]["visibility"] == "tooling"
    assert result == parse_qmake(source, relative_file="tools.pro")


@pytest.mark.parametrize("line", [
    "unix {\n QML_IMPORT_NAME = Hidden\n}", "win32: QML_IMPORT_NAME = Hidden",
    "QML_IMPORT_NAME = $$MODULE", "include(other.pri)",
    "QML_IMPORT_NAME = Public.Tools\nSOURCES += $$files(*.cpp)",
    "QML_IMPORT_NAME = Public.Tools\nSOURCES -= service.cpp",
])
def test_qmake_conditions_expansion_functions_never_produce_guessed_context(line):
    result = parse_qmake("QML_IMPORT_MAJOR_VERSION = 1\n" + line)
    assert result["qml_failures"]
    assert records(result, "qt_module") == []


def test_qmake_assignment_semantics_and_evidenced_base_minor():
    result = parse_qmake("QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_MAJOR_VERSION = 1\n"
                         "SOURCES = old.cpp\nSOURCES = new.cpp\nSOURCES += helper.cpp")
    module = records(result, "qt_module")[0]
    assert module["minor"] == 0
    assert module["version_origin"] == "base_major_registration"
    assert module["minor_upper_bound_known"] is False
    assert [md["value"] for md in records(result, "qt_source")] == ["new.cpp", "helper.cpp"]
    for source in ("QML_IMPORT_NAME = A\nQML_IMPORT_VERSION = 1.0\nQML_IMPORT_MAJOR_VERSION = 2",
                   "QML_IMPORT_NAME = A\nQML_IMPORT_VERSION = bogus"):
        assert parse_qmake(source)["qml_failures"]


@pytest.mark.parametrize("reader,name", [(extract_cmake, "CMakeLists.txt"), (extract_qmake, "tools.pro")])
def test_build_reader_containment_utf8_and_actual_read_limits(tmp_path, monkeypatch, reader, name):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / name
    outside.write_bytes(b"project(Outside)")
    assert reader(outside, root=root)["nodes"] == []
    path = root / name
    path.write_bytes(b"\xff")
    assert reader(path, root=root)["qml_failures"]
    path.write_bytes(b"x" * (MAX_PROJECT_BYTES + 1))
    assert reader(path, root=root)["diagnostics"][0]["reason"] == "metadata_size_limit"


def test_cmake_ids_are_comment_stable_and_case_distinct():
    source = "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml main.qml)"
    before, after = parse_cmake(source), parse_cmake("# comment\n" + source)
    assert [n["id"] for n in before["nodes"]] == [n["id"] for n in after["nodes"]]
    assert len({n["id"] for n in before["nodes"]}) == len(before["nodes"])
