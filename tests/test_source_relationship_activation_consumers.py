"""INC120: malformed typed activation rejects before durable consumer mutation."""
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
from graphify.source_relationships import FIELD
from tests.test_source_relationship_activation_helpers import (
    accepted, assert_recovery, graph_state, payload, topology,
)


@pytest.mark.parametrize("boundary", ["build", "mapping_load", "path_load"])
@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("damage", ["null", "false", "number", "empty_text", "text", "empty_mapping", "mapping"])
def test_req_qml014_ac04_marker_envelope_rejection_retains_publication_and_recovers(
        tmp_path, boundary, directed, damage):
    """Real APIs reject promised malformed carriers, retain prior bytes, then repair/repeat."""
    valid = payload(tmp_path)
    valid["graph"] = {FIELD: {"contract_version": 1}}
    graph, output, before_bytes = accepted(tmp_path, valid, directed)
    before_graph, expected = graph_state(graph), topology(graph)
    data = deepcopy(valid)
    data["nodes"] = {"null": None, "false": False, "number": 3, "empty_text": "",
                     "text": "text", "empty_mapping": {}, "mapping": {"ordinary": {}}}[damage]
    before = deepcopy(data)
    rejected = tmp_path / "rejected.json"
    if boundary == "path_load":
        rejected.write_text(json.dumps(data), encoding="utf-8")
        bad_bytes = rejected.read_bytes()
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        if boundary == "build":
            build_from_json(data, root=tmp_path, directed=directed)
        else:
            load_node_link_graph(rejected if boundary == "path_load" else data)
    assert data == before and graph_state(graph) == before_graph and output.read_bytes() == before_bytes
    if boundary == "path_load":
        assert rejected.read_bytes() == bad_bytes
    assert_recovery(tmp_path, valid, output, expected, directed)


@pytest.mark.parametrize("boundary", ["build", "mapping_load", "path_load"])
@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("damage", [None, [], "text", 3])
def test_req_qml022_ac06_autoactivated_bad_record_retains_all_input_and_recovers(
        tmp_path, boundary, directed, damage):
    """Actual local-function facts activate validation without a facade/storage marker."""
    valid = payload(tmp_path)
    assert FIELD not in valid.get("graph", {})
    graph, output, before_bytes = accepted(tmp_path, valid, directed)
    before_graph, expected = graph_state(graph), topology(graph)
    data = deepcopy(valid)
    data["nodes"].append(deepcopy(damage))
    before = deepcopy(data)
    rejected = tmp_path / "rejected.json"
    if boundary == "path_load":
        rejected.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        if boundary == "build":
            build_from_json(data, root=tmp_path, directed=directed)
        else:
            load_node_link_graph(rejected if boundary == "path_load" else data)
    assert data == before and graph_state(graph) == before_graph and output.read_bytes() == before_bytes
    assert_recovery(tmp_path, valid, output, expected, directed)


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("force", [False, True])
def test_req_qml014_ac04_rejection_then_real_write_failure_retains_and_repeats(
        tmp_path, monkeypatch, directed, force):
    """Admission failure neither damages accepted state nor wedges subsequent writer recovery."""
    valid = payload(tmp_path)
    graph, output, before_bytes = accepted(tmp_path, valid, directed)
    expected = topology(graph)
    corrupt = deepcopy(valid)
    corrupt["nodes"] = None
    corrupt["graph"] = {FIELD: {"contract_version": 1}}
    with pytest.raises(ValueError, match="SOURCE_RELATIONSHIPS_INVALID"):
        build_from_json(corrupt, root=tmp_path, directed=directed)
    graph.graph.update(_dedup_collapsed=3, _pruned_node_count=2)
    before_graph = graph_state(graph)
    replace, reached = os.replace, []

    def failed(source, target):
        if Path(str(target).removeprefix("\\\\?\\")) == output:
            reached.append(str(target))
            raise OSError(errno.EIO, "injected activation recovery replacement failure")
        return replace(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", failed)
        with pytest.raises(OSError, match="injected activation recovery"):
            to_json(graph, {}, str(output), force=force)
    assert reached and graph_state(graph) == before_graph and output.read_bytes() == before_bytes
    assert_recovery(tmp_path, valid, output, expected, directed)
