"""INC-QML-89 source-owned local identity survives direct producer entry points."""
from __future__ import annotations

import copy

import pytest

from graphify.build import build, build_from_json
from graphify.extract import extract_csharp


@pytest.mark.parametrize("entry", ["build", "build_from_json"])
@pytest.mark.parametrize("dedup", [False, True])
def test_req_qml022_ac06_direct_same_line_local_scopes_are_not_semantic_ghosts(tmp_path, entry, dedup):
    """Typed declaration provenance survives without the facade-only AST tier stamp."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){{void Local(){}Local();}{void Local(){}Local();}}}")
    result = extract_csharp(path)
    originals = {node["id"] for node in result["nodes"] if "csharp_local_function" in node.get("metadata", {})}
    assert len(originals) == 2 and all("_origin" not in node for node in result["nodes"])
    data = copy.deepcopy(result)
    graph = build([data], root=tmp_path, dedup=dedup) if entry == "build" else build_from_json(data, root=tmp_path, dedup=dedup)
    retained = {identity for identity, node in graph.nodes(data=True) if "csharp_local_function" in node.get("metadata", {})}
    assert retained == originals
    for local in originals:
        assert {data["relation"] for _, _, data in graph.edges(data=True) if data["_tgt"] == local} >= {"contains", "calls"}
