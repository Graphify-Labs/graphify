"""claude-cli error surfacing when the CLI reports failures on stdout."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from graphify import llm as llmmod


def _proc(returncode=1, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_claude_cli_error_prefers_stderr(monkeypatch):
    import shutil as _shutil
    import subprocess as _subprocess

    monkeypatch.setattr(_shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        _subprocess, "run", lambda *a, **k: _proc(stderr="real stderr", stdout="noise")
    )
    with pytest.raises(RuntimeError, match="real stderr"):
        llmmod._call_claude_cli("hi")


def test_claude_cli_error_falls_back_to_stdout(monkeypatch):
    import shutil as _shutil
    import subprocess as _subprocess

    monkeypatch.setattr(_shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        _subprocess,
        "run",
        lambda *a, **k: _proc(
            stdout='{"type":"result","result":"Claude AI usage limit reached|1752200000"}'
        ),
    )
    with pytest.raises(RuntimeError, match="usage limit reached"):
        llmmod._call_claude_cli("hi")
