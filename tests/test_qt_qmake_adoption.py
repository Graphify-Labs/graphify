"""REQ-QML-018-AC01: source-owned qmake paths never imply runtime roots."""
from __future__ import annotations

import json

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_qmake import extract_qmake, parse_qmake
from graphify.security import sanitize_metadata


BASE = "QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_VERSION = 1.0\n"


def records(result, kind):
    return [qml_metadata(node) for node in result["nodes"]
            if qml_metadata(node).get("kind") == kind]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_req_qml018_ac01_pwd_paths_preserve_current_file_and_original_token_spans(tmp_path, newline, bom):
    """Quoted Unicode and continued paths retain literal text and byte boundaries."""
    directory = tmp_path / "app"
    directory.mkdir()
    source = bom + (BASE + 'SOURCES += $$PWD/service.cpp \\\n "$$PWD/Écran.cpp"\n'
                    'QML_FILES += $$PWD/ui/Main.qml\n'
                    'QML_IMPORT_PATH += $$PWD/ui/Public/Tools\n'
                    'QMLPATHS += $$PWD/ui\n').replace("\n", newline)
    raw = source.encode()
    path = directory / "tools.pro"
    path.write_bytes(raw)
    result = extract_qmake(path, root=tmp_path)
    assert not result.get("error")
    paths = records(result, "qt_source") + records(result, "qt_import_path")
    assert [md["value"] for md in paths] == [
        "service.cpp", "Écran.cpp", "ui/Main.qml", "ui/Public/Tools", "ui"]
    for md in paths:
        assert md["path_origin"] == "current_file_pwd"
        span = md["span"]
        lexeme = raw[span["start_byte"]:span["end_byte"]].decode()
        assert lexeme.strip('"') == md["source_value"]
        for point in ("start", "end"):
            prefix = raw[:span[f"{point}_byte"]]
            assert span[f"{point}_row"] == prefix.count(b"\n")
            assert span[f"{point}_column"] == len(prefix) - prefix.rfind(b"\n") - 1
    imports = records(result, "qt_import_path")
    assert [md["visibility"] for md in imports] == ["tooling", "build"]
    assert [md["qmake_variable"] for md in imports] == ["QML_IMPORT_PATH", "QMLPATHS"]
    transported = json.loads(json.dumps(result))
    for item in transported["nodes"] + transported["edges"]:
        item["metadata"] = sanitize_metadata(item["metadata"])
    assert records(transported, "qt_source") == records(result, "qt_source")
    assert result == parse_qmake(raw, relative_file="app/tools.pro")


def test_req_qml018_ac01_unrelated_conditional_build_settings_do_not_hide_module():
    """Ignored toolchain settings do not make unconditional membership uncertain."""
    source = BASE + """QT += qml quick
CONFIG += c++17
win32: LIBS += $$PWD/vendor/lib.lib
unix {
 QMAKE_CXXFLAGS += -Wall
 contains(CONFIG, release) {
  DEFINES += RELEASE_BUILD
 }
}
QML_FILES += $$PWD/Main.qml
"""
    result = parse_qmake(source)
    assert not result.get("error")
    assert records(result, "qt_module")[0]["uri"] == "Public.Tools"
    assert records(result, "qt_source")[0]["value"] == "Main.qml"
    assert records(result, "qt_qmake_statement")


@pytest.mark.parametrize("statement", [
    "win32: QML_FILES += $$PWD/Hidden.qml",
    "unix {\n QML_FILES += $$PWD/Hidden.qml\n}",
    "contains(CONFIG, quick): QML_IMPORT_NAME = Hidden",
])
def test_req_qml018_ac01_relevant_conditions_remain_source_owned_uncertainty(statement):
    """A relevant unevaluated branch is inspectable and never authoritative."""
    result = parse_qmake(BASE + "QML_FILES += $$PWD/Visible.qml\n" + statement)
    assert result["partial"] and result["qml_failures"]
    assert not records(result, "qt_module")
    coverage = records(result, "qt_qmake_statement")
    assert any(md.get("status") == "unresolved" and md.get("conditional") for md in coverage)
    assert any(md.get("qmake_variable") == "QML_FILES" and md.get("status") == "observed"
               for md in records(result, "qt_qmake_assignment"))


