"""Tests for the openai-cli backend (_call_openai_cli).

Covers the argv contract, the happy JSON parse, the failure paths (non-zero
exit, missing/empty -o output, hollow graph), and turn-usage accounting.
No network, no Codex binary: shutil.which and subprocess.run are monkeypatched.
"""
import json

import pytest

from graphify import llm


class _Captured:
    def __init__(self):
        self.args = None
        self.kwargs = None
        self.calls = []


def _arm(monkeypatch, response=None, servers=("graphify", "docs"),
         exec_returncode=0, exec_stdout="", exec_stderr="", write_output=True):
    """Fake a Codex CLI: `mcp list --json` returns servers, `exec` writes the -o file."""
    cap = _Captured()
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)

    class P:
        def __init__(self, stdout="", returncode=0, stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args, **kwargs):
        cap.calls.append(list(args))
        if "mcp" in args and "list" in args:
            return P(json.dumps([{"name": n, "enabled": True} for n in servers]))
        cap.args = list(args)
        cap.kwargs = kwargs
        # write the -o file the way codex exec does
        out_idx = args.index("-o") + 1
        if write_output:
            payload = response if response is not None else {"nodes": [{"id": "f", "type": "function"}], "edges": []}
            if isinstance(payload, str):
                with open(args[out_idx], "w", encoding="utf-8") as fh:
                    fh.write(payload)
            else:
                with open(args[out_idx], "w", encoding="utf-8") as fh:
                    json.dump(payload, fh)
        else:
            # simulate codex never producing the file (the backend pre-creates
            # the temp path, so "missing" means it is gone by the time we look)
            import os as _os
            try:
                _os.unlink(args[out_idx])
            except OSError:
                pass
        return P(stdout=exec_stdout, returncode=exec_returncode, stderr=exec_stderr)

    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", fake_run)
    return cap


