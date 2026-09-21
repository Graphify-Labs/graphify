import json

import pytest

from graphify.jev_shadow import JevShadowError, candidate_slice, load_task, outbound_payload, sidecar


def _graph(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"nodes": [
        {"id": "a", "label": "Alpha", "node_type": "function", "source_file": "src/a.py"},
        {"id": "b", "label": "Beta", "node_type": "function", "source_file": "src/b.py"},
        {"id": "c", "label": "Gamma", "node_type": "test", "source_file": "tests/test_a.py"},
    ], "links": [
        {"id": "ab", "source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
        {"id": "bc", "source": "b", "target": "c", "relation": "tests", "confidence": "INFERRED"},
    ]}), encoding="utf-8")
    return path


def _task(tmp_path, **overrides):
    value = {"schema_version": 1, "case_id": "case", "objective": "Change alpha", "changed_files": ["src/a.py"], "seed_nodes": []}
    value.update(overrides)
    path = tmp_path / "task.json"; path.write_text(json.dumps(value), encoding="utf-8")
    return load_task(path)


def test_task_validation_fails_closed(tmp_path):
    with pytest.raises(JevShadowError):
        _task(tmp_path, unexpected=True)
    with pytest.raises(JevShadowError):
        _task(tmp_path, changed_files=[])


def test_candidate_slice_is_deterministic_and_bounded(tmp_path):
    graph, task = _graph(tmp_path), _task(tmp_path)
    assert candidate_slice(graph, task) == candidate_slice(graph, task)
    assert [node["id"] for node in candidate_slice(graph, task)["nodes"]] == ["a", "b", "c"]


def test_outbound_state_excludes_source_contents_and_sidecar_preserves_answers(tmp_path):
    graph, task = _graph(tmp_path), _task(tmp_path)
    original = graph.read_bytes()
    payload = outbound_payload(task, graph)
    serialized = json.dumps(payload)
    assert "def secret" not in serialized
    answers = {}
    for key, question in payload["questions"].items():
        answers[key] = ({"type": "choice", "choice": next(iter(question["criteria"])), "confidence": 0.7, "probabilities": {choice: 1 / len(question["criteria"]) for choice in question["criteria"]}} if question["type"] == "choice" else {"type": "noul", "noul": 0.6})
    result = sidecar(payload, task, graph, {"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 2}, "answers": answers})
    assert result["provenance"] == "JEV_INFERRED"
    assert result["node_judgments"][0]["semantic_role"]["probabilities"]
    assert graph.read_bytes() == original
