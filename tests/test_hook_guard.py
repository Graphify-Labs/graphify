"""Rigorous edge-case coverage for the `graphify hook-guard` subcommand (#522).

Covers the shell-agnostic PreToolUse/BeforeTool guard that replaced the inline
bash hooks: the search/read detection matrix, the gemini BeforeTool contract,
fail-open behavior, output-dir overrides, subcommand dispatch, exit codes, and
UTF-8 (em dash) byte fidelity. Detection is exercised by calling _run_hook_guard
directly (hermetic, fast); dispatch/exit/encoding go through a real subprocess.
"""
import io
import json
import os
import subprocess
import sys

import pytest

from graphify import __main__ as m


# --------------------------------------------------------------------------- #
# Direct-call harness: hermetic w.r.t. the ambient GRAPHIFY_OUT env.
# --------------------------------------------------------------------------- #
def _invoke(kind, payload, tmp_path, monkeypatch, *, graph=True, out_name="graphify-out"):
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT", out_name)
    monkeypatch.setattr("graphify.paths.GRAPHIFY_OUT_NAME", out_name)
    monkeypatch.chdir(tmp_path)
    if graph:
        (tmp_path / out_name).mkdir(parents=True, exist_ok=True)
        (tmp_path / out_name / "graph.json").write_text("{}", encoding="utf-8")

    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    elif payload is None:
        data = b""
    else:
        data = json.dumps(payload).encode("utf-8")

    class _Stdin:
        def __init__(self, b):
            self.buffer = io.BytesIO(b)

    monkeypatch.setattr(sys, "stdin", _Stdin(data))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    m._run_hook_guard(kind)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# search: commands that MUST nudge (mirror the old *grep*/token globs)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", [
    "grep -rn foo .",
    "pgrep -f server",          # contains 'grep'
    "egrep pattern file",       # contains 'grep'
    "fgrep lit file",           # contains 'grep'
    "ls -la | grep foo",        # piped
    "ripgrep thing",
    "rg pattern src/",
    "find . -name '*.py'",
    "fd bar",
    "ack needle",
    "ag needle",
])
def test_search_nudges(command, tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {"command": command}}, tmp_path, monkeypatch)
    assert "graphify query" in out, f"{command!r} should nudge"
    assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


# --------------------------------------------------------------------------- #
# search: commands / inputs that MUST stay silent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", [
    "",                          # empty
    "ls -la",
    "git status",
    "cat README.md",
    "python app.py",
    "cd findings && ls",         # 'find' without a trailing space is not a match
    "manage db migrate",         # 'ag' mid-word, no 'ag ' token
    "echo hello",
])
def test_search_silent(command, tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {"command": command}}, tmp_path, monkeypatch)
    assert out.strip() == "", f"{command!r} should be silent"


def test_search_silent_without_graph(tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {"command": "grep x"}}, tmp_path, monkeypatch, graph=False)
    assert out.strip() == ""


def test_search_missing_command_key(tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {}}, tmp_path, monkeypatch)
    assert out.strip() == ""


def test_search_non_string_command_is_silent(tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": {"command": 123}}, tmp_path, monkeypatch)
    assert out.strip() == ""


def test_search_top_level_command_without_tool_input(tmp_path, monkeypatch):
    # Some hosts pass the tool payload flat (no "tool_input" wrapper).
    out = _invoke("search", {"command": "grep x"}, tmp_path, monkeypatch)
    assert "graphify query" in out


def test_search_non_dict_tool_input_is_silent(tmp_path, monkeypatch):
    out = _invoke("search", {"tool_input": "grep foo"}, tmp_path, monkeypatch)
    assert out.strip() == ""


# --------------------------------------------------------------------------- #
# read: file targets that MUST nudge
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tool_input", [
    {"file_path": "src/app.py"},
    {"file_path": "pkg/mod.ts"},
    {"file_path": "src/App.vue"},
    {"file_path": "src/Hero.astro"},
    {"file_path": "src/Card.svelte"},
    {"file_path": "SRC/APP.PY"},                 # uppercase extension
    {"file_path": "src/a.test.tsx"},             # multi-dot -> .tsx
    {"file_path": "lib/foo.min.js"},             # multi-dot -> .js
    {"file_path": r"src\components\app.py"},     # windows backslashes
    {"pattern": "**/*.py", "path": "src"},       # glob pattern
    {"pattern": "**/*.astro"},
])
def test_read_nudges(tool_input, tmp_path, monkeypatch):
    out = _invoke("read", {"tool_input": tool_input}, tmp_path, monkeypatch)
    assert "graphify query" in out, f"{tool_input!r} should nudge"


# --------------------------------------------------------------------------- #
# read: targets that MUST stay silent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tool_input", [
    {"file_path": "package.json"},               # .json must not match .js
    {"file_path": "tsconfig.json"},
    {"file_path": "data.geojson"},
    {"file_path": "uv.lock"},
    {"file_path": "logo.png"},
    {"file_path": "data.bin"},
    {"file_path": ".gitignore"},
    {"file_path": "Makefile"},                   # no extension
    {"file_path": "my.ts/file"},                 # extension on a directory segment
    {"file_path": "graphify-out/GRAPH_REPORT.md"},  # the graph's own output
    {"file_path": ""},
    {},                                          # nothing at all
])
def test_read_silent(tool_input, tmp_path, monkeypatch):
    out = _invoke("read", {"tool_input": tool_input}, tmp_path, monkeypatch)
    assert out.strip() == "", f"{tool_input!r} should be silent"