def test_argv_contract_defaults(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OPENAI_CLI_MODEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_OPENAI_CLI_EFFORT", raising=False)
    cap = _arm(monkeypatch)
    llm._call_openai_cli("def f(): pass", max_tokens=64)
    a = cap.args
    assert a[0] == "/usr/bin/codex" and a[1] == "exec"
    assert "--skip-git-repo-check" in a and "--json" in a
    assert a[a.index("--sandbox") + 1] == "read-only"
    assert a[a.index("--model") + 1] == "gpt-5.6-sol"          # default model
    assert "model_reasoning_effort=ultra" in a                  # default effort
    assert a[-1] == "-"                                         # prompt via stdin
    assert cap.kwargs.get("input")                              # not argv (MAX_ARG_STRLEN)


def test_every_configured_mcp_server_is_disabled_per_call(monkeypatch):
    """A blanket `mcp_servers={}` is merged away by Codex; per-server `enabled` works."""
    cap = _arm(monkeypatch, servers=("graphify", "docs"))
    llm._call_openai_cli("def f(): pass", max_tokens=64)
    a = cap.args
    assert "mcp_servers.graphify.enabled=false" in a
    assert "mcp_servers.docs.enabled=false" in a
    assert "mcp_servers={}" not in a
    # the server list came from Codex itself, no hardcoded names
    assert any("mcp" in c and "list" in c and "--json" in c for c in cap.calls)


def test_no_configured_servers_adds_no_overrides(monkeypatch):
    cap = _arm(monkeypatch, servers=())
    llm._call_openai_cli("def f(): pass", max_tokens=64)
    assert not [x for x in cap.args if str(x).startswith("mcp_servers.")]


def test_argv_env_overrides(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OPENAI_CLI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("GRAPHIFY_OPENAI_CLI_EFFORT", "high")
    cap = _arm(monkeypatch)
    llm._call_openai_cli("def f(): pass", max_tokens=64)
    a = cap.args
    assert a[a.index("--model") + 1] == "gpt-5.6-luna"
    assert "model_reasoning_effort=high" in a
    assert "model_reasoning_effort=ultra" not in a


def test_missing_binary_raises(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Codex CLI not found"):
        llm._call_openai_cli("x", max_tokens=16)


# ---------------------------------------------------------------------------
# Happy path: the -o JSON becomes the result dict, usage rides the JSONL stdout
# ---------------------------------------------------------------------------

def test_happy_parse_returns_graph_and_usage(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OPENAI_CLI_MODEL", raising=False)
    stdout = "\n".join([
        json.dumps({"type": "turn.started"}),
        "not-json diagnostics line",
        json.dumps({"type": "turn.completed",
                    "usage": {"input_tokens": 1200, "cached_input_tokens": 1000,
                              "output_tokens": 345}}),
    ])
    payload = {"nodes": [{"id": "acme.f", "type": "function"}],
               "edges": [{"source": "acme.f", "target": "acme.g", "relation": "calls"}]}
    _arm(monkeypatch, response=payload, exec_stdout=stdout)
    result = llm._call_openai_cli("def f(): g()", max_tokens=64)
    assert result["nodes"] == payload["nodes"]
    assert result["edges"] == payload["edges"]
    # input_tokens already includes cached_input_tokens; must not be re-added
    assert result["input_tokens"] == 1200
    assert result["output_tokens"] == 345
    assert result["model"] == "gpt-5.6-sol"
    assert result["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# Failure paths: every raise carries the vendor detail (stderr + stdout tail)
# ---------------------------------------------------------------------------

def test_nonzero_exit_raises_with_vendor_detail(monkeypatch):
    _arm(monkeypatch, exec_returncode=2,
         exec_stderr="ERROR: 400 Bad Request: model not found",
         exec_stdout=json.dumps({"type": "error", "message": "http 400"}))
    with pytest.raises(RuntimeError) as exc:
        llm._call_openai_cli("x", max_tokens=16)
    msg = str(exc.value)
    assert "codex exec exited 2" in msg
    assert "400 Bad Request" in msg           # stderr preserved
    assert "http 400" in msg                  # JSONL stdout tail preserved


def test_missing_output_file_raises(monkeypatch):
    _arm(monkeypatch, write_output=False, exec_stderr="boom")
    with pytest.raises(RuntimeError, match="produced no -o output file"):
        llm._call_openai_cli("x", max_tokens=16)


def test_empty_output_file_raises(monkeypatch):
    _arm(monkeypatch, response="   \n", exec_stderr="quota hint on stderr")
    with pytest.raises(RuntimeError) as exc:
        llm._call_openai_cli("x", max_tokens=16)
    msg = str(exc.value)
    assert "empty -o output file" in msg
    assert "quota hint on stderr" in msg


def test_empty_graph_raises_instead_of_hollow_bisect(monkeypatch):
    # An empty-but-valid graph must raise, or _response_is_hollow would bisect
    # the chunk into up to 15 more subscription calls.
    _arm(monkeypatch, response={"nodes": [], "edges": []})
    with pytest.raises(RuntimeError, match="returned no graph content"):
        llm._call_openai_cli("x", max_tokens=16)


# ---------------------------------------------------------------------------
# _openai_cli_turn_usage: JSONL accounting
# ---------------------------------------------------------------------------

def test_turn_usage_reads_last_completed_event():
    stdout = "\n".join([
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 30, "output_tokens": 40}}),
    ])
    assert llm._openai_cli_turn_usage(stdout) == (30, 40)


def test_turn_usage_tolerates_malformed_lines():
    stdout = "\n".join([
        "plain diagnostics",
        "{not json",
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 8}}),
    ])
    assert llm._openai_cli_turn_usage(stdout) == (7, 8)


def test_turn_usage_without_completed_event_reports_zero():
    assert llm._openai_cli_turn_usage("") == (0, 0)
    assert llm._openai_cli_turn_usage(json.dumps({"type": "turn.started"})) == (0, 0)


def test_turn_usage_non_numeric_counts_are_zero():
    stdout = json.dumps({"type": "turn.completed",
                         "usage": {"input_tokens": "many", "output_tokens": None}})
    assert llm._openai_cli_turn_usage(stdout) == (0, 0)


def test_vendor_detail_bounds_and_labels():
    detail = llm._openai_cli_vendor_detail("E" * 1000, "O" * 1000)
    assert detail.startswith("stderr: ")
    assert "stdout tail: " in detail
    # both sides bounded to their last 400 chars
    assert len(detail) < 900
    assert llm._openai_cli_vendor_detail("", "") == "(no stderr or stdout)"
