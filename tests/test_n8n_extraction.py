"""Tests for n8n workflow extraction.

An exported n8n workflow is data-shaped JSON, so :func:`extract_json` skips it
(#1224) and the file contributes nothing to the graph — even though its
``nodes``/``connections`` pair is the program itself. :func:`extract_n8n_workflow`
reads those two structures, and ``_get_extractor`` routes to it by content sniff
before generic ``.json`` dispatch.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import (
    _get_extractor,
    _make_id,
    extract_json,
    extract_n8n_workflow,
    is_n8n_workflow_path,
)

WORKFLOW = {
    "name": "Demo Router",
    "nodes": [
        {"id": "a1", "name": "Приём сообщения", "type": "n8n-nodes-base.telegramTrigger",
         "typeVersion": 1, "position": [0, 0], "parameters": {}},
        {"id": "a2", "name": "Это /start?", "type": "n8n-nodes-base.if",
         "typeVersion": 2, "position": [10, 0], "parameters": {}},
        {"id": "a3", "name": "Отправить приветствие", "type": "n8n-nodes-base.telegram",
         "typeVersion": 1, "position": [20, 0], "parameters": {}},
        {"id": "a4", "name": "Блок 1: приём", "type": "n8n-nodes-base.stickyNote",
         "typeVersion": 1, "position": [0, 40], "parameters": {"content": "заметка"}},
    ],
    "connections": {
        "Приём сообщения": {"main": [[{"node": "Это /start?", "type": "main", "index": 0}]]},
        "Это /start?": {"main": [
            [{"node": "Отправить приветствие", "type": "main", "index": 0}],
            [],
        ]},
    },
    "active": True,
    "settings": {},
}


def _write_workflow(path: Path, doc: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc if doc is not None else WORKFLOW,
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


def _flow(result: dict) -> set[tuple[str, str]]:
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (by_id.get(e["source"], e["source"]), by_id.get(e["target"], e["target"]))
        for e in result["edges"] if e["relation"] == "calls"
    }


def test_workflow_is_routed_to_the_n8n_extractor(tmp_path):
    """Generic .json dispatch would skip it as data JSON and yield nothing."""
    wf = _write_workflow(tmp_path / "router.json")
    assert _get_extractor(wf) is extract_n8n_workflow
    assert extract_json(wf)["nodes"] == []


def test_non_workflow_json_is_left_to_json_config(tmp_path):
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps({"name": "demo", "dependencies": {"left-pad": "^1"}}),
                        encoding="utf-8")
    assert not is_n8n_workflow_path(manifest)
    assert _get_extractor(manifest) is extract_json


def test_community_node_workflow_is_recognized_structurally(tmp_path):
    """A workflow built only from community nodes carries no n8n-nodes-base marker."""
    doc = json.loads(json.dumps(WORKFLOW))
    for node in doc["nodes"]:
        node["type"] = node["type"].replace("n8n-nodes-base.", "@acme/n8n-nodes-acme.")
    assert is_n8n_workflow_path(_write_workflow(tmp_path / "community.json", doc))


def test_steps_and_control_flow_become_nodes_and_edges(tmp_path):
    result = extract_n8n_workflow(_write_workflow(tmp_path / "router.json"))

    assert "Приём сообщения" in _labels(result)
    assert _flow(result) == {
        ("Приём сообщения", "Это /start?"),
        ("Это /start?", "Отправить приветствие"),
    }


def test_every_step_is_contained_by_the_workflow_node(tmp_path):
    wf = _write_workflow(tmp_path / "router.json")
    result = extract_n8n_workflow(wf)

    file_nid = _make_id(str(wf))
    contained = {e["target"] for e in result["edges"]
                 if e["relation"] == "contains" and e["source"] == file_nid}
    assert len(contained) == len(WORKFLOW["nodes"])
    assert {n["label"] for n in result["nodes"] if n["id"] == file_nid} == {"Demo Router"}


def test_sticky_notes_are_documents_and_carry_no_control_flow(tmp_path):
    result = extract_n8n_workflow(_write_workflow(tmp_path / "router.json"))

    sticky = [n for n in result["nodes"] if n["label"] == "Блок 1: приём"]
    assert [n["file_type"] for n in sticky] == ["document"]
    sticky_id = sticky[0]["id"]
    assert not [e for e in result["edges"]
                if e["relation"] == "calls" and sticky_id in (e["source"], e["target"])]


def test_cyrillic_step_names_survive_id_normalization(tmp_path):
    """Cyrillic must not collapse to a single per-file id (#811)."""
    result = extract_n8n_workflow(_write_workflow(tmp_path / "router.json"))
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids))
    assert all(_make_id("x", n["label"]) != "x" for n in result["nodes"][1:])


def test_source_location_points_at_the_step_definition(tmp_path):
    wf = _write_workflow(tmp_path / "router.json")
    result = extract_n8n_workflow(wf)
    lines = wf.read_text(encoding="utf-8").splitlines()

    for node in result["nodes"]:
        line_no = int(node["source_location"].lstrip("L"))
        if line_no > 1:
            assert node["label"] in lines[line_no - 1]


def test_malformed_json_reports_an_error_instead_of_raising(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text('{"nodes": [ "connections": "typeVersion"', encoding="utf-8")
    result = extract_n8n_workflow(broken)
    assert result["nodes"] == [] and result["error"]


def test_json_without_a_nodes_array_is_skipped(tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"connections": {}, "typeVersion": 1}), encoding="utf-8")
    result = extract_n8n_workflow(other)
    assert result["nodes"] == [] and result["skipped"]
