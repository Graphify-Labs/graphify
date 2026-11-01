"""INC-QML-90: source indexer data never becomes a concrete delegate callee."""
from __future__ import annotations

import pytest

from graphify.extract import extract
from tests.test_csharp_indexers import indexers


@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.parametrize("damage", ["valid", "kind_none", "version_unknown", "null_payload"])
def test_req_qml022_ac06_indexer_role_rejects_callable_guess_without_borrowed_owner_edge(tmp_path, complete, damage):
    """A node-only context retains data rejection while actual fresh methods remain callable."""
    member, caller = tmp_path / "Members.cs", tmp_path / "Caller.cs"
    member.write_text("class Key{}partial class Holder{public System.Action this[Key key]=>null;}")
    caller.write_text("partial class Holder{void Real(){}void Use(Key Key){Real();this[Key]();}}")
    context = extract([member], root=tmp_path, cache_root=tmp_path, parallel=False)
    (data,) = indexers(context)
    if damage == "kind_none":
        data["metadata"]["csharp_member"]["kind"] = None
    elif damage == "version_unknown":
        data["metadata"]["csharp_member"]["contract_version"] = 999
    elif damage == "null_payload":
        data["metadata"]["csharp_member"] = None
    result = extract([caller], root=tmp_path, cache_root=tmp_path, parallel=False,
                     resolution_context_nodes=context["nodes"],
                     resolution_context_edges=context["edges"] if complete else [])
    calls = [edge for edge in result["edges"] if edge["relation"] == "calls"]
    assert not any(edge["target"] == data["id"] for edge in calls)
    real = next(node["id"] for node in result["nodes"] if node["label"] == ".Real()")
    assert any(edge["target"] == real for edge in calls)
