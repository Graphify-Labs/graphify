"""REQ-QML-020 publishes literal metadata membership without runtime guesses."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.paths import load_node_link_graph
from graphify.qt_project_index import QtProjectIndex


def fixture(root, system="cmake", resource="resources.qrc"):
    """An unused frontend still has explicit build and resource declarations."""
    sources = {
        "qml/ResizeHandle.qml": "import QtQuick\nItem { id: handle; property int position: 1 }\n",
        "backend.cpp": "class Backend {};\n",
        resource: '<RCC><qresource prefix="/ui"><file alias="handle.qml">'
                  'qml/ResizeHandle.qml</file></qresource></RCC>',
    }
    if system == "cmake":
        sources["CMakeLists.txt"] = "qt_add_qml_module(app URI Public.Layout VERSION 1.0 " \
            "QML_FILES qml/ResizeHandle.qml SOURCES backend.cpp)\n"
    else:
        sources["project.pro"] = "QML_IMPORT_NAME = Public.Layout\nQML_IMPORT_VERSION = 1.0\n" \
            "QML_FILES += qml/ResizeHandle.qml\nSOURCES += backend.cpp\nRESOURCES += " + resource + "\n"
    paths = []
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        paths.append(path)
    result = extract(paths, root=root, cache_root=root, parallel=False)
    assert not result.get("qml_failures")
    return result


def facts(result, kind):
    return [node for node in result["nodes"] if qml_metadata(node).get("kind") == kind]


def apply(root, nodes, edges, declarations, **kwargs):
    """Use actual accepted producer records and the production per-run index."""
    from graphify.qt_project_membership import resolve_project_memberships

    results = {}
    for node in declarations:
        results.setdefault(root / node["source_file"], {"nodes": [], "edges": []})["nodes"].append(node)
    index = QtProjectIndex(nodes, edges, root=root)
    resolve_project_memberships(results, nodes, edges, root=root, project_index=index, **kwargs)
    return [node for result in results.values() for node in result["nodes"]
            if qml_metadata(node).get("kind") == "membership_resolution"]


@pytest.mark.parametrize("system", ["cmake", "qmake"])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml020_ac01_unused_component_has_persisted_build_and_resource_membership(tmp_path, system, directed):
    """Real facade/build/reload connects declared source membership, with no QML instantiation."""
    result = fixture(tmp_path, system)
    declarations = facts(result, "qt_source") + facts(result, "resource_alias")
    sites = facts(result, "membership_resolution")
    assert len(sites) == len(declarations)
    assert all(qml_metadata(site)["status"] == "resolved" for site in sites)
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    assert reloaded.is_directed() is directed
    component = facts(result, "component")[0]["id"]
    for site in sites:
        md = qml_metadata(site)
        assert reloaded.has_edge(md["declaration_id"], site["id"])
        edge = reloaded.edges[site["id"], md["target_id"]]
        assert edge["confidence"] == "EXTRACTED" and edge["relation"] == "references"
        # Directed transport owns direction structurally; the undirected form
        # needs its explicit logical endpoint hints to retain that information.
        if directed:
            assert not reloaded.has_edge(md["target_id"], site["id"])
        else:
            assert (edge["_src"], edge["_tgt"]) == (site["id"], md["target_id"])
        assert qml_metadata(edge)["span"] == md["span"]
    assert any(qml_metadata(site)["target_id"] == component for site in sites)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.resolve_url("qrc:/ui/handle.qml").target_id == component
    assert index.resolve_component("Public.Layout", "ResizeHandle", 1, 0).target_id == component


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "outside_root", "generated",
                                         "conditional", "foreign_module", "duplicate_module", "non_file",
                                         "non_ast_module", "non_ast_target", "non_ast_declaration"])
def test_req_qml020_ac02_source_projection_rejects_unproved_membership(tmp_path, corruption):
    """Wrong paths, source roles and module authority cannot create a guessed endpoint."""
    result = fixture(tmp_path)
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if qml_metadata(node).get("kind") == "qt_source"
                       and qml_metadata(node).get("source_kind") == "qml")
    target = next(node for node in nodes if qml_metadata(node).get("kind") == "component")
    md = qml_metadata(declaration)
    if corruption == "missing":
        nodes[:] = [node for node in nodes if node["source_file"] != target["source_file"]]
    elif corruption == "duplicate":
        nodes.append({**copy.deepcopy(target), "id": target["id"] + "_competing"})
    elif corruption == "non_file":
        target["metadata"]["qml"] = encode_metadata({"kind": "function"})
        for node in nodes:
            if node["source_file"] == target["source_file"]:
                node["type"] = "function"
                node["_callable"] = True
    elif corruption == "foreign_module":
        for node in nodes:
            if qml_metadata(node).get("kind") == "qt_module":
                node["source_file"] = "foreign/CMakeLists.txt"
    elif corruption == "duplicate_module":
        module = next(node for node in nodes if qml_metadata(node).get("kind") == "qt_module")
        nodes.append({**copy.deepcopy(module), "id": module["id"] + "_competing"})
    elif corruption in {"non_ast_module", "non_ast_target", "non_ast_declaration"}:
        chosen = (next(node for node in nodes if qml_metadata(node).get("kind") == "qt_module")
                  if corruption == "non_ast_module" else target if corruption == "non_ast_target" else declaration)
        chosen["_origin"] = "semantic"
    else:
        md[{"outside_root": "value", "generated": "generated", "conditional": "conditional"}[corruption]] = (
            "../../foreign.qml" if corruption == "outside_root" else True)
        declaration["metadata"]["qml"] = encode_metadata({key: value for key, value in md.items() if key != "raw_values"})
    borrowed = list(nodes)
    before = copy.deepcopy((nodes, edges, declaration))
    sites = apply(tmp_path, nodes, edges, [declaration])
    assert len(sites) == 1 and qml_metadata(sites[0])["status"] != "resolved"
    assert not qml_metadata(sites[0])["target_id"]
    assert not [edge for edge in edges if edge.get("source") == sites[0]["id"]]
    assert declaration == before[2]
    assert borrowed == before[0]


@pytest.mark.parametrize("corruption", ["duplicate", "locale", "generated", "missing", "outside_root"])
def test_req_qml020_ac02_resources_reuse_existing_alias_guard_decisions(tmp_path, corruption):
    """Membership cannot reinterpret ambiguous/localized resource lookup as runtime authority."""
    result = fixture(tmp_path)
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if qml_metadata(node).get("kind") == "resource_alias")
    md = qml_metadata(declaration)
    if corruption == "duplicate":
        nodes.append({**copy.deepcopy(declaration), "id": declaration["id"] + "_competing"})
    elif corruption == "missing":
        nodes[:] = [node for node in nodes if node["source_file"] != md["target_path"]]
    else:
        md[{"locale": "locale", "generated": "generated", "outside_root": "target_path"}[corruption]] = (
            "fr" if corruption == "locale" else "../foreign.qml" if corruption == "outside_root" else True)
        declaration["metadata"]["qml"] = encode_metadata({key: value for key, value in md.items() if key != "raw_values"})
    sites = apply(tmp_path, nodes, edges, [declaration])
    assert qml_metadata(sites[0])["status"] != "resolved"
    assert not [edge for edge in edges if edge.get("source") == sites[0]["id"]]


def test_req_qml020_ac03_fresh_derived_sites_replace_borrowed_state_without_mutation(tmp_path):
    """Deleting a provider keeps the site's ID while removing its stale target edge."""
    result = fixture(tmp_path)
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    declaration = next(node for node in nodes if qml_metadata(node).get("kind") == "resource_alias")
    old_site = apply(tmp_path, nodes, edges, [declaration])[0]
    retained = copy.deepcopy(old_site)
    target_file = qml_metadata(declaration)["target_path"]
    nodes[:] = [node for node in nodes if node["source_file"] != target_file]
    new_site = apply(tmp_path, nodes, edges, [declaration])[0]
    assert old_site == retained and old_site is not new_site and new_site["id"] == old_site["id"]
    assert qml_metadata(new_site)["status"] != "resolved"
    assert not [edge for edge in edges if edge.get("source") == new_site["id"]]
    snapshot = copy.deepcopy((nodes, edges))
    apply(tmp_path, nodes, edges, [declaration])
    assert (nodes, edges) == snapshot


