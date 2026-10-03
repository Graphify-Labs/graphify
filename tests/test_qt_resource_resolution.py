"""QML-009-AC03 and QML-017: resource mapping, URL bases and accepted corpus."""
import copy
import json
from pathlib import Path

import pytest

from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_cmake import extract_cmake, parse_cmake
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_qmake import extract_qmake, parse_qmake
from graphify.extractors.qml_resources import extract_qrc, parse_qrc
from graphify.qml_resolution_types import fact_node
from graphify.qt_project_index import QtProjectIndex
from graphify.security import sanitize_metadata


def corpus(tmp_path, *, duplicate=False, locale=False):
    source = tmp_path / "Main.qml"
    source.write_bytes(b'Item { property int status: 1 }')
    qml = extract_qml(source, root=tmp_path)
    text = '<RCC><qresource prefix="/ui"><file alias="Écran.qml">Main.qml</file>'
    if duplicate:
        text += '<file alias="Écran.qml">Main.qml</file>'
    text += '</qresource>'
    if locale:
        text += '<qresource prefix="/ui" lang="fr"><file alias="Écran.qml">Main.qml</file></qresource>'
    text += '</RCC>'
    qrc = parse_qrc(text)
    assert not qrc.get("error")
    return qml, qrc


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_qrc_original_byte_spans_utf8_aliases_and_roundtrip(tmp_path, bom, newline):
    raw = bom + newline.join([b'<?xml version="1.0" encoding="UTF-8"?>',
        '<!-- α -->'.encode(), b'<RCC><qresource prefix="/ui">',
        '<file alias="Écran.qml">Main.qml</file>'.encode(), b'</qresource></RCC>']) + newline
    path = tmp_path / "ui.qrc"
    path.write_bytes(raw)
    result = extract_qrc(path, root=tmp_path)
    assert not result.get("error")
    alias = next(n for n in result["nodes"] if qml_metadata(n)["kind"] == "resource_alias")
    span = qml_metadata(alias)["span"]
    assert raw[span["start_byte"]:span["end_byte"]] == '<file alias="Écran.qml">Main.qml</file>'.encode()
    assert qml_metadata(alias)["logical_url"] == "qrc:/ui/Écran.qml"
    assert qml_metadata(alias)["target_path"] == "Main.qml"
    for node in result["nodes"]:
        span = qml_metadata(node)["span"]
        for end in ("start", "end"):
            prefix = raw[:span[f"{end}_byte"]]
            assert span[f"{end}_row"] == prefix.count(b"\n")
            assert span[f"{end}_column"] == len(prefix) - prefix.rfind(b"\n") - 1


def test_qrc_urls_resolve_only_accepted_component_and_explicit_runtime_base(tmp_path):
    qml, qrc = corpus(tmp_path)
    nodes, edges = qml["nodes"] + qrc["nodes"], qml["edges"] + qrc["edges"]
    before = copy.deepcopy((nodes, edges))
    index = QtProjectIndex(nodes, edges, root=tmp_path)
    component = next(n for n in qml["nodes"] if qml_metadata(n)["kind"] == "component")
    for url in ("qrc:/ui/Écran.qml", ":/ui/Écran.qml", "qrc:/ui/%C3%89cran.qml"):
        assert index.resolve_url(url).target_id == component["id"]
    assert index.resolve_url("Écran.qml", "qrc:/ui/Other.qml").target_id == component["id"]
    assert index.resolve_url("Main.qml").reason == "runtime_url_base_unavailable"
    assert index.resolve_url((tmp_path / "Main.qml").as_uri()).target_id == component["id"]
    assert index.resolve_url("Main.qml", (tmp_path / "Other.qml").as_uri()).target_id == component["id"]
    for base in ("qrc://other/ui/Other.qml", "qrc:/ui/Other.qml?variant=1",
                 "qrc:/ui/Other.qml#fragment", "qrc:/ui/../Other.qml"):
        assert index.resolve_url("Écran.qml", base).target_id is None
    assert (nodes, edges) == before
    sanitized = json.loads(json.dumps({"nodes": nodes, "edges": edges}))
    for item in sanitized["nodes"] + sanitized["edges"]:
        item["metadata"] = sanitize_metadata(item["metadata"])
    reload = QtProjectIndex(sanitized["nodes"], sanitized["edges"], root=tmp_path)
    assert reload.resolve_url("qrc:/ui/Écran.qml") == index.resolve_url("qrc:/ui/Écran.qml")


