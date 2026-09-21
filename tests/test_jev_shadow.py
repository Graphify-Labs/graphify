import json

import pytest

from graphify.jev_shadow import JevShadowError, call_typesafe, candidate_slice, load_task, outbound_payload, run, sidecar


def _graph(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"nodes": [
        {"id": "a", "label": "Alpha", "node_type": "function", "source_file": "src/a.py", "source_code": "def secret(): pass"},
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


def test_mocked_typesafe_request_and_response_parsing(tmp_path, monkeypatch):
    payload = outbound_payload(_task(tmp_path), _graph(tmp_path))
    answers = {key: ({"type": "choice", "choice": next(iter(question["criteria"])), "confidence": 1.0, "probabilities": {choice: 1.0 if choice == next(iter(question["criteria"])) else 0.0 for choice in question["criteria"]}} if question["type"] == "choice" else {"type": "noul", "noul": 0.6}) for key, question in payload["questions"].items()}
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps({"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 2}, "answers": answers}).encode()
    def fake_urlopen(request, timeout):
        captured["request"], captured["timeout"] = request, timeout
        return Response()
    monkeypatch.setattr("graphify.jev_shadow.urllib.request.urlopen", fake_urlopen)
    assert call_typesafe(payload, "not-written")["model"] == "jev-1.13.0"
    assert captured["timeout"] == 20
    assert b"def secret" not in captured["request"].data


def test_malformed_typesafe_response_fails_closed(tmp_path):
    with pytest.raises(JevShadowError):
        from graphify.jev_shadow import _validated_response
        _validated_response(outbound_payload(_task(tmp_path), _graph(tmp_path)), {"answers": {}})


def test_dry_run_requires_no_key_or_network(tmp_path, monkeypatch, capsys):
    graph, task = _graph(tmp_path), _task(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("graphify.jev_shadow.urllib.request.urlopen", lambda *_args, **_kwargs: pytest.fail("network called"))
    run(["--task", str(tmp_path / "task.json"), "--graph", str(graph), "--dry-run"])
    assert json.loads(capsys.readouterr().out)["state"]["case_id"] == task["case_id"]


def test_live_mode_fails_before_network_without_key(tmp_path, monkeypatch):
    graph = _graph(tmp_path); _task(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("graphify.jev_shadow.urllib.request.urlopen", lambda *_args, **_kwargs: pytest.fail("network called"))
    with pytest.raises(SystemExit):
        run(["--task", str(tmp_path / "task.json"), "--graph", str(graph)])
