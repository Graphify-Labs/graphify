import json
import urllib.error

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


def _answers(payload, *, confidence=1.0, probability=1.0, noul=0.6):
    return {
        key: ({"type": "choice", "choice": next(iter(question["criteria"])), "confidence": confidence,
               "probabilities": {choice: probability for choice in question["criteria"]}}
              if question["type"] == "choice" else {"type": "noul", "noul": noul})
        for key, question in payload["questions"].items()
    }


def _response(payload, **kwargs):
    return {"model": "jev-test", "usage": {"input_tokens": 1, "output_tokens": 2},
            "answers": _answers(payload, **kwargs)}


def test_candidate_slice_enforces_node_bound(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [{"id": str(i), "source_file": "src/a.py"} for i in range(50)], "links": []}))
    assert len(candidate_slice(graph, _task(tmp_path))["nodes"]) == 40


def test_candidate_slice_enforces_edge_bound(tmp_path):
    graph = tmp_path / "graph.json"
    nodes = [{"id": str(i), "source_file": "src/a.py"} for i in range(40)]
    links = [{"id": str(i), "source": "0", "target": str(i), "relation": "relates"} for i in range(1, 40)]
    links += [{"id": f"extra-{i}", "source": "0", "target": "1", "relation": "relates"} for i in range(50)]
    graph.write_text(json.dumps({"nodes": nodes, "links": links}))
    assert len(candidate_slice(graph, _task(tmp_path))["edges"]) == 80


def test_explicit_seed_selects_node_without_changed_file_match(tmp_path):
    graph = _graph(tmp_path)
    task = _task(tmp_path, changed_files=["does-not-exist.py"], seed_nodes=["c"])
    assert [node["id"] for node in candidate_slice(graph, task)["nodes"]] == ["c", "b", "a"]


def test_unknown_explicit_seed_fails_closed(tmp_path):
    with pytest.raises(JevShadowError, match="unknown graph node"):
        candidate_slice(_graph(tmp_path), _task(tmp_path, seed_nodes=["missing"]))


@pytest.mark.parametrize("failure", [
    urllib.error.HTTPError("https://api.typesafe.ai", 500, "error", {}, None),
    urllib.error.URLError("offline"),
    TimeoutError(),
])
def test_typesafe_transport_failures_fail_safely(tmp_path, monkeypatch, failure):
    payload = outbound_payload(_task(tmp_path), _graph(tmp_path))
    monkeypatch.setattr("graphify.jev_shadow.urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(JevShadowError):
        call_typesafe(payload, "secret-value")


def test_malformed_json_fails_safely(tmp_path, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b"not-json"
    monkeypatch.setattr("graphify.jev_shadow.urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(JevShadowError):
        call_typesafe(outbound_payload(_task(tmp_path), _graph(tmp_path)), "secret-value")


@pytest.mark.parametrize("field,value", [("confidence", -0.1), ("confidence", 1.1), ("confidence", "high"),
                                          ("probabilities", {"localized": 2})])
def test_malformed_choice_probability_or_confidence_fails_closed(tmp_path, field, value):
    payload = outbound_payload(_task(tmp_path), _graph(tmp_path))
    response = _response(payload)
    answer = response["answers"]["blast_radius"]
    answer[field] = value
    with pytest.raises(JevShadowError, match="malformed Choice"):
        from graphify.jev_shadow import _validated_response
        _validated_response(payload, response)


def test_credentials_stay_out_of_diagnostics_and_sidecar(tmp_path, monkeypatch, capsys):
    graph, task = _graph(tmp_path), _task(tmp_path)
    secret = "credential-that-must-not-leak"
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)
    monkeypatch.setattr("graphify.jev_shadow.call_typesafe", lambda *_args: (_ for _ in ()).throw(JevShadowError("request failed")))
    with pytest.raises(SystemExit):
        run(["--task", str(tmp_path / "task.json"), "--graph", str(graph)])
    assert secret not in capsys.readouterr().err
    payload = outbound_payload(task, graph)
    result = sidecar(payload, task, graph, _response(payload))
    assert secret not in json.dumps(result)


def test_live_run_writes_beside_selected_graph_and_preserves_graph(tmp_path, monkeypatch):
    graph, task = _graph(tmp_path), _task(tmp_path)
    original = graph.read_bytes()
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-key")
    monkeypatch.setattr("graphify.jev_shadow.call_typesafe", lambda payload, _key: _response(payload))
    run(["--task", str(tmp_path / "task.json"), "--graph", str(graph)])
    assert graph.read_bytes() == original
    assert (tmp_path / ".graphify_jev.json").is_file()


def test_graph_change_between_evaluation_and_write_fails_closed(tmp_path, monkeypatch):
    graph, task = _graph(tmp_path), _task(tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-key")
    def evaluate(payload, _key):
        graph.write_text(graph.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return _response(payload)
    monkeypatch.setattr("graphify.jev_shadow.call_typesafe", evaluate)
    with pytest.raises(SystemExit):
        run(["--task", str(tmp_path / "task.json"), "--graph", str(graph)])
    assert not (tmp_path / ".graphify_jev.json").exists()
