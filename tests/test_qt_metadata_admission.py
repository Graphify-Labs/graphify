"""Qt metadata reaches deterministic readers under existing discovery policy."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, cast

import pytest

from graphify.detect import FileType, classify_file, detect
from graphify.extractors import LANGUAGE_EXTRACTORS
from graphify.extractors.qml_facts import qml_metadata


CASES = [
    ("CMakeLists.txt", "cmake", "qt_add_qml_module(tools URI Public.Tools VERSION 1.0 QML_FILES Main.qml)\n", "qt_module"),
    ("module.cmake", "cmake", "qt_add_qml_module(tools URI Public.Tools VERSION 1.0)\n", "qt_module"),
    ("tools.pro", "qmake", "QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_MAJOR_VERSION = 1\n", "qt_module"),
    ("tools.pri", "qmake", "QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_MAJOR_VERSION = 1\n", "qt_module"),
    ("resources.qrc", "qrc", '<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file></qresource></RCC>', "resource_alias"),
    ("plugins.qmltypes", "qmltypes", 'import QtQuick.tooling 1.2\nModule { Component { name: "Service"; exports: ["Public.Tools/Service 1.0"] } }', "qmltypes_export"),
]


@pytest.mark.parametrize("name,key,source,kind", CASES, ids=[case[0] for case in CASES])
def test_qml009_metadata_classification_registry_and_original_source_facts(tmp_path, name, key, source, kind):
    path = tmp_path / name
    original = b"\xef\xbb\xbf" + source.replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(original)
    assert classify_file(path) == FileType.CODE
    discovered = detect(tmp_path)
    assert str(path) in discovered["files"]["code"]
    result = cast(Callable[..., dict], LANGUAGE_EXTRACTORS[key])(path, root=tmp_path)
    assert not result.get("error") and not result.get("qml_failures"), result
    facts = [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind]
    assert facts
    assert all(node["source_file"] == name for node in facts)
    for fact in facts:
        span = qml_metadata(fact)["span"]
        # qmake combines source lines into a module record, including the first
        # line's BOM; syntax-backed CMake/qmltypes records start after it.
        assert 0 <= span["start_byte"] < span["end_byte"] <= len(original)
        assert original[span["start_byte"]:span["end_byte"]].decode("utf-8")


def test_cmake_exact_name_does_not_reclassify_arbitrary_text():
    assert classify_file(Path("CMakeLists.txt")) == FileType.CODE
    for name in ("cmakelists.txt", "CMakeLists.TXT", "CMakeLists.txt.bak", "notes.txt"):
        assert classify_file(Path(name)) != FileType.CODE
    assert classify_file(Path("metadata.QRC")) == FileType.CODE
    assert classify_file(Path("component.UI.QML")) == FileType.CODE


@pytest.mark.parametrize("ignore_name", [".graphifyignore", ".gitignore"])
def test_qt_metadata_discovery_obeys_existing_ignore_policy(tmp_path, ignore_name):
    accepted = tmp_path / "CMakeLists.txt"
    accepted.write_text("qt_add_qml_module(tools URI Public.Tools)\n", encoding="utf-8")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    for name, _, source, _ in CASES:
        (ignored / name).write_text(source, encoding="utf-8")
    (tmp_path / ignore_name).write_text("ignored/\n", encoding="utf-8")
    result = detect(tmp_path)
    assert str(accepted) in result["files"]["code"]
    assert not any("ignored" in Path(value).relative_to(tmp_path).parts for value in result["files"]["code"])


def test_new_metadata_admission_preserves_credential_directory_exclusion(tmp_path):
    credentials = tmp_path / ".ssh"
    credentials.mkdir()
    for name, _, source, _ in CASES:
        (credentials / name).write_text(source, encoding="utf-8")
    result = detect(tmp_path)
    assert result["files"]["code"] == []


@pytest.mark.parametrize("key,source", [
    ("cmake", "if(ENABLE_FEATURE)\nqt_add_qml_module(tools URI Public.Tools)\nendif()\n"),
    ("qmake", "CONFIG(debug): QML_IMPORT_NAME = Public.Tools\n"),
    ("qrc", '<!DOCTYPE RCC [<!ENTITY leak SYSTEM "file:///outside">]><RCC>&leak;</RCC>'),
    ("qmltypes", "Module { Component { name: computedName() } }"),
])
def test_registered_readers_report_unsupported_partial_inputs(tmp_path, key, source):
    path = tmp_path / {"cmake": "CMakeLists.txt", "qmake": "tools.pro", "qrc": "resources.qrc", "qmltypes": "plugins.qmltypes"}[key]
    path.write_text(source, encoding="utf-8")
    result = cast(Callable[..., dict], LANGUAGE_EXTRACTORS[key])(path, root=tmp_path)
    assert result.get("qml_failures"), result
    assert result.get("partial") or result.get("error")
