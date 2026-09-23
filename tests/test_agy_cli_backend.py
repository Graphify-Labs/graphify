"""Antigravity CLI backend tests; every subprocess is mocked."""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from graphify import llm

_GRAPH = {
    "nodes": [{"id": "a", "label": "A", "rationale": "An explicit reason"}],
    "edges": [],
    "hyperedges": [],
}


@pytest.fixture(autouse=True)
def fake_agy(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_AGY_CLI_MODEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_AGY_CLI_PARALLEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_TRIAGE_BACKEND", raising=False)
    monkeypatch.delenv("GRAPHIFY_TRIAGE_MODEL", raising=False)
    completed = MagicMock(returncode=0, stderr="", stdout=json.dumps({
        "status": "SUCCESS", "structured_output": _GRAPH,
        "response": '{"nodes":[],"edges":[],"toolAction":"ignore"}',
        "usage": {"input_tokens": 15_000, "cache_read_tokens": 30,
                  "output_tokens": 390, "thinking_tokens": 347},
    }))
    with patch("shutil.which", return_value="/fake/bin/agy"), \
         patch("subprocess.run", return_value=completed) as run:
        yield run


def test_structured_output_and_usage(fake_agy):
    result = llm._call_agy_cli("source")
    assert result["nodes"] == _GRAPH["nodes"]
    assert "toolAction" not in result
    assert result["input_tokens"] == 15_030
    assert result["output_tokens"] == 390
    assert result["model"] == "gemini-3.8-flash-low"
    assert result["finish_reason"] == "stop"
    assert llm.BACKENDS["agy-cli"]["pricing"] == {"input": 0.0, "output": 0.0}


def test_response_fallback(fake_agy):
    fake_agy.return_value.stdout = json.dumps({
        "status": "SUCCESS", "response": "```json\n" + json.dumps(_GRAPH) + "\n```",
    })
    result = llm._call_agy_cli("source")
    assert result["nodes"] == _GRAPH["nodes"]
    assert result["input_tokens"] == result["output_tokens"] == 0


@pytest.mark.parametrize("plain", [False, True])
@pytest.mark.parametrize("status", ["ERROR", "UNKNOWN", None])
def test_error_status_even_on_zero_exit(fake_agy, plain, status):
    fake_agy.return_value.stdout = json.dumps({
        "status": status, "error": "INVALID_ARGUMENT (code 400)", "response": "",
    })
    with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
        if plain:
            llm._call_llm("label", backend="agy-cli")
        else:
            llm._call_agy_cli("source")


@pytest.mark.parametrize("code,detail", [(1, "invalid model selection"), (3, "missing items")])
def test_nonzero_exit(fake_agy, code, detail):
    fake_agy.return_value.returncode = code
    fake_agy.return_value.stdout = ""
    fake_agy.return_value.stderr = detail
    with pytest.raises(RuntimeError, match=f"exited {code}: {detail}"):
        llm._call_agy_cli("source")


def test_nonzero_exit_with_error_envelope(fake_agy):
    fake_agy.return_value.returncode = 1
    fake_agy.return_value.stdout = json.dumps({"status": "ERROR", "error": "auth failed"})
    with pytest.raises(RuntimeError, match="exited 1:.*auth failed"):
        llm._call_agy_cli("source")


@pytest.mark.parametrize("plain", [False, True])
def test_missing_binary(fake_agy, plain):
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Antigravity CLI not found"):
            if plain:
                llm._call_llm("label", backend="agy-cli")
            else:
                llm._call_agy_cli("source")
    fake_agy.assert_not_called()


@pytest.mark.parametrize("stdout", ["not json", "[]", "null"])
def test_invalid_envelope(fake_agy, stdout):
    fake_agy.return_value.stdout = stdout
    with pytest.raises(RuntimeError, match="envelope"):
        llm._call_agy_cli("source")


def test_prompt_schema_and_timeout(fake_agy, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_API_TIMEOUT", "42")
    source = "quotes ' \" and unicode á\n--model=untrusted"
    llm._call_agy_cli(source, deep_mode=True)
    args = fake_agy.call_args.args[0]
    prompts = [arg for arg in args if arg.startswith("-p=")]
    assert len(prompts) == 1
    assert source in prompts[0]
    assert llm._extraction_system(deep=True) in prompts[0]
    assert "-p" not in args and "--system-prompt" not in args
    assert "--dangerously-skip-permissions" in args
    assert fake_agy.call_args.kwargs.get("shell", False) is False
    assert fake_agy.call_args.kwargs["stdin"] == subprocess.DEVNULL
    assert fake_agy.call_args.kwargs["timeout"] == 42.0
    schema = json.loads(args[args.index("--json-schema") + 1])

    def check_arrays(value):
        if isinstance(value, dict):
            if value.get("type") == "array":
                assert isinstance(value.get("items"), dict)
            for child in value.values():
                check_arrays(child)
        elif isinstance(value, list):
            for child in value:
                check_arrays(child)

    check_arrays(schema)
    assert schema["required"] == ["nodes", "edges"]
    props = schema["properties"]
    assert props["nodes"]["items"]["required"] == ["id", "label"]
    assert props["edges"]["items"]["required"] == ["source", "target", "relation"]
    assert props["hyperedges"]["items"]["properties"]["nodes"]["items"] == {"type": "string"}


@pytest.mark.parametrize("explicit", [None, "gemini-3.1-pro-low"])
def test_model_override_for_both_dispatches(fake_agy, monkeypatch, tmp_path, explicit):
    monkeypatch.setenv("GRAPHIFY_AGY_CLI_MODEL", " gemini-3.7-flash-low ")
    source = tmp_path / "a.md"
    source.write_text("A")
    expected = explicit or "gemini-3.7-flash-low"
    llm.extract_files_direct([source], backend="agy-cli", root=tmp_path, model=explicit)
    args = fake_agy.call_args.args[0]
    assert args[args.index("--model") + 1] == expected
    fake_agy.return_value.stdout = json.dumps({"status": "SUCCESS", "response": "label"})
    assert llm._call_llm("name", backend="agy-cli", model=explicit) == "label"
    args = fake_agy.call_args.args[0]
    assert args[args.index("--model") + 1] == expected


def test_images_are_paths_with_unique_directories(fake_agy, tmp_path):
    images = [tmp_path / name for name in ("a.png", "b.png")]
    for path in images:
        path.write_bytes(b"image")
    with patch.object(llm, "_build_image_refs", wraps=llm._build_image_refs) as refs:
        llm.extract_files_direct(images, backend="agy-cli", root=tmp_path)
    assert refs.call_args.kwargs["read_bytes"] is False
    args = fake_agy.call_args.args[0]
    assert args.count("--add-dir") == 1
    assert args[args.index("--add-dir") + 1] == str(tmp_path)
    prompt = next(arg for arg in args if arg.startswith("-p="))
    assert all(str(path) in prompt for path in images)


@pytest.mark.parametrize("parallel", [False, True])
def test_extraction_parallel_guard(fake_agy, monkeypatch, tmp_path, parallel):
    if parallel:
        monkeypatch.setenv("GRAPHIFY_AGY_CLI_PARALLEL", "1")
    files = [tmp_path / f"f{i}.md" for i in range(3)]
    for path in files:
        path.write_text("A")
    with patch.object(llm, "ThreadPoolExecutor", wraps=ThreadPoolExecutor) as pool:
        result = llm.extract_corpus_parallel(
            files, backend="agy-cli", root=tmp_path, chunk_size=1,
            token_budget=None, max_concurrency=3,
        )
    assert result["failed_chunks"] == 0
    assert fake_agy.call_count == 3
    assert pool.called is parallel


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("structured", [False, True])
def test_labeling_dispatch_usage_and_parallel_guard(fake_agy, monkeypatch, parallel, structured):
    if parallel:
        monkeypatch.setenv("GRAPHIFY_AGY_CLI_PARALLEL", "1")
    envelope = json.loads(fake_agy.return_value.stdout)
    envelope.pop("structured_output")
    envelope["response"] = json.dumps({"0": "Alpha", "1": "Beta"})
    if structured:
        envelope["structured_output"] = {"0": "Alpha", "1": "Beta"}
        envelope["response"] = "Labels generated"
    fake_agy.return_value.stdout = json.dumps(envelope)
    graph = nx.Graph()
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    usage = {}
    with patch.object(llm, "ThreadPoolExecutor", wraps=ThreadPoolExecutor) as pool:
        labels = llm.label_communities(
            graph, {0: ["a"], 1: ["b"]}, backend="agy-cli", batch_size=1, usage_out=usage,
        )
    assert labels == {0: "Alpha", 1: "Beta"}
    assert usage == {"input": 30_060, "output": 780}
    assert pool.called is parallel
    assert "--json-schema" not in fake_agy.call_args.args[0]
    assert "semantic extraction agent" not in fake_agy.call_args.args[0][1]


@pytest.mark.parametrize("available", [False, True])
def test_extract_cli_validates_agy_on_path(fake_agy, monkeypatch, tmp_path, capsys, available):
    import graphify.__main__ as mainmod

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "notes.md").write_text("# Notes\nA documented concept.\n")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "extract", str(corpus), "--backend", "agy-cli",
        "--out", str(tmp_path / "out"),
    ])
    # Stop at the semantic extraction boundary after real CLI validation.
    with patch("shutil.which", return_value="/fake/bin/agy" if available else None) as which, \
         patch.object(llm, "extract_corpus_parallel", side_effect=SystemExit(0)) as extract:
        with pytest.raises(SystemExit) as exc:
            mainmod.main()
    assert exc.value.code == (0 if available else 1)
    which.assert_any_call("agy")
    stderr = capsys.readouterr().err
    assert "AWS_PROFILE" not in stderr
    assert "AWS_REGION" not in stderr
    if available:
        extract.assert_called_once()
        assert extract.call_args.kwargs["backend"] == "agy-cli"
    else:
        extract.assert_not_called()
        assert "backend 'agy-cli' requires the `agy` CLI on $PATH" in stderr
    fake_agy.assert_not_called()


