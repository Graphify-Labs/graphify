"""INC-QML-53: all source-backed resource providers share one uncertainty policy."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_csharp
from graphify.extractors.qml_facts import encode_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from graphify.qt_project_index import QtProjectIndex
from tests.qt_analysis_helpers import analysis


MODULE = "qt_add_qml_module(app URI Public.Tools RESOURCE_PREFIX /ui NO_RESOURCE_TARGET_PATH QML_FILES Main.qml)\n"


def corpus(root, *, representation="cmake", target="Other.qml", variant="unique"):
    """The real producer accepts both declarations; endpoint choice stays unresolved."""
    sources = {"Main.qml": "Item { property int primary: 1 }\n",
               "Other.qml": "Item { property int secondary: 2 }\n"}
    if representation == "cmake":
        prop = "" if target == "Main.qml" else (
            f"set_source_files_properties({target} PROPERTIES QT_RESOURCE_ALIAS Main.qml)\n")
        sources["CMakeLists.txt"] = prop + MODULE + f"qt_add_resources(app extras PREFIX /ui FILES {target})\n"
    else:
        locale = ' lang="fr"' if variant == "locale" else ""
        entry = f'<file alias="Main.qml">{target}</file>'
        if variant == "duplicate":
            entry += entry
        sources["CMakeLists.txt"] = MODULE
        sources["extras.qrc"] = f'<RCC><qresource prefix="/ui"{locale}>{entry}</qresource></RCC>'
    return analysis(root, sources)


@pytest.mark.parametrize("representation", ["cmake", "qrc"])
@pytest.mark.parametrize("same_target", [False, True])
def test_req_qml009_ac03_cross_representation_resource_collision_never_selects_a_winner(
    tmp_path, representation, same_target
):
    """Distinct declarations stay ambiguous even when both name the same component."""
    result = corpus(tmp_path, representation=representation, target="Main.qml" if same_target else "Other.qml")
    original = copy.deepcopy(result)
    resolutions = []
    for reverse in (False, True):
        nodes = list(reversed(result["nodes"])) if reverse else result["nodes"]
        edges = list(reversed(result["edges"])) if reverse else result["edges"]
        index = QtProjectIndex(nodes, edges, root=tmp_path)
        answer = index.resolve_url("qrc:/ui/Main.qml")
        assert answer.status == "ambiguous" and answer.target_id is None
        assert answer.reason == "duplicate_resource_alias" and answer.evidence
        expected = {node["id"] for node in result["nodes"]
                    if qml_metadata(node).get("kind") == "component"
                    and node["source_file"] in ({"Main.qml"} if same_target else {"Main.qml", "Other.qml"})}
        assert set(answer.candidates) == expected
        assert index.resolve_url("Main.qml", "qrc:/ui/Base.qml") == answer
        resolutions.append(answer)
    assert resolutions[0] == resolutions[1]
    assert result == original


@pytest.mark.parametrize("variant,status,reason", [
    ("duplicate", "ambiguous", "duplicate_resource_alias"),
    ("locale", "unsupported", "resource_locale_dependent"),
    ("missing", "unavailable", "resource_target_outside_corpus"),
])
def test_req_qml009_ac03_unestablished_explicit_provider_cannot_fall_back_to_module(
    tmp_path, variant, status, reason
):
    """An accepted module cannot erase explicit alias uncertainty or missing corpus evidence."""
    result = corpus(tmp_path, representation="qrc", target="Missing.qml" if variant == "missing" else "Other.qml",
                    variant=variant)
    outcomes = []
    for nodes in (result["nodes"], list(reversed(result["nodes"]))):
        answer = QtProjectIndex(nodes, result["edges"], root=tmp_path).resolve_url("qrc:/ui/Main.qml")
        assert (answer.status, answer.reason, answer.target_id) == (status, reason, None)
        outcomes.append(answer)
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("declaration", ["qt_add_resources(app extras PREFIX /ui FILES Main.qml)\n", MODULE],
                         ids=["explicit_alias", "module_generated"])
def test_req_qml010_ac02_identical_declaration_copies_are_not_distinct_providers(tmp_path, declaration):
    """Transport can repeat an exact fact ID; this does not create a new declaration."""
    result = analysis(tmp_path, {"CMakeLists.txt": declaration,
                                 "Main.qml": "Item {}\n"})
    baseline = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path).resolve_url("qrc:/ui/Main.qml")
    assert baseline.status == "resolved"
    repeated = QtProjectIndex(result["nodes"] + copy.deepcopy(result["nodes"]), result["edges"], root=tmp_path)
    assert repeated.resolve_url("qrc:/ui/Main.qml") == baseline


def test_req_qml009_ac03_missing_module_provider_cannot_borrow_explicit_target(tmp_path):
    """A matching module declaration outside the admitted corpus keeps uncertainty."""
    result = analysis(tmp_path, {
        "CMakeLists.txt": "set_source_files_properties(Missing.qml PROPERTIES QT_RESOURCE_ALIAS Main.qml)\n"
                         + MODULE.replace("QML_FILES Main.qml", "QML_FILES Missing.qml")
                         + "qt_add_resources(app extras PREFIX /ui FILES Main.qml)\n",
        "Main.qml": "Item {}\n",
    })
    answer = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path).resolve_url("qrc:/ui/Main.qml")
    assert answer.status == "unavailable" and answer.target_id is None
    assert answer.reason == "resource_target_outside_corpus" and answer.evidence


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml010_ac02_conflicting_copies_of_one_declaration_identity_are_rejected(tmp_path, reverse):
    """Coalescing exact copies cannot authorize a conflicting transported alias target."""
    result = analysis(tmp_path, {"CMakeLists.txt": "qt_add_resources(app extras PREFIX /ui FILES Main.qml)\n",
                                 "Main.qml": "Item {}\n", "Other.qml": "Item {}\n"})
    alias = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "resource_alias")
    conflicting = copy.deepcopy(alias)
    metadata = qml_metadata(conflicting)
    metadata["target_path"] = "Other.qml"
    conflicting["metadata"]["qml"] = encode_metadata(metadata)
    nodes = result["nodes"] + [conflicting]
    with pytest.raises(ValueError, match="conflicting records for declaration identity"):
        QtProjectIndex(list(reversed(nodes)) if reverse else nodes, result["edges"], root=tmp_path)


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml010_ac02_shared_csharp_namespace_is_not_a_conflicting_qt_declaration(tmp_path, reverse):
    """Qt provider integrity must not redefine generic C# namespace identity.

    C# intentionally shares a namespace ID across source files. Both direct
    index construction and a complete mixed-language scan retain that contract.
    """
    result = analysis(tmp_path, {"CMakeLists.txt": "qt_add_resources(app extras PREFIX /ui FILES Main.qml)\n",
                                 "Main.qml": "Item {}\n"})
    paths, records = [], []
    for filename, name in (("First.cs", "First"), ("Second.cs", "Second")):
        path = tmp_path / filename
        path.write_text(f"namespace Shared {{ public class {name} {{ }} }}\n", encoding="utf-8")
        paths.append(path)
        records.append(extract_csharp(path))
    namespaces = [node for item in records for node in item["nodes"] if node.get("type") == "namespace"]
    assert len(namespaces) == 2 and namespaces[0]["id"] == namespaces[1]["id"]
    assert namespaces[0]["source_file"] != namespaces[1]["source_file"]
    nodes = result["nodes"] + [node for item in records for node in item["nodes"]]
    index = QtProjectIndex(list(reversed(nodes)) if reverse else nodes, result["edges"], root=tmp_path)
    assert index.resolve_url("qrc:/ui/Main.qml").status == "resolved"
    mixed = extract(paths + [tmp_path / "Main.qml", tmp_path / "CMakeLists.txt"], root=tmp_path,
                    cache_root=tmp_path / "mixed-cache", parallel=False)
    assert not mixed.get("qml_failures") and not mixed.get("qt_failures") and not mixed.get("failed_sources")


def test_req_qml009_ac03_duplicate_module_declarations_do_not_coalesce_same_target(tmp_path):
    """A second generated mapping is a competing resource provider, not extra richness."""
    result = analysis(tmp_path, {"CMakeLists.txt": MODULE + MODULE, "Main.qml": "Item {}\n"})
    answer = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path).resolve_url("qrc:/ui/Main.qml")
    assert answer.status == "ambiguous" and answer.reason == "duplicate_resource_alias"
    assert len(answer.candidates) == 1 and answer.target_id is None


def test_req_qml010_ac03_published_membership_retains_cross_provider_ambiguity(tmp_path):
    """Real extraction/build/export/reload cannot publish the formerly chosen resource edge."""
    result = corpus(tmp_path)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    saved = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    sites = [qml_metadata(node) for _, node in saved.nodes(data=True)
             if qml_metadata(node).get("kind") == "membership_resolution"
             and qml_metadata(node).get("declaration_kind") == "resource_alias"]
    assert len(sites) == 1
    assert sites[0]["status"] == "ambiguous" and sites[0]["reason"] == "duplicate_resource_alias"
    assert not sites[0]["target_id"]
    assert not any(edge.get("context") == "qt_resource_membership" for _, _, edge in saved.edges(data=True))
