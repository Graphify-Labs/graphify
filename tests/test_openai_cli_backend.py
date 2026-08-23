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
        self.calls = []


def _arm(monkeypatch, response=None, servers=("graphify", "docs")):
    """Fake a Codex CLI: `mcp list --json` returns servers, `exec` writes the -o file."""
    cap = _Captured()
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)

    class P:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, **kwargs):
        cap.calls.append(list(args))
        if "mcp" in args and "list" in args:
            return P(json.dumps([{"name": n, "enabled": True} for n in servers]))
        cap.args = list(args)
        cap.kwargs = kwargs
        # write the -o file the way codex exec does
        out_idx = args.index("-o") + 1
        payload = response if response is not None else {"nodes": [{"id": "f", "type": "function"}], "edges": []}
        with open(args[out_idx], "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return P()

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
