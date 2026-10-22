"""REQ-QML-011-AC04/REQ-QML-017-AC04: accepted full refresh retires stale stubs."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.qt_orphan_cleanup import prune_stale_ast_orphans
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_reflection_updates import cpp_source, fixture


@pytest.mark.parametrize("operation", ["invoke", "static_read", "static_write", "property_handle"])
def test_req_qml017_ac04_watch_restored_sdk_source_has_no_stale_generic_placeholder(tmp_path, monkeypatch, operation):
    """An actual source class introduces external type stubs, then is removed."""
    cpp = fixture(tmp_path, operation)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, "watch")
    valid, untouched = cpp.read_bytes(), unrelated(initial)
    cpp.write_bytes(cpp_source(tmp_path, operation, "local_alias"))
    shadow = run(tmp_path, monkeypatch, "watch", [cpp])
    assert "qobject" in shadow
    cpp.write_bytes(valid)
    restored = run(tmp_path, monkeypatch, "watch", [cpp])
    assert "qobject" not in restored, "Removed source declaration left its unreferenced generic AST stub"
    assert normalized(restored) == normalized(initial) == normalized(clean(tmp_path, tmp_path / ".restored-cold"))
    assert unrelated(restored) == untouched


def payload():
    """Prior accepted graph roles differ even when their source path is empty."""
    base = {"file_type": "code", "_origin": "ast", "source_file": "", "source_location": ""}
    nodes: list[dict] = [{**base, "id": name, "label": name} for name in
             ("stale", "fresh", "edge_target", "hyper_target", "typed", "source", "semantic", "callable", "metadata")]
    by_id = {node["id"]: node for node in nodes}
    by_id["typed"]["type"] = "class"
    by_id["source"]["source_file"] = "keep.cpp"
    by_id["semantic"]["_origin"] = "semantic"
    by_id["callable"]["_callable"] = True
    by_id["metadata"]["metadata"] = {"qt": {"contract_version": 1, "kind": "class"}}
    return {"nodes": nodes, "edges": [{"source": "semantic", "target": "edge_target"}],
            "hyperedges": [{"nodes": ["semantic", "hyper_target"]}], "input_tokens": 0}


def test_req_qml011_ac04_cleanup_preserves_authority_references_and_borrowed_dictionaries():
    """Only stale generic placeholders are retired, without in-place mutation."""
    original = payload()
    borrowed = copy.deepcopy(original)
    candidate = prune_stale_ast_orphans(original, fresh_ids={"fresh"}, complete_refresh=True)
    assert {node["id"] for node in candidate["nodes"]} == {node["id"] for node in original["nodes"]} - {"stale"}
    assert original == borrowed
    assert candidate["edges"] == original["edges"] and candidate["hyperedges"] == original["hyperedges"]


@pytest.mark.parametrize("field", ["nodes", "members", "node_ids"])
def test_req_qml011_ac04_hyperedge_member_aliases_protect_source_less_ast_nodes(field):
    """All existing hyperedge membership spellings protect their accepted target."""
    original = payload()
    original["hyperedges"] = [{field: ["stale"]}]
    assert "stale" in {node["id"] for node in prune_stale_ast_orphans(original, fresh_ids=set(), complete_refresh=True)["nodes"]}


def test_req_qml011_ac04_partial_refresh_is_not_authority_to_remove_placeholder():
    original = payload()
    assert prune_stale_ast_orphans(original, fresh_ids=set(), complete_refresh=False) is original


@pytest.mark.parametrize("mode", ["manual", "watch", "watch_policy"])
def test_req_qml011_ac04_complete_refresh_keeps_semantic_connected_and_hyperedge_stub_context(tmp_path, monkeypatch, mode):
    """The production reconcile path retains facts that fresh code cannot recreate."""
    cpp = fixture(tmp_path, "invoke")
    monkeypatch.chdir(tmp_path)
    run(tmp_path, monkeypatch, "watch")
    cpp.write_bytes(cpp_source(tmp_path, "invoke", "local_alias"))
    run(tmp_path, monkeypatch, "watch", [cpp])
    output = tmp_path / "graphify-out/graph.json"
    previous = json.loads(output.read_text(encoding="utf-8"))
    role_nodes = payload()["nodes"]
    retained = [node for node in role_nodes if node["id"] in {"semantic", "edge_target", "hyper_target"}]
    previous["nodes"].extend(retained)
    previous["links"].append({"source": "semantic", "target": "edge_target", "relation": "references",
                              "confidence": "INFERRED", "_origin": "semantic", "source_file": ""})
    previous["hyperedges"] = [{"id": "retained_hyperedge", "nodes": ["semantic", "hyper_target"]}]
    output.write_text(json.dumps(previous), encoding="utf-8")
    cpp.write_bytes(cpp_source(tmp_path, "invoke"))
    if mode == "watch_policy":
        import graphify.qt_incremental as policy
        monkeypatch.setattr(policy, "QT_POLICY_VERSION", policy.QT_POLICY_VERSION + 1)
    restored = run(tmp_path, monkeypatch, "manual" if mode == "manual" else "watch", [cpp])
    assert "qobject" not in restored
    assert {"semantic", "edge_target", "hyper_target"} <= set(restored)
    assert restored.has_edge("semantic", "edge_target")
    assert json.loads(output.read_text(encoding="utf-8"))["hyperedges"] == previous["hyperedges"]
