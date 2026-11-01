"""D30: one bounded placeholder convention preserves authored node attributes."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import (
    _backfill_origin,
    _is_external_stub,
    _lost_saved_semantic_nodes,
    build_from_json,
    build_merge,
    finalize_raw_graph_endpoints,
)


def placeholder(**attributes):
    """Use the actual minted record, with only explicitly varied persisted fields."""
    return {"id": "missing", "label": "missing", "file_type": "concept",
            "type": "external", "external": True, "source_file": "", **attributes}


@pytest.mark.parametrize("attributes", [
    {}, {"_origin": "semantic"}, {"community": None}, {"community": 3},
    {"community_name": "Imports", "norm_label": "missing"},
    {"x": 0, "y": -2.5},
])
def test_canonical_legacy_and_exported_shapes_remain_tierless(attributes):
    """A known legacy/presentation shape heals its old stamp and retires without references."""
    node = placeholder(**attributes)
    assert _is_external_stub(node)
    assert not _lost_saved_semantic_nodes([node], [])
    _backfill_origin(node)
    assert "_origin" not in node
    graph = {"nodes": [node], "links": []}
    finalize_raw_graph_endpoints(graph)
    assert graph["nodes"] == []


@pytest.mark.parametrize("attributes", [
    {"metadata": {}}, {"metadata": {"ownership": "authored"}}, {"attributes": {}},
    {"source_location": ""}, {"source_location": None}, {"source_location": "L2"},
    {"note": "Authored rationale"}, {"_origin": None}, {"_origin": "manual"},
    {"_origin": "ast"}, {"label": "Authored label"}, {"file_type": "code"},
    {"type": "class"}, {"external": 1}, {"source_file": None},
    {"source_file": "kept.py"}, {"community": True}, {"community": "3"},
    {"community_name": None}, {"norm_label": "Authored label"}, {"x": True},
    {"x": float("nan")}, {"y": float("inf")}, {"x": "2"},
])
def test_authored_or_noncanonical_shapes_keep_their_data(attributes):
    """Sourceless spelling is insufficient to erase attributes, tiers or orphaned records."""
    node = placeholder(**{"_origin": "semantic", **attributes})
    original = copy.deepcopy(node)
    assert not _is_external_stub(node)
    _backfill_origin(node)
    # NaN is not equal to itself, so compare the original serialized transport.
    assert json.dumps(node, sort_keys=True) == json.dumps(original, sort_keys=True)
    graph = {"nodes": [node], "links": []}
    finalize_raw_graph_endpoints(graph)
    assert graph["nodes"] == [node]
    if node.get("_origin") != "ast":
        assert _lost_saved_semantic_nodes([node], []) == [node]


@pytest.mark.parametrize("missing", ["label", "file_type", "external", "type", "source_file", "id"])
def test_partial_external_shapes_have_no_automatic_cleanup_authority(missing):
    """The full compound mint contract is required, including a stored or graph-owned ID."""
    node = placeholder(_origin="semantic")
    node.pop(missing)
    assert not _is_external_stub(node)
    assert _lost_saved_semantic_nodes([node], []) == [node]


def test_graph_attributes_use_the_actual_identity_and_unicode_presentation():
    """NetworkX keeps IDs outside attributes; presentation normalization cannot invent that ID."""
    node = placeholder(id="café", label="café", norm_label="cafe")
    attrs = {key: value for key, value in node.items() if key != "id"}
    assert _is_external_stub(attrs, node_id="café")
    assert not _is_external_stub(attrs, node_id="unrelated")
    assert not _is_external_stub(attrs)
    assert not _is_external_stub(node, node_id="unrelated")


@pytest.mark.parametrize("attributes", [
    {"metadata": {}}, {"note": "Authored rationale"}, {"_origin": "manual"},
    {"file_type": "code"}, {"file_type": "code", "metadata": {}},
    {"file_type": "code", "external": False},
])
@pytest.mark.parametrize("prune", [False, True])
def test_real_incremental_graph_retains_authored_external_orphans(tmp_path, attributes, prune):
    """Re-extraction or deletion drops the last import while retaining authored content unchanged."""
    node = placeholder(**{"_origin": "semantic", **attributes})
    owner = {"id": "app", "label": "app", "file_type": "code", "source_file": "app.py",
             "source_location": "L1", "_origin": "ast"}
    graph = build_from_json({"nodes": [owner, node], "edges": [
        {"source": "app", "target": "missing", "relation": "imports",
         "confidence": "EXTRACTED", "source_file": "app.py", "_origin": "ast"}]})
    from networkx.readwrite import json_graph
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")
    updated = build_merge([] if prune else [{"nodes": [owner], "edges": []}],
                          graph_path=str(path), root=tmp_path, prune_sources=["app.py"] if prune else None)
    assert updated.degree("missing") == 0
    assert dict(updated.nodes["missing"]) == {key: value for key, value in node.items() if key != "id"}


@pytest.mark.parametrize("external_role", [{"external": True}, {"type": "external"}, {}])
@pytest.mark.parametrize("prune", [False, True])
def test_generic_code_orphan_collection_cannot_bypass_external_role(tmp_path, external_role, prune):
    """Ordinary machine code placeholders still retire; an incomplete external role stays protected."""
    from networkx.readwrite import json_graph
    owner = {"id": "app", "label": "app", "file_type": "code", "source_file": "app.py",
             "source_location": "L1", "_origin": "ast"}
    node = {"id": "missing", "label": "missing", "file_type": "code", **external_role}
    graph = build_from_json({"nodes": [owner, node], "edges": [
        {"source": "app", "target": "missing", "relation": "imports",
         "confidence": "EXTRACTED", "source_file": "app.py", "_origin": "ast"}]})
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")), encoding="utf-8")
    updated = build_merge([] if prune else [{"nodes": [owner], "edges": []}],
                          graph_path=str(path), root=tmp_path, prune_sources=["app.py"] if prune else None)
    assert ("missing" in updated) == bool(external_role)