def test_req_qml020_ac01_metadata_spans_survive_bom_crlf_unicode_and_sanitation(tmp_path):
    """Projection carries original declaration byte offsets and decoded alias punctuation."""
    component = tmp_path / "qml/ResizeHandle.qml"
    component.parent.mkdir()
    component.write_text("Item {}", encoding="utf-8")
    resource = tmp_path / "resources.qrc"
    raw = '\ufeff<!-- caf\u00e9 \u96ea -->\r\n<RCC><qresource prefix="/ui">\r\n<file alias="handle&amp;.qml">qml/ResizeHandle.qml</file>\r\n</qresource></RCC>\r\n'.encode("utf-8")
    resource.write_bytes(raw)
    result = extract([component, resource], root=tmp_path, cache_root=tmp_path, parallel=False)
    site = facts(result, "membership_resolution")[0]
    span = qml_metadata(site)["span"]
    assert raw[span["start_byte"]:span["end_byte"]] == b'<file alias="handle&amp;.qml">qml/ResizeHandle.qml</file>'
    graph = build_from_json(result, root=tmp_path)
    assert qml_metadata(graph.nodes[site["id"]])["logical_url"] == "qrc:/ui/handle&.qml"


def test_req_qml020_ac02_corrupt_literal_transport_is_rejected(tmp_path):
    """Corruption fails at the actual seam instead of resolving escaped display data."""
    result = fixture(tmp_path)
    declaration = facts(result, "resource_alias")[0]
    declaration["metadata"]["qml"]["raw_values"]["target_path"] = "invalid!"
    with pytest.raises(ValueError, match="QML_METADATA"):
        apply(tmp_path, result["nodes"], result["edges"], [declaration])


