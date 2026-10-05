"""REQ-QML-008-AC02/016-AC01 retain native ownership over borrowed header facts."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.qt_qml_pipeline import resolve_qt_qml
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_cpp_definition_ownership import CPP, HEADER, canonical_run


def accepted_context(root, *, qualified, conflict=False):
    """Use real finalized generic identities and unchanged accepted header overlays.

    Only implementation overlays are being refreshed. Generic canonical nodes
    remain accepted inputs, including their exact header/definition provenance.
    """
    cpp = CPP.replace("Backend::run", "Shared::Backend::run") if qualified else CPP
    sources = {"backend.hpp": HEADER, "backend.cpp": cpp}
    if conflict:
        sources["competing.hpp"] = HEADER
    complete = analysis(root, sources)
    nodes = [node for node in complete["nodes"]
             if not (node.get("source_file") == "backend.cpp" and qt_metadata(node))]
    identities = {node["id"] for node in nodes}
    edges = [edge for edge in complete["edges"]
             if edge["source"] in identities and edge["target"] in identities]
    return complete, nodes, edges


def refresh(root, nodes, edges):
    """Exercise the same scratch overlay/join owner used by the extraction facade."""
    fresh = {"nodes": [], "edges": []}
    added_nodes, added_edges = [], []
    failures = resolve_qt_qml([root / "backend.cpp"], [fresh], added_nodes, added_edges,
        root=root, context_nodes=nodes, context_edges=edges)
    assert not failures and not fresh.get("qml_failures") and not fresh.get("qt_failures")
    return fresh, {"nodes": nodes + added_nodes, "edges": edges + added_edges}


@pytest.mark.parametrize("qualified", [True, False])
def test_req_qml008_ac02_borrowed_complete_header_is_not_counted_as_two_definitions(tmp_path, qualified):
    """Two representations of one source body keep the canonical method and real containment."""
    complete, nodes, edges = accepted_context(tmp_path, qualified=qualified)
    method = canonical_run(complete)
    before = copy.deepcopy((nodes, edges))
    fresh = {"nodes": [], "edges": []}
    enrich_qt_cpp([tmp_path / "backend.cpp"], [fresh], root=tmp_path,
                 accepted_nodes=nodes, accepted_edges=edges)
    assert not fresh.get("qml_failures")
    member = sites(fresh, "member")[0]
    metadata = qt_metadata(member)
    assert metadata["class_name"] == "Shared::Backend" and metadata["class_id"]
    assert metadata["generic_target_id"] == method["id"]
    assert metadata["owner_id"] == metadata["class_id"]
    assert any(edge["source"] == metadata["class_id"] and edge["target"] == member["id"]
               and edge["relation"] == "contains" and edge["confidence"] == "EXTRACTED"
               for edge in fresh["edges"])
    assert (nodes, edges) == before


@pytest.mark.parametrize("qualified", [True, False])
def test_req_qml016_ac01_context_pipeline_preserves_owned_emission_through_json_reload(tmp_path, qualified):
    """A refreshed implementation joins unchanged signal facts without rewriting borrowed data."""
    complete, nodes, edges = accepted_context(tmp_path, qualified=qualified)
    method = canonical_run(complete)
    before = copy.deepcopy((nodes, edges))
    fresh, assembled = refresh(tmp_path, nodes, edges)
    member = sites(fresh, "member")[0]
    member_metadata = qt_metadata(member)
    assert member_metadata["class_id"] and member_metadata["generic_target_id"] == method["id"]
    emission = sites(fresh, "emission")[0]
    metadata = qt_metadata(emission)
    assert metadata["owner_id"] == method["id"] and metadata["owner_class"] == "Shared::Backend"
    assert metadata["status"] == "resolved" and metadata["target_id"]
    span = metadata["span"]
    original = (tmp_path / "backend.cpp").read_bytes()
    assert original[span["start_byte"]:span["end_byte"]] == b"changed()"
    graph = build_from_json(assembled, root=tmp_path)
    assert graph.has_edge(member_metadata["class_id"], member["id"])
    assert graph.has_edge(method["id"], emission["id"])
    assert graph.has_edge(emission["id"], metadata["target_id"])
    assert not any(edge.get("relation") == "calls" for _, _, edge in graph.edges(emission["id"], data=True))
    path = tmp_path / "refreshed.json"
    assert to_json(graph, {}, str(path))
    reloaded = build_from_json(json.loads(path.read_text(encoding="utf-8")), root=tmp_path)
    assert reloaded.has_edge(method["id"], emission["id"])
    assert reloaded.has_edge(emission["id"], metadata["target_id"])
    assert reloaded.has_edge(member_metadata["class_id"], member["id"])
    assert qt_metadata(reloaded.nodes[emission["id"]])["owner_id"] == method["id"]
    assert (nodes, edges) == before


def test_req_qml008_ac02_borrowed_distinct_complete_bodies_remain_ambiguous(tmp_path):
    """Deduplication may join representations of one body, never two original source bodies."""
    _, nodes, edges = accepted_context(tmp_path, qualified=False, conflict=True)
    classes = sites({"nodes": nodes}, "class")
    assert len(classes) == 2 and all(qt_metadata(node)["is_definition"] is True for node in classes)
    before = copy.deepcopy((nodes, edges))
    fresh, _ = refresh(tmp_path, nodes, edges)
    member = sites(fresh, "member")[0]
    emission = sites(fresh, "emission")[0]
    assert qt_metadata(member)["class_id"] == ""
    assert qt_metadata(emission)["status"] != "resolved" and qt_metadata(emission)["target_id"] == ""
    assert (nodes, edges) == before


@pytest.mark.parametrize("body", [False, None])
def test_req_qml008_ac02_borrowed_missing_body_authority_stays_unavailable(tmp_path, body):
    """A forward/legacy metadata record cannot substitute for accepted complete-body authority."""
    _, nodes, edges = accepted_context(tmp_path, qualified=False)
    for node in nodes:
        if qt_metadata(node).get("kind") == "class":
            update_qt(node, is_definition=body)
    before = copy.deepcopy((nodes, edges))
    fresh, _ = refresh(tmp_path, nodes, edges)
    assert qt_metadata(sites(fresh, "member")[0])["class_id"] == ""
    emission = qt_metadata(sites(fresh, "emission")[0])
    assert emission["status"] == "unavailable" and emission["target_id"] == ""
    assert not any(edge.get("context") == "qt_signal_emit" for edge in fresh["edges"])
    assert (nodes, edges) == before


@pytest.mark.parametrize("spelling", ["dot", "windows_separator", "absolute"])
def test_req_qml008_ac02_borrowed_body_provenance_keeps_equivalent_path_representation(tmp_path, spelling):
    """A valid alternate path representation cannot manufacture a second copy of one body."""
    complete, nodes, edges = accepted_context(tmp_path, qualified=False)
    method = canonical_run(complete)
    for node in nodes:
        if qt_metadata(node).get("kind") == "class":
            node["source_file"] = str(tmp_path / "backend.hpp") if spelling == "absolute" else (
                "./backend.hpp" if spelling == "dot" else ".\\backend.hpp")
    before = copy.deepcopy((nodes, edges))
    fresh = {"nodes": [], "edges": []}
    enrich_qt_cpp([tmp_path / "backend.cpp"], [fresh], root=tmp_path,
                 accepted_nodes=nodes, accepted_edges=edges)
    member = qt_metadata(sites(fresh, "member")[0])
    assert member["class_id"] and member["generic_target_id"] == method["id"]
    assert member["class_name"] == "Shared::Backend" and (nodes, edges) == before
