"""Adversarial work bounds and syntax/read failures at actual metadata interfaces."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphify.extractors.qml_cmake import extract_cmake, parse_cmake
from graphify.extractors.qml_project_read import MAX_PROJECT_BYTES
from graphify.extractors.qml_qmake import parse_qmake
from graphify.extractors.qml_resources import parse_qrc
from graphify.extractors.qml_types import parse_qmltypes
from graphify.qt_resource_index import normalize_url
from graphify.qml_resolution_types import Resolution


@pytest.mark.parametrize("source", [
    "# comment without newline", '#[[ unterminated comment',
    'qt_add_qml_module(app URI "unclosed)', 'qt_add_qml_module(app URI Public.Tools',
    'qt_add_qml_module(app URI A URI B)', 'qt_add_qml_module(app URI)',
    'qt_add_qml_module(app URI bad-name VERSION 1.0)', 'endif()',
    'function(f)\nendmacro()', 'qt_add_qml_module(app URI A QML_FILES a; b)',
])
def test_cmake_comments_and_syntax_boundary(source):
    result = parse_cmake(source)
    if source == "# comment without newline":
        assert not result.get("error")
    else:
        assert result["qml_failures"]


def test_cmake_scope_limit_and_source_file_growth_are_rejected(tmp_path, monkeypatch):
    result = parse_cmake("if(A)\n" * 65 + "endif()\n" * 65)
    assert result["diagnostics"][0]["reason"] == "cmake_scope_limit"
    path = tmp_path / "CMakeLists.txt"
    path.write_bytes(b"x" * (MAX_PROJECT_BYTES + 1))
    original_stat = Path.stat
    # Understate only the size so the real post-read growth guard is exercised;
    # native spelling admission still needs the actual mode and file identity.
    def changed_stat(self, *args, **kwargs):
        actual = original_stat(self, *args, **kwargs)
        if self == path:
            fields = {name: getattr(actual, name) for name in dir(actual) if name.startswith("st_")}
            return SimpleNamespace(**(fields | {"st_size": 1}))
        return actual
    monkeypatch.setattr(Path, "stat", changed_stat)
    actual, understated = original_stat(path), path.stat()
    assert understated.st_size == 1
    assert all(getattr(understated, name) == getattr(actual, name)
               for name in dir(actual) if name.startswith("st_") and name != "st_size")
    assert path.samefile(path)
    assert extract_cmake(path, root=tmp_path)["diagnostics"][0]["reason"] == "metadata_size_limit"


def test_fact_and_token_work_limits_reject_authoritative_partial_results(monkeypatch):
    monkeypatch.setattr("graphify.extractors.qml_project_read.MAX_PROJECT_FACTS", 2)
    result = parse_cmake("qt_add_qml_module(app URI Public.Tools QML_FILES Main.qml)")
    assert result["diagnostics"][0]["reason"] == "metadata_fact_limit"
    assert result["nodes"] == []
    result = parse_cmake("message(" + "x " * 10_001 + ")")
    assert result["diagnostics"][0]["reason"] == "cmake_token_limit"


@pytest.mark.parametrize("source", [
    "}\n", "unix {\n", 'QML_IMPORT_NAME = "unclosed',
    "QML_IMPORT_NAME += A B", "QML_IMPORT_NAME = A\nQML_IMPORT_VERSION = 1.0\nTARGET += a b",
    "QML_IMPORT_NAME = A\nQML_IMPORT_VERSION = 1.0\nHEADERS += *.h",
])
def test_qmake_unbalanced_and_malformed_state_never_creates_context(source):
    assert parse_qmake(source)["qml_failures"]


@pytest.mark.parametrize("source", [
    '<RCC strange="yes"/>', '<RCC><qresource strange="yes"/></RCC>',
    '<RCC><qresource><file strange="yes">Main.qml</file></qresource></RCC>',
    '<RCC><directory/></RCC>', '<RCC>unexpected</RCC>',
    '<RCC><qresource><file empty="true">Main.qml</file></qresource></RCC>',
])
def test_unsupported_xml_forms_are_explicit_partial_failures(source):
    assert parse_qrc(source)["qml_failures"]


@pytest.mark.parametrize("source", [
    'Module { Component { name: "A"; name: "B" } }',
    'Module { Component { name: "A"; Property { type: "int" } } }',
    'Module { Component { name: "A"; Unknown { name: "p" } } }',
    'Module { Component { name: "A"; Property { name: "p"; Parameter { name: "x" } } } }',
    'Module { Component { name: "A"; Method { name: "f"; Unknown { name: "x" } } } }',
    'Module { Component { name: "A"; Method { name: "f"; Parameter { Unknown {} } } } }',
    'Module { Unknown {} }', 'Module { function computed() {} }',
    'var value = 1; Module {}', 'Module { Component { name: "A"; exports: "A/B 1.0" } }',
])
def test_qmltypes_structure_cannot_be_interpreted_as_executable_qml(source):
    assert parse_qmltypes(source)["qml_failures"]


def test_invalid_url_grammar_returns_scoped_resolution_instead_of_reading():
    for url in ("", "x" * 385, "qrc:Main.qml", "https://host/Main.qml", "qrc://[invalid/",
                "qrc:/%ff.qml"):
        assert isinstance(normalize_url(url), Resolution)