@pytest.mark.parametrize("available", [False, True])
def test_label_falls_back_to_agy(monkeypatch, available):
    monkeypatch.setattr(llm, "detect_backend", lambda: None)
    monkeypatch.setattr(llm, "_claude_cli_available", lambda: False)
    graph = nx.Graph()
    graph.add_node("a", label="A")
    with patch("shutil.which", return_value="/fake/bin/agy" if available else None), \
         patch.object(llm, "label_communities", return_value={0: "Alpha"}) as label:
        labels, source = llm.generate_community_labels(graph, {0: ["a"]}, quiet=True)
    assert source == ("llm" if available else "placeholder")
    assert labels == {0: "Alpha" if available else "Community 0"}
    if available:
        assert label.call_args.kwargs["backend"] == "agy-cli"
    else:
        label.assert_not_called()


def test_triage_falls_back_to_agy():
    from graphify.prs import _resolve_triage_backend

    with patch("shutil.which", side_effect=lambda name: "/fake/bin/agy" if name == "agy" else None):
        assert _resolve_triage_backend() == ("agy-cli", llm._default_model_for_backend("agy-cli"))


def test_triage_dispatches_explicit_agy(monkeypatch, capsys):
    from graphify.prs import triage_with_opus

    monkeypatch.setenv("GRAPHIFY_TRIAGE_BACKEND", "agy-cli")
    monkeypatch.setenv("GRAPHIFY_TRIAGE_MODEL", "gemini-3.1-pro-low")
    pr = MagicMock(base_branch="v8", status="READY")
    with patch.object(llm, "_call_llm", return_value="#1 — Review this PR.") as call:
        triage_with_opus([pr], "v8")
    assert call.call_args.kwargs == {
        "backend": "agy-cli", "model": "gemini-3.1-pro-low", "max_tokens": 1024,
    }
    assert "#1 — Review this PR." in capsys.readouterr().out
