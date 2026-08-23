"""Tests for the openai-cli backend (_call_openai_cli): argv contract only.

No network, no Codex binary: shutil.which and subprocess.run are monkeypatched.
"""
import json

import pytest

from graphify import llm


class _Captured:
    def __init__(self):
        self.args = None
        self.kwargs = None


def _arm(monkeypatch, tmp_path, response=None):
    cap = _Captured()
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)

    def fake_run(args, **kwargs):
        cap.args = args
        cap.kwargs = kwargs
        # write the -o file the way codex exec does
        out_idx = args.index("-o") + 1
        payload = response if response is not None else {"nodes": [{"id": "f", "type": "function"}], "edges": []}
        with open(args[out_idx], "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", fake_run)
    return cap


def test_argv_contract_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHIFY_OPENAI_CLI_MODEL", raising=False)
    monkeypatch.delenv("GRAPHIFY_OPENAI_CLI_EFFORT", raising=False)
    cap = _arm(monkeypatch, tmp_path)
    llm._call_openai_cli("def f(): pass", max_tokens=64)
    a = cap.args
    assert a[0] == "/usr/bin/codex" and a[1] == "exec"
    assert "--skip-git-repo-check" in a and "--json" in a
    assert a[a.index("--sandbox") + 1] == "read-only"
    assert a[a.index("--model") + 1] == "gpt-5.6-sol"          # default model
    assert "mcp_servers={}" in a                                # no MCP spawn per call
    assert "model_reasoning_effort=ultra" in a                  # default effort
    assert a[-1] == "-"                                         # prompt via stdin
    assert cap.kwargs.get("input")                              # not argv (MAX_ARG_STRLEN)


def test_argv_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHIFY_OPENAI_CLI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("GRAPHIFY_OPENAI_CLI_EFFORT", "high")
    cap = _arm(monkeypatch, tmp_path)
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