@pytest.mark.parametrize("value", [
    "$$OTHER/Main.qml", "$${PWD}/Main.qml", "$$PWDtail/Main.qml",
    "$$PWD/$$files(*.qml)", "$$PWD/../../Outside.qml", "C:/Outside.qml",
    "/Outside.qml", "$$PWD/../../Outside.qml", "$$PWD/../x/../../Outside.qml",
])
def test_req_qml018_ac06_unsupported_or_escaping_paths_never_gain_authority(value):
    """Only a lexical current-file prefix within the accepted root is admitted."""
    result = parse_qmake(BASE + f"QML_FILES += {value}\n", relative_file="app/tools.pro")
    assert result["qml_failures"]
    assert not records(result, "qt_module")


@pytest.mark.parametrize("statement", [
    "include(other.pri)", "load(qmltypes)", "system(echo no)",
    "QML_FILES -= $$PWD/Main.qml", "QMLPATHS += $$unknown_path", "PWD = elsewhere",
])
def test_req_qml018_ac06_unknown_mutations_and_pwd_overwrite_are_explicit(statement):
    """Unknown mutation cannot be repaired by running a qmake hook or include."""
    result = parse_qmake(BASE + statement)
    assert result["qml_failures"]
    assert not records(result, "qt_module")


def test_req_qml018_ac01_standalone_import_roles_do_not_create_modules():
    """A normal application project may expose build/tool hints without a module."""
    result = parse_qmake("QT += qml quick\nQML_IMPORT_PATH += $$PWD/Public/Tools\n"
                         "QMLPATHS += $$PWD/imports\n", relative_file="app/project.pri")
    assert not result.get("error") and not records(result, "qt_module")
    imports = records(result, "qt_import_path")
    assert [(md["value"], md["visibility"], md["module_key"]) for md in imports] == [
        ("Public/Tools", "tooling", None), ("imports", "build", None)]


def test_req_qml018_ac01_else_unrelated_scope_remains_non_authoritative():
    """Else scopes retain balance; no platform condition is selected."""
    result = parse_qmake(BASE + "win32 {\n LIBS += native.lib\n} else {\n LIBS += -lnative\n}\n")
    assert not result.get("error") and records(result, "qt_module")


@pytest.mark.parametrize("value", ['"Main.qml"suffix', 'prefix"Main.qml"', '"Main.qml""Other.qml"'])
def test_req_qml018_ac06_quote_concatenation_is_not_invented_as_two_paths(value):
    """Unsupported qmake token concatenation rejects the required source fact."""
    assert parse_qmake(BASE + f"QML_FILES += {value}\n")["qml_failures"]


def test_req_qml018_ac06_scope_depth_is_bounded():
    """Nested source scopes are refused before unbounded branch processing."""
    result = parse_qmake("win32 {\n" * 65 + BASE + "}\n" * 65)
    assert result["diagnostics"][0]["reason"] == "qmake_scope_limit"


def test_req_qml018_ac01_message_text_does_not_mutate_named_metadata():
    """Build messages mentioning source variables are coverage, not assignments."""
    result = parse_qmake(BASE + 'message("QML_FILES = $$UNKNOWN")\n'
                         'warning("include(other.pri)")\nQML_FILES += $$PWD/Main.qml\n')
    assert not result.get("error")
    assert [md["value"] for md in records(result, "qt_source")] == ["Main.qml"]


def test_req_qml018_ac06_multibyte_path_transport_limit_is_explicit():
    """UTF-8 transport bytes are bounded independently of character count."""
    result = parse_qmake(BASE + "QML_FILES += $$PWD/" + "é" * 200 + ".qml\n")
    assert result["diagnostics"][0]["reason"] == "qmake_path_limit"
