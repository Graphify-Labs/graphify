"""Tests for `graphify watch --semantic` - automatic LLM extraction on doc changes.

The extract subprocess is always mocked: no test here may reach a real
backend. CLI arg-validation tests drive `python -m graphify watch` as a
subprocess but only down paths that exit before the watcher starts.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.watch import _run_semantic_extract, _GRAPHIFY_OUT

PYTHON = sys.executable
REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeCompleted:
    def __init__(self, rc: int):
        self.returncode = rc


def _patch_run(monkeypatch, rc: int, calls: list):
    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _FakeCompleted(rc)
    monkeypatch.setattr(subprocess, "run", fake_run)


# --- _run_semantic_extract: subprocess command shape ---

def test_semantic_extract_invokes_module_cli(tmp_path, monkeypatch):
    calls: list = []
    _patch_run(monkeypatch, 0, calls)
    assert _run_semantic_extract(tmp_path) is True
    assert calls == [[PYTHON, "-m", "graphify", "extract", str(tmp_path)]]

def test_semantic_extract_forwards_backend_flags(tmp_path, monkeypatch):
    calls: list = []
    _patch_run(monkeypatch, 0, calls)
    _run_semantic_extract(tmp_path, backend="gemini", fallback_backend="ollama")
    assert calls[0] == [
        PYTHON, "-m", "graphify", "extract", str(tmp_path),
        "--backend", "gemini", "--fallback-backend", "ollama",
    ]

def test_semantic_extract_omits_unset_backend_flags(tmp_path, monkeypatch):
    # An unset backend must not appear as `--backend None` in the child argv.
    calls: list = []
    _patch_run(monkeypatch, 0, calls)
    _run_semantic_extract(tmp_path)
    assert "--backend" not in calls[0]
    assert "--fallback-backend" not in calls[0]


# --- _run_semantic_extract: needs_update flag contract ---

def test_semantic_extract_clears_stale_flag_on_success(tmp_path, monkeypatch):
    """Extract never touches the flag itself (only _rebuild_code does), so a
    successful semantic run must clear it here or the user is left with a
    stale 'run /graphify --update' prompt."""
    flag = tmp_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True)
    flag.write_text("1", encoding="utf-8")
    _patch_run(monkeypatch, 0, [])
    assert _run_semantic_extract(tmp_path) is True
    assert not flag.exists()

def test_semantic_extract_failure_keeps_flag(tmp_path, monkeypatch, capsys):
    """A failed extract must leave the flag alone and return False so the
    watcher falls back to _notify_only - never swallow the failure."""
    flag = tmp_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True)
    flag.write_text("1", encoding="utf-8")
    _patch_run(monkeypatch, 1, [])
    assert _run_semantic_extract(tmp_path) is False
    assert flag.exists()
    assert "exited with code 1" in capsys.readouterr().out

def test_semantic_extract_success_without_flag_is_fine(tmp_path, monkeypatch):
    # No pre-existing flag (the common case: the batch never wrote one).
    _patch_run(monkeypatch, 0, [])
    assert _run_semantic_extract(tmp_path) is True

def test_semantic_extract_oserror_returns_false(tmp_path, monkeypatch, capsys):
    def boom(cmd, *args, **kwargs):
        raise OSError("no such interpreter")
    monkeypatch.setattr(subprocess, "run", boom)
    assert _run_semantic_extract(tmp_path) is False
    assert "failed to start" in capsys.readouterr().out


# --- watch() signature: semantic knobs are keyword-only ---

def test_watch_semantic_params_are_keyword_only():
    import inspect
    from graphify.watch import watch
    params = inspect.signature(watch).parameters
    for name in ("semantic", "backend", "fallback_backend"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


# --- CLI arg validation (exits before the watcher starts; no watchdog needed) ---

def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    # Pin PYTHONPATH to this checkout so the subprocess exercises the code
    # under test even when a different graphify is installed site-wide.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "watch"] + args,
        cwd=cwd, capture_output=True, text=True, timeout=60, env=env,
    )

def test_cli_watch_backend_without_semantic_rejected(tmp_path):
    """Without --semantic no extract ever runs, so a backend flag would be a
    silent no-op - it must be rejected loudly."""
    r = _run_cli(["--backend", "gemini"], tmp_path)
    assert r.returncode == 2
    assert "--semantic" in r.stderr

def test_cli_watch_fallback_backend_without_semantic_rejected(tmp_path):
    r = _run_cli(["--fallback-backend=ollama"], tmp_path)
    assert r.returncode == 2
    assert "--semantic" in r.stderr

def test_cli_watch_unknown_option_rejected(tmp_path):
    r = _run_cli(["--sematnic"], tmp_path)
    assert r.returncode == 2
    assert "unknown watch option" in r.stderr

def test_cli_watch_two_paths_rejected(tmp_path):
    r = _run_cli([str(tmp_path), str(tmp_path)], tmp_path)
    assert r.returncode == 2
    assert "at most one path" in r.stderr

def test_cli_watch_semantic_missing_path_errors(tmp_path):
    # Flag parsing must leave the positional path intact.
    r = _run_cli(["--semantic", "no-such-dir"], tmp_path)
    assert r.returncode == 1
    assert "path not found" in r.stderr