@pytest.mark.parametrize("duplicate,locale,status,reason", [
    (True, False, "ambiguous", "duplicate_resource_alias"),
    (False, True, "unsupported", "resource_locale_dependent"),
])
def test_qrc_duplicate_and_locale_variants_never_guess(tmp_path, duplicate, locale, status, reason):
    qml, qrc = corpus(tmp_path, duplicate=duplicate, locale=locale)
    result = QtProjectIndex(qml["nodes"] + qrc["nodes"], [], root=tmp_path).resolve_url("qrc:/ui/Écran.qml")
    assert (result.status, result.reason, result.target_id) == (status, reason, None)


@pytest.mark.parametrize("source,code", [
    ('<!DOCTYPE RCC [<!ENTITY x SYSTEM "file:///host/private">]><RCC><qresource><file>&x;</file></qresource></RCC>', "QML_QRC_ENTITY"),
    ('<!DOCTYPE RCC [<!ENTITY x "payload">]><RCC/>', "QML_QRC_ENTITY"),
    ('<RCC><qresource><file>../../host.qml</file></qresource></RCC>', "QML_QRC_PATH"),
    ('<RCC><qresource prefix="/../ui"><file>Main.qml</file></qresource></RCC>', "QML_QRC_PATH"),
    ('<RCC><qresource><file alias="../Main.qml">Main.qml</file></qresource></RCC>', "QML_QRC_PATH"),
    ('<RCC><qresource><file>C:/host.qml</file></qresource></RCC>', "QML_QRC_PATH"),
    ('<RCC><qresource>', "QML_QRC_SYNTAX"),
])
def test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected(source, code):
    result = parse_qrc(source)
    assert result["qml_failures"]
    assert result["diagnostics"][0]["code"] == code
    assert not any(qml_metadata(n).get("kind") == "resource_alias" for n in result["nodes"])


def test_qrc_missing_target_and_ignored_file_never_expand_corpus(tmp_path):
    (tmp_path / "Main.qml").write_bytes(b"Item {}")
    qrc = parse_qrc('<RCC><qresource><file>Main.qml</file></qresource></RCC>')
    index = QtProjectIndex(qrc["nodes"], [], root=tmp_path)
    assert index.resolve_url("qrc:/Main.qml").reason == "resource_target_outside_corpus"
    for url in ("qrc:/ui/%2e%2e/Main.qml", "qrc://host/Main.qml", "https://host/Main.qml",
                "qrc:/Main.qml?variant=1", "qrc:/Main.qml#fragment", "file:///host/Main.qml"):
        assert index.resolve_url(url).target_id is None


