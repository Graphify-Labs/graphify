"""INC-QML-60: generic navigation cannot reverse typed Qt/QML membership."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.serve import _load_graph, _shortest_path_text
from tests.qt_consumer_helpers import saved_graph


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("legacy_membership", [False, True])
def test_req_qml010_ac04_typed_membership_requires_explicit_undirected_query(
        tmp_path, directed, legacy_membership):
    """Actual producer/JSON roles retain direction, including unannotated legacy links.

    The optional parser is required to make the source-backed fixture; parser-
    absence install behavior belongs to its separate core-only acceptance.
    """
    pytest.importorskip("tree_sitter_language_pack", reason="Source-backed QML path fixture needs the QML extra")
    _, extraction, component, prop, _ = saved_graph(tmp_path)
    graph = build_from_json(extraction, root=tmp_path, directed=directed)
    path = tmp_path / "direction.json"
    assert to_json(graph, {}, str(path), force=True, built_at_commit="fixed")
    if legacy_membership:
        # Historical exports can retain typed declarations but have plain
        # membership links. Declaration authority must still forbid guessing
        # their reverse dependency; no label or suffix is used as a role.
        payload = json.loads(path.read_text(encoding="utf-8"))
        for edge in payload["links"]:
            if edge.get("relation") == "contains":
                edge.pop("metadata", None)
        path.write_text(json.dumps(payload), encoding="utf-8")
    accepted = path.read_bytes()
    restored = _load_graph(str(path))
    forward = _shortest_path_text(restored, {"source": component["id"], "target": prop["id"]})
    assert "Shortest path" in forward and "--contains [EXTRACTED]-->" in forward
    assert "Main.qml:L" in forward and "Path confidence: EXTRACTED" in forward
    reverse = {"source": prop["id"], "target": component["id"]}
    assert "No directed path found" in _shortest_path_text(restored, reverse)
    undirected = _shortest_path_text(restored, {**reverse, "undirected": True})
    assert "Shortest path" in undirected and "<--contains [EXTRACTED]--" in undirected
    assert "Main.qml:L" in undirected and "Path confidence: EXTRACTED" in undirected
    assert path.read_bytes() == accepted
