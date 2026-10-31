"""REQ-QML-022: precise source identity governs local source ownership only."""
from __future__ import annotations

import copy

import pytest

from graphify.extractors.cpp_functions import free_definition_fact
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_qml_bridge import build_qt_qml_bridge
from tests.qt_analysis_helpers import analysis
from tests.test_qt_member_source_links import LOCAL, accepted_generic


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("profile", ["invalid_suffix", "two_proven", "legacy_untyped"])
def test_req_qml022_ac02_source_fallback_preserves_proof_eligibility_and_real_ambiguity(
        tmp_path, profile, reverse):
    """Retain the old invalid copy; only two eligible peers establish ambiguity.

    Actual collector inputs remain unchanged. A precise free-definition fact
    cannot be copied to an invalid ID to gain ownership, while legacy untyped
    candidates retain conservative ambiguity. Neither path supplies Qt authority.
    """
    path = tmp_path / "local.cpp"
    accepted = analysis(tmp_path, {path.name: LOCAL + "\n"})
    nodes, edges = accepted_generic(accepted)
    chosen = next(node for node in nodes if node.get("_callable") and node["label"] == "collect()")
    original = chosen["id"]
    peer = copy.deepcopy(chosen)
    # Preserve the exact historical bad suffix as a control, rather than
    # silently changing that input to make the old assertion pass.
    peer["id"] = original + "_different" if profile == "invalid_suffix" else "other_" + original
    nodes.append(peer)
    if profile == "legacy_untyped":
        for node in (chosen, peer):
            node["metadata"].pop("cpp_function")
    eligible = [node for node in (chosen, peer) if free_definition_fact(node)]
    assert len(eligible) == {"invalid_suffix": 1, "two_proven": 2, "legacy_untyped": 0}[profile]
    if reverse:
        nodes.reverse()
    before = copy.deepcopy((nodes, edges))
    fresh = {"nodes": [], "edges": []}
    enrich_qt_cpp([path], [fresh], root=tmp_path, accepted_nodes=nodes, accepted_edges=edges)
    assert not fresh.get("qml_failures") and (nodes, edges) == before
    sites = [node for node in fresh["nodes"] if qt_metadata(node).get("kind") == "class"]
    assert len(sites) == 1
    site = sites[0]
    metadata = qt_metadata(site)
    assert metadata["class_id"] == metadata["generic_target_id"] == ""
    assert not metadata["is_qobject"] and not metadata["source_q_object"]
    links = [edge for edge in fresh["edges"] if edge.get("context") == "qt_source_site"
             and edge["target"] == site["id"]]
    if profile == "invalid_suffix":
        assert metadata["owner_id"] == original and len(links) == 1
        assert links[0]["source"] == original and links[0]["confidence"] == "EXTRACTED"
        assert not any(edge.get("source") == peer["id"] for edge in fresh["edges"])
    else:
        assert metadata["owner_id"] == "" and not links
    # Source containment cannot grant QObject/provider/member authority even
    # when the sole eligible enclosing free definition is known exactly.
    bridge = build_qt_qml_bridge(nodes + fresh["nodes"], edges + fresh["edges"], root=tmp_path)
    assert not bridge.provider_records