def test_literal_build_context_and_module_resource_component_mapping(tmp_path):
    qml, _ = corpus(tmp_path)
    cpp = fact_node("service.h", "file", "cpp", "service.h", 1)
    cmake = parse_cmake("qt_add_qml_module(app URI Public.Tools VERSION 1.2 "
                        "RESOURCE_PREFIX /ui QML_FILES Main.qml SOURCES service.h)")
    nodes = qml["nodes"] + cmake["nodes"] + [cpp]
    index = QtProjectIndex(nodes, [], root=tmp_path)
    context = index.module_context("service.h")
    assert context.status == "resolved"
    assert context.target_id is not None
    assert index.module_metadata(context.target_id)["uri"] == "Public.Tools"
    component = index.resolve_component("Public.Tools", "Main")
    assert component.status == "resolved"
    assert index.resolve_url("qrc:/ui/Public/Tools/Main.qml").target_id == component.target_id
    assert index.resolve_url("Main.qml", "qrc:/ui/Public/Tools/Other.qml").target_id == component.target_id
    assert index.resolve_url("qrc:/ui/Public/Tools/%4dain.qml").target_id == component.target_id
    assert index.resolve_component("Public.Tools", "Main", 1, 1).target_id == component.target_id
    assert index.resolve_component("Public.Tools", "Main", 2, 0).target_id is None
    assert index.resolve_component("Other.Tools", "Main").target_id is None
    assert index.module_import("Public.Tools", 1, 2).status == "resolved"
    assert index.module_import("Public.Tools", 2, 0).target_id is None
    assert index.module_context("other/service.h").target_id is None
    other = parse_cmake("qt_add_qml_module(other URI Other.Tools VERSION 1.0 SOURCES service.h)",
                        relative_file="other.cmake")
    conflict = QtProjectIndex(nodes + other["nodes"], [], root=tmp_path).module_context("service.h")
    assert conflict.status == "ambiguous"
    assert conflict.evidence
    duplicate = parse_cmake("qt_add_qml_module(other URI Public.Tools VERSION 1.2 QML_FILES Main.qml)",
                            relative_file="other.cmake")
    assert QtProjectIndex(nodes + duplicate["nodes"], [], root=tmp_path).module_import("Public.Tools").status == "ambiguous"


def test_qmake_qrc_membership_resolves_the_same_component(tmp_path):
    qml, qrc = corpus(tmp_path)
    cpp = fact_node("service.h", "file", "cpp", "service.h", 1)
    qmake = parse_qmake("QML_IMPORT_NAME = Public.Tools\nQML_IMPORT_VERSION = 1.2\n"
                         "HEADERS += service.h\nRESOURCES += resources.qrc")
    index = QtProjectIndex(qml["nodes"] + qrc["nodes"] + qmake["nodes"] + [cpp], [], root=tmp_path)
    assert index.module_context("service.h").status == "resolved"
    assert index.resolve_component("Public.Tools", "Main").target_id == index.resolve_url("qrc:/ui/Écran.qml").target_id


def test_public_qt6_cmake_and_qmake_fixtures_describe_identical_membership():
    root = Path(__file__).parent / "fixtures/qml/project_metadata"
    qml = extract_qml(root / "Main.qml", root=root)
    cpp = fact_node("backend.h", "file", "cpp", "backend.h", 1)
    qrc = extract_qrc(root / "resources.qrc", root=root)
    for metadata in (extract_cmake(root / "CMakeLists.txt", root=root),
                     extract_qmake(root / "tools.pro", root=root)):
        assert not metadata.get("error")
        index = QtProjectIndex(qml["nodes"] + qrc["nodes"] + metadata["nodes"] + [cpp], [], root=root)
        context = index.module_context("backend.h")
        assert context.target_id is not None
        md = index.module_metadata(context.target_id)
        assert (md["uri"], md["major"], md["minor"]) == ("Public.Tools", 1, 0)
        assert index.resolve_component("Public.Tools", "Main").target_id == index.resolve_url("qrc:/ui/Public/Tools/Main.qml").target_id


@pytest.mark.parametrize("same_file", [False, True])
def test_same_target_name_does_not_coalesce_distinct_module_providers(tmp_path, same_file):
    declaration = "qt_add_qml_module(app URI Public.Tools VERSION 1.0)\n"
    if same_file:
        results = [parse_cmake(declaration * 2)]
    else:
        results = [parse_cmake(declaration, relative_file=file) for file in
                   ("first/CMakeLists.txt", "second/CMakeLists.txt")]
    nodes = [node for result in results for node in result["nodes"]]
    providers = [node["id"] for node in nodes if qml_metadata(node).get("kind") == "qt_module"]
    assert len(set(providers)) == 2
    index = QtProjectIndex(nodes, [], root=tmp_path)
    resolution = index.module_import("Public.Tools", 1, 0)
    assert resolution.status == "ambiguous" and resolution.target_id is None
    assert set(resolution.evidence) == set(resolution.candidates) == set(providers)
    assert index.resolve_component("Public.Tools", "Main", 1, 0).status == "ambiguous"