def test_req_qml020_ac01_scoped_paths_repeated_declarations_and_query_keep_exact_identity(tmp_path):
    """Equal basenames and repeated declarations keep distinct evidence and source scope."""
    from graphify.serve import _query_graph_text

    paths = [tmp_path / "left/Handle.qml", tmp_path / "right/Handle.qml", tmp_path / "CMakeLists.txt"]
    for path in paths[:2]:
        path.parent.mkdir()
        path.write_text("Item {}", encoding="utf-8")
    paths[2].write_text("qt_add_qml_module(app URI Public.Layout VERSION 1.0 "
                        "QML_FILES left/Handle.qml right/Handle.qml left/Handle.qml)", encoding="utf-8")
    source_bytes = {path: path.read_bytes() for path in paths}
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    declarations, sites = facts(result, "qt_source"), facts(result, "membership_resolution")
    assert len(declarations) == len(sites) == 3 and len({site["id"] for site in sites}) == 3
    components = {node["source_file"]: node["id"] for node in facts(result, "component")}
    assert [qml_metadata(site)["target_id"] for site in sites].count(components["left/Handle.qml"]) == 2
    assert [qml_metadata(site)["target_id"] for site in sites].count(components["right/Handle.qml"]) == 1
    before = copy.deepcopy(declarations)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    lookup = index.resolve_component("Public.Layout", "Handle", 1, 0)
    assert lookup.status == "ambiguous"
    apply(tmp_path, result["nodes"], result["edges"], declarations)
    assert declarations == before
    assert QtProjectIndex(result["nodes"], result["edges"], root=tmp_path).resolve_component(
        "Public.Layout", "Handle", 1, 0) == lookup
    graph = build_from_json(result, root=tmp_path)
    answer = _query_graph_text(graph, "left/Handle.qml", token_budget=8000)
    assert "left/Handle.qml" in answer and "CMakeLists.txt" in answer and "references" in answer
    assert source_bytes == {path: path.read_bytes() for path in paths}


def test_req_qml020_ac02_projection_reads_no_targets_and_executes_no_corpus(tmp_path, monkeypatch):
    """Source parsing precedes this guard; the index/join uses only accepted dictionaries."""
    import builtins
    import subprocess
    from pathlib import Path
    from graphify.qt_project_membership import resolve_project_memberships

    result = fixture(tmp_path)
    declarations = facts(result, "qt_source") + facts(result, "resource_alias")
    active = {}
    for node in declarations:
        active.setdefault(tmp_path / node["source_file"], {"nodes": [], "edges": []})["nodes"].append(node)
    before = copy.deepcopy(declarations)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Membership projection may not read, discover or execute target sources")

    for method in ("open", "read_bytes", "read_text", "glob", "rglob"):
        monkeypatch.setattr(Path, method, forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    sites, _ = resolve_project_memberships(active, result["nodes"], result["edges"], root=tmp_path, project_index=index)
    assert sites and all(qml_metadata(site)["status"] == "resolved" for site in sites)
    assert declarations == before


@pytest.mark.parametrize("bad_location", ["L10", "L1-L999"])
def test_req_qml020_ac02_location_prefix_cannot_authorize_another_source_span(tmp_path, bad_location):
    """A line prefix cannot substitute for the exact transported declaration location."""
    result = fixture(tmp_path)
    declaration = facts(result, "resource_alias")[0]
    assert declaration["source_location"] == "L1"
    declaration["source_location"] = bad_location
    with pytest.raises(ValueError, match="QML_METADATA"):
        apply(tmp_path, result["nodes"], result["edges"], [declaration])


def test_req_qml020_ac03_typed_file_role_survives_punctuation_and_borrowed_publication(tmp_path):
    """Actual publication retains the file label/path while literal metadata survives sanitation."""
    result = fixture(tmp_path, "qmake", "res&ources.qrc")
    declaration = next(node for node in facts(result, "qt_source") if qml_metadata(node)["source_kind"] == "qrc")
    path = tmp_path / "graph.json"
    assert to_json(build_from_json(result, root=tmp_path), {}, str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    nodes, edges = raw["nodes"], raw.get("links", raw.get("edges"))
    target = next(node for node in nodes if node["source_file"] == "res&ources.qrc"
                  and qml_metadata(node).get("kind") == "file")
    assert target["label"] == "res&ources.qrc"
    site = apply(tmp_path, nodes, edges, [declaration])[0]
    assert qml_metadata(site)["status"] == "resolved" and qml_metadata(site)["target_id"] == target["id"]
