"""INC117: corrupted complete evidence and actual write failures retain accepted state."""
from __future__ import annotations

from copy import deepcopy
import errno
import json
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.source_observation_helpers import observations, produce, reference, state


@pytest.mark.parametrize("damage", ["list", "record", "source", "target", "relation", "key", "_src", "_tgt", "also_seen"])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml014_ac04_malformed_source_evidence_rejects_before_accounting(tmp_path, damage, force):
    """Nested endpoints/lists cannot compete with the owning logical arc or erase accepted products."""
    raw = produce(tmp_path)
    graph = build_from_json(raw, root=tmp_path, directed=True)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    edge = reference(graph)
    if damage == "list":
        edge["also_seen"] = {}
    elif damage == "record":
        edge["also_seen"] = [None]
    else:
        edge["also_seen"] = [{damage: [] if damage == "also_seen" else "foreign"}]
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph)
    assert to_json(graph, {}, str(output), force=force) is False
    assert state(graph) == before and output.read_bytes() == accepted


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml014_ac04_duplicate_persisted_logical_keys_still_reject(tmp_path, directed):
    """The writer correction must not turn the strict loader into a duplicate-key repair path."""
    graph = build_from_json(produce(tmp_path), root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    payload = json.loads(output.read_text())
    payload["links"].append(deepcopy(payload["links"][0]))
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID: duplicate"):
        load_node_link_graph(payload)
    assert payload == before


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml014_ac04_source_observation_write_failure_retention_recovery(tmp_path, monkeypatch, directed):
    """The actual atomic replacement fails once, retaining graph/accounting/disk, then recovers."""
    raw = produce(tmp_path)
    graph = build_from_json(raw, root=tmp_path, directed=directed)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    graph.graph.update(_dedup_collapsed=7, _pruned_node_count=3)
    before = state(graph)
    replace = os.replace

    def failed(source, target):
        if Path(str(target).removeprefix("\\\\?\\")) == output:
            raise OSError(errno.EIO, "injected source evidence write failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failed)
        with pytest.raises(OSError, match="injected source evidence"):
            to_json(graph, {}, str(output), force=True, original_links=raw["edges"])
    assert output.read_bytes() == accepted and state(graph) == before
    assert to_json(graph, {}, str(output), force=True, original_links=raw["edges"])
    loaded = load_node_link_graph(output)
    assert {entry.get("context") for entry in observations(reference(loaded))} == {"field", "generic_arg"}
    recovered = output.read_bytes()
    assert to_json(loaded, {}, str(output), force=True)
    assert output.read_bytes() == recovered


@pytest.mark.parametrize("counter", ["_dedup_collapsed", "_pruned_node_count"])
def test_req_qml014_ac04_source_counter_rejection_is_bounded_and_retains_state(tmp_path, capsys, counter):
    """Counter conversion fails before writing, with no malicious delimiter/value disclosure."""
    graph = build_from_json(produce(tmp_path), root=tmp_path)
    output = tmp_path / "graph.json"
    assert to_json(graph, {}, str(output))
    accepted = output.read_bytes()
    graph.graph[counter] = "public-sentinel\nforged diagnostic"
    before = state(graph)
    assert to_json(graph, {}, str(output), force=True) is False
    message = capsys.readouterr().err
    assert "SOURCE_RELATIONSHIPS_INVALID: invalid source accounting" in message
    assert "public-sentinel" not in message and "forged diagnostic" not in message
    assert state(graph) == before and output.read_bytes() == accepted