def test_read_silent_without_graph(tmp_path, monkeypatch):
    out = _invoke("read", {"tool_input": {"file_path": "src/app.py"}}, tmp_path, monkeypatch, graph=False)
    assert out.strip() == ""


def test_read_non_dict_tool_input_is_silent(tmp_path, monkeypatch):
    out = _invoke("read", {"tool_input": ["src/app.py"]}, tmp_path, monkeypatch)
    assert out.strip() == ""


def test_read_respects_custom_output_dir_name(tmp_path, monkeypatch):
    # A source file living under a CUSTOM output dir name must be suppressed too,
    # not just the literal 'graphify-out/'.
    out = _invoke("read", {"tool_input": {"file_path": "build-out/report.py"}},
                  tmp_path, monkeypatch, graph=True, out_name="build-out")
    assert out.strip() == ""


def test_read_nudges_source_outside_custom_output_dir(tmp_path, monkeypatch):
    out = _invoke("read", {"tool_input": {"file_path": "src/app.py"}},
                  tmp_path, monkeypatch, graph=True, out_name="build-out")
    assert "graphify query" in out


# --------------------------------------------------------------------------- #
# fail-open: malformed / empty stdin never crashes or blocks
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", ["search", "read"])
@pytest.mark.parametrize("raw", [b"not json at all", b"", b"[1,2,3]", b"\xff\xfe\x00bad"])
def test_fail_open_on_bad_stdin(kind, raw, tmp_path, monkeypatch):
    out = _invoke(kind, raw, tmp_path, monkeypatch)
    assert out.strip() == ""


def test_search_out_path_error_is_swallowed(tmp_path, monkeypatch):
    # If the graph-existence check itself throws, the guard stays silent (never
    # blocks the tool).
    def _boom(*a, **k):
        raise OSError("boom")
    monkeypatch.setattr("graphify.paths.out_path", _boom)
    out = _invoke("search", {"tool_input": {"command": "grep x"}}, tmp_path, monkeypatch)
    assert out.strip() == ""


# --------------------------------------------------------------------------- #
# gemini: BeforeTool contract (always allow; nudge only when a graph exists)
# --------------------------------------------------------------------------- #
def test_gemini_allow_with_nudge(tmp_path, monkeypatch):
    out = _invoke("gemini", None, tmp_path, monkeypatch, graph=True)
    payload = json.loads(out)
    assert payload["decision"] == "allow"
    assert "graphify query" in payload["additionalContext"]


def test_gemini_allow_without_graph(tmp_path, monkeypatch):
    out = _invoke("gemini", None, tmp_path, monkeypatch, graph=False)
    payload = json.loads(out)
    assert payload == {"decision": "allow"}


def test_gemini_always_allows_even_when_check_throws(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise OSError("boom")
    monkeypatch.setattr("graphify.paths.out_path", _boom)
    out = _invoke("gemini", None, tmp_path, monkeypatch, graph=True)
    assert json.loads(out) == {"decision": "allow"}


# --------------------------------------------------------------------------- #
# subcommand dispatch, exit codes, and UTF-8 fidelity (real subprocess)
# --------------------------------------------------------------------------- #
def _env():
    e = dict(os.environ)
    e.pop("GRAPHIFY_OUT", None)
    return e


def _cli(args, tmp_path, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        input=stdin, capture_output=True, text=True, cwd=tmp_path, env=_env(),
    )


def test_dispatch_missing_mode_exits_zero_silent(tmp_path):
    r = _cli(["hook-guard"], tmp_path, stdin="{}")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_dispatch_unknown_mode_exits_zero_silent(tmp_path):
    r = _cli(["hook-guard", "bogus"], tmp_path, stdin="{}")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


@pytest.mark.parametrize("args,stdin", [
    (["hook-guard", "search"], '{"tool_input":{"command":"grep x"}}'),
    (["hook-guard", "read"], '{"tool_input":{"file_path":"a.py"}}'),
    (["hook-guard", "gemini"], ""),
])
def test_dispatch_always_exits_zero(args, stdin, tmp_path):
    # even with a graph present (nudge path), exit code must be 0 (never blocks)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    r = _cli(args, tmp_path, stdin=stdin)
    assert r.returncode == 0


def test_read_nudge_em_dash_survives_utf8(tmp_path):
    # The read nudge contains an em dash; the emitted bytes must be valid UTF-8
    # and parse back cleanly (guards the ensure_ascii=False + stdout reconfigure).
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "read"],
        input=b'{"tool_input":{"file_path":"src/app.py"}}',
        capture_output=True, cwd=tmp_path, env=_env(),
    )
    assert r.returncode == 0
    text = r.stdout.decode("utf-8")   # raises if not valid UTF-8
    payload = json.loads(text)
    assert "—" in payload["hookSpecificOutput"]["additionalContext"]  # em dash preserved
