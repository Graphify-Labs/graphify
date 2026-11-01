"""INC117: source transport closure at actual loaders and raw extract publisher."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

import graphify.__main__ as entrypoint
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from graphify.source_relationships import is_source_graph
from tests.source_observation_helpers import observations, produce, reference, state


@pytest.mark.parametrize("damage", ["links", "duplicate_node", "bool_node", "missing_endpoint"])
def test_req_qml014_ac04_persisted_source_parent_cohort_rejects_without_mutation(tmp_path, damage):
    """Storage-only evidence never authorizes malformed collections, duplicate IDs or missing endpoints."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    payload = json.loads(output.read_text())
    if damage == "links":
        payload["links"] = None
    elif damage == "duplicate_node":
        payload["nodes"].append(deepcopy(payload["nodes"][0]))
    elif damage == "bool_node":
        payload["nodes"][0]["id"] = True
    else:
        token = next(node["id"] for node in payload["nodes"] if node["label"] == "Token")
        payload["nodes"] = [node for node in payload["nodes"] if node["id"] != token]
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        load_node_link_graph(payload)
    assert payload == before


def test_req_qml014_ac04_non_json_source_record_rejects_before_accounting(tmp_path):
    """The real source-record serializer rejects unsupported values before accepted state changes."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    reference(graph)["also_seen"] = [{"metadata": {"not_json": {"value"}}}]
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph)
    assert to_json(graph, {}, str(output), force=True) is False
    assert state(graph) == before and output.read_bytes() == accepted


def test_req_qml022_ac06_raw_source_missing_reference_keeps_existing_drop_policy(tmp_path):
    """A raw source profile does not fabricate a missing ordinary reference endpoint."""
    raw = produce(tmp_path)
    panel = next(node["id"] for node in raw["nodes"] if node["label"] == "Panel")
    raw["edges"].append({"source": panel, "target": "unavailable_target", "relation": "references",
                         "confidence": "EXTRACTED", "source_file": "Data.cs", "source_location": "L3"})
    graph = build_from_json(raw, root=tmp_path)
    assert "unavailable_target" not in graph and is_source_graph(graph)
    assert {row.get("context") for row in observations(reference(graph))} == {"field", "generic_arg"}


def test_req_qml022_ac06_raw_source_nodes_only_retains_empty_link_compatibility(tmp_path):
    """Node-only caller input remains storage-only; absence of links creates no relationships."""
    raw = produce(tmp_path)
    payload = {"nodes": raw["nodes"]}
    graph = load_node_link_graph(payload)
    assert is_source_graph(graph) and graph.number_of_edges() == 0


def test_req_qml022_ac06_actual_raw_extract_publisher_retains_complete_observations(tmp_path, monkeypatch):
    """In-process CLI extract, its incremental raw merge and repeat use the same source composer."""
    produce(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "extract", str(tmp_path), "--code-only", "--no-cluster"])

    def publish():
        with pytest.raises(SystemExit) as stopped:
            entrypoint.main()
        assert stopped.value.code == 0

    publish()
    output = tmp_path / "graphify-out/graph.json"
    first = load_node_link_graph(output)
    assert {row.get("context") for row in observations(reference(first))} == {"field", "generic_arg"}
    source = tmp_path / "Data.cs"
    source.write_bytes(source.read_bytes().replace(b"void Nested() {} Nested();", b""))
    publish()
    changed = load_node_link_graph(output)
    assert is_source_graph(changed)
    assert not any("csharp_local_function" in node.get("metadata", {}) for _, node in changed.nodes(data=True))
    assert {row.get("context") for row in observations(reference(changed))} == {"field", "generic_arg"}
    accepted = output.read_bytes()
    publish()
    assert output.read_bytes() == accepted
