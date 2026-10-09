"""Tests for the `cursor-cli` backend.

Mocks subprocess.run + shutil.which so the suite runs on CI without
the `cursor-agent` binary or a live network call.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from graphify import llm

_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": json.dumps({
        "nodes": [
            {"id": "foo_module", "label": "Foo", "file_type": "document", "source_file": "foo.md"},
            {"id": "foo_greet", "label": "greet", "file_type": "code", "source_file": "foo.md"},
        ],
        "edges": [
            {"source": "foo_module", "target": "foo_greet",
             "relation": "references", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }),
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 6,
        "output_tokens": 11,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "modelUsage": {"composer-2.5": {"inputTokens": 6, "outputTokens": 11}},
}


@pytest.fixture
def fake_cursor(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        if name in ("cursor-agent", "cursor-agent.cmd"):
            return "/fake/bin/cursor-agent"
        return None

    with patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed) as run:
        yield run


def test_backend_registered_with_zero_cost():
    assert "cursor-cli" in llm.BACKENDS
    pricing = llm.BACKENDS["cursor-cli"]["pricing"]
    assert pricing["input"] == 0.0
    assert pricing["output"] == 0.0
    assert llm.estimate_cost("cursor-cli", 1_000_000, 1_000_000) == 0.0


def test_returns_parsed_nodes_and_edges(fake_cursor):
    result = llm._call_cursor_cli("dummy", max_tokens=8192)
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1


def test_token_accounting(fake_cursor):
    result = llm._call_cursor_cli("dummy", max_tokens=8192)
    assert result["input_tokens"] == 6
    assert result["output_tokens"] == 11
    assert result["model"] == "composer-2.5"
    assert result["finish_reason"] == "stop"


def test_raises_when_cli_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Cursor Agent CLI was not found"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_never_resolves_editor_cursor_binary(monkeypatch):
    """The editor `cursor` binary must never be used as the Agent CLI."""
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        if name == "cursor":
            return "/fake/bin/cursor"
        return None

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Cursor Agent CLI was not found"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_prefers_cursor_agent_over_agent_symlink(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        return {
            "cursor-agent": "/fake/bin/cursor-agent",
            "agent": "/fake/bin/agent",
        }.get(name)

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_cursor_cli("dummy", max_tokens=8192)

    assert run.call_args.args[0][0] == "cursor-agent"


def test_falls_back_to_agent_when_cursor_agent_missing(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        return "/fake/bin/agent" if name == "agent" else None

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_cursor_cli("dummy", max_tokens=8192)

    assert run.call_args.args[0][0] == "agent"


def test_argv_shape_includes_print_json_ask_isolated_workspace(fake_cursor, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_CURSOR_CLI_TRUST", raising=False)
    llm._call_cursor_cli("dummy", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert "-p" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--mode") + 1] == "ask"
    assert "--workspace" in argv
    workspace = argv[argv.index("--workspace") + 1]
    assert "graphify-cursor-" in workspace
    assert "--trust" not in argv  # opt-in only
    assert "--force" not in argv
    assert "--yolo" not in argv


def test_trust_flag_opt_in_via_env(fake_cursor, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_CURSOR_CLI_TRUST", "1")
    llm._call_cursor_cli("dummy", max_tokens=8192)
    assert "--trust" in fake_cursor.call_args.args[0]


def test_model_flag_from_argument(fake_cursor):
    llm._call_cursor_cli("dummy", max_tokens=8192, model="composer-2.5")
    argv = fake_cursor.call_args.args[0]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "composer-2.5"


def test_model_flag_from_env(monkeypatch, fake_cursor):
    monkeypatch.setenv("GRAPHIFY_CURSOR_CLI_MODEL", "auto")
    llm._call_cursor_cli("dummy", max_tokens=8192)
    argv = fake_cursor.call_args.args[0]
    assert argv[argv.index("--model") + 1] == "auto"


def test_no_model_flag_when_unset(monkeypatch, fake_cursor):
    monkeypatch.delenv("GRAPHIFY_CURSOR_CLI_MODEL", raising=False)
    llm._call_cursor_cli("dummy", max_tokens=8192)
    assert "--model" not in fake_cursor.call_args.args[0]


def test_prompt_delivered_via_stdin(fake_cursor):
    marker = "UNIQUE_CURSOR_PROMPT_MARKER\nline2"
    llm._call_cursor_cli(marker, max_tokens=8192)
    sent = fake_cursor.call_args.kwargs["input"]
    assert "UNIQUE_CURSOR_PROMPT_MARKER" in sent
    assert "line2" in sent
    assert "output ONLY the JSON object" in sent
    assert "graphify semantic extraction agent" in sent


def test_raises_on_nonzero_exit():
    completed = MagicMock(returncode=2, stdout="", stderr="something broke")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="exited 2"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_auth_failure_gives_actionable_hint():
    completed = MagicMock(
        returncode=1,
        stdout="",
        stderr="Error: not authenticated. Please run cursor-agent login",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="cursor-agent login"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_permission_denied_gives_auth_hint():
    completed = MagicMock(
        returncode=1,
        stdout="",
        stderr="NonRetriableError: [permission_denied] Cursor is not available in your region.",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="not authenticated|denied"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


_ERROR_ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "result": "API Error: Rate limit reached",
    "usage": {"input_tokens": 0, "output_tokens": 0},
    "modelUsage": {},
}


def test_raises_on_error_envelope_with_zero_exit():
    completed = MagicMock(
        returncode=0, stdout=json.dumps(_ERROR_ENVELOPE), stderr="",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Rate limit reached"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_raises_on_empty_stdout():
    completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="empty response"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


_MCP_PREAMBLE = (
    "Client.listTools() called but server does not advertise tools capability "
    "- returning empty list\n"
)


def test_envelope_survives_diagnostic_preamble(monkeypatch):
    completed = MagicMock(
        returncode=0, stdout=_MCP_PREAMBLE + json.dumps(_ENVELOPE), stderr=""
    )
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        result = llm._call_cursor_cli("dummy", max_tokens=8192)
    assert [n["label"] for n in result["nodes"]] == ["Foo", "greet"]


def test_raises_on_garbage_envelope():
    completed = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="unparseable JSON envelope"):
            llm._call_cursor_cli("dummy", max_tokens=8192)


def test_call_llm_success_returns_result_text(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_CURSOR_CLI_TRUST", raising=False)
    envelope = dict(_ENVELOPE, result='{"0": "Authentication"}')
    completed = MagicMock(returncode=0, stdout=json.dumps(envelope), stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed) as run:
        out = llm._call_llm("label these", backend="cursor-cli", model="auto")
    assert out == '{"0": "Authentication"}'
    argv = run.call_args.args[0]
    assert "-p" in argv
    assert "--mode" in argv and argv[argv.index("--mode") + 1] == "ask"
    assert "--workspace" in argv
    assert "--trust" not in argv
    assert argv[argv.index("--model") + 1] == "auto"
    assert run.call_args.kwargs["input"] == "label these"


def test_call_llm_raises_on_error_envelope():
    completed = MagicMock(
        returncode=0, stdout=json.dumps(_ERROR_ENVELOPE), stderr="",
    )
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="Rate limit reached"):
            llm._call_llm("dummy", backend="cursor-cli")


def test_call_llm_empty_response():
    completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="empty response"):
            llm._call_llm("dummy", backend="cursor-cli")


def test_call_llm_multiline_prompt_integrity():
    prompt = "line1\nline2\n{\"batch\": true}\nfinal"
    envelope = dict(_ENVELOPE, result='{"0": "Auth"}')
    completed = MagicMock(returncode=0, stdout=json.dumps(envelope), stderr="")
    with patch("shutil.which", return_value="/fake/bin/cursor-agent"), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_llm(prompt, backend="cursor-cli")
    assert run.call_args.kwargs["input"] == prompt


def test_extract_files_direct_dispatches_to_cursor_cli(tmp_path, fake_cursor):
    f = tmp_path / "foo.md"
    f.write_text("# Foo\n\nThe greet() helper formats a name.\n")
    result = llm.extract_files_direct(files=[f], backend="cursor-cli", root=tmp_path)
    assert fake_cursor.called
    assert len(result["nodes"]) == 2


def test_cursor_cli_honours_timeout(monkeypatch, fake_cursor):
    monkeypatch.setenv("GRAPHIFY_API_TIMEOUT", "30")
    llm._call_cursor_cli("dummy", max_tokens=8192)
    assert fake_cursor.call_args.kwargs["timeout"] == 30.0


def test_call_llm_cursor_cli_honours_timeout(monkeypatch, fake_cursor):
    monkeypatch.setenv("GRAPHIFY_API_TIMEOUT", "30")
    llm._call_llm(prompt="x", backend="cursor-cli", max_tokens=10)
    assert fake_cursor.call_args.kwargs["timeout"] == 30.0


def test_windows_prefers_cursor_agent_cmd(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        return {
            "cursor-agent.cmd": r"C:\Users\u\AppData\Local\cursor-agent.cmd",
            "cursor-agent": r"C:\Users\u\AppData\Local\cursor-agent.ps1",
            "agent.cmd": r"C:\Users\u\AppData\Local\agent.cmd",
        }.get(name)

    with patch("platform.system", return_value="Windows"), \
         patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_cursor_cli("dummy", max_tokens=8192)

    assert run.call_args.args[0][0] == r"C:\Users\u\AppData\Local\cursor-agent.cmd"


def test_windows_falls_back_to_agent_cmd(monkeypatch):
    completed = MagicMock(returncode=0, stdout=json.dumps(_ENVELOPE), stderr="")
    monkeypatch.setattr(llm, "_response_is_hollow", lambda raw, parsed: False)

    def fake_which(name):
        return {
            "agent.cmd": r"C:\Users\u\AppData\Local\agent.cmd",
        }.get(name)

    with patch("platform.system", return_value="Windows"), \
         patch("shutil.which", side_effect=fake_which), \
         patch("subprocess.run", return_value=completed) as run:
        llm._call_cursor_cli("dummy", max_tokens=8192)

    assert run.call_args.args[0][0] == r"C:\Users\u\AppData\Local\agent.cmd"


def test_label_communities_forces_serial_for_cursor_cli(monkeypatch):
    import networkx as nx
    from graphify.llm import label_communities

    G = nx.Graph()
    communities = {}
    for i in range(8):
        nid = f"n{i}"
        G.add_node(nid, label=f"Node {i}", community=i)
        communities[i] = [nid]

    state = {"peak": 0, "current": 0}
    import threading
    lock = threading.Lock()

    def fake_batch(batch_cids, batch_lines, *, backend, model=None, depth=0, max_depth=3, usage_out=None):
        with lock:
            state["current"] += 1
            state["peak"] = max(state["peak"], state["current"])
        import time
        time.sleep(0.02)
        with lock:
            state["current"] -= 1
        return {cid: f"Name {cid}" for cid in batch_cids}

    monkeypatch.setattr("graphify.llm._label_batch_with_retry", fake_batch)
    monkeypatch.delenv("GRAPHIFY_CURSOR_CLI_PARALLEL", raising=False)
    label_communities(G, communities, backend="cursor-cli", batch_size=1, max_concurrency=8)
    assert state["peak"] == 1, "cursor-cli must be forced serial"


def test_cursor_cli_available_true_when_on_path():
    with patch("shutil.which", side_effect=lambda n: "/x" if n == "cursor-agent" else None):
        assert llm._cursor_cli_available() is True


def test_cursor_cli_available_false_when_missing():
    with patch("shutil.which", return_value=None):
        assert llm._cursor_cli_available() is False


def test_no_shell_true(fake_cursor):
    llm._call_cursor_cli("dummy", max_tokens=8192)
    assert fake_cursor.call_args.kwargs.get("shell") in (None, False)


def test_subprocess_uses_utf8_and_replace(fake_cursor):
    llm._call_cursor_cli("dummy", max_tokens=8192)
    assert fake_cursor.call_args.kwargs["encoding"] == "utf-8"
    assert fake_cursor.call_args.kwargs["errors"] == "replace"
