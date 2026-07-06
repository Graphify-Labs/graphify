"""The Read|Glob PreToolUse guard nudges toward the graph instead of raw reads.

Closes the issue #1114 gap: the Bash search hook never sees a file read through
the native Read tool or a Glob. Since #522 the guard runs as the shell-agnostic
`graphify hook-guard read` subcommand (not inline bash), so it works on Windows
too. These tests invoke that subcommand with crafted stdin JSON and assert it
nudges only for a source/doc file outside graphify-out/ when a graph exists, and
otherwise stays silent and fails open.
"""
import json
import os
import subprocess
import sys

from graphify.__main__ import _claude_pretooluse_hooks


def _read_matcher():
    hooks = _claude_pretooluse_hooks()
    return next(h for h in hooks if h["matcher"] == "Read|Glob")


def _env():
    # The guard resolves the graph via GRAPHIFY_OUT (default "graphify-out",
    # relative to cwd). Drop any inherited override so the tmp_path graph is found.
    e = dict(os.environ)
    e.pop("GRAPHIFY_OUT", None)
    return e


def _run(tool_input, cwd, *, graph: bool):
    if graph:
        (cwd / "graphify-out").mkdir(parents=True, exist_ok=True)
        (cwd / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    stdin = json.dumps({"tool_input": tool_input})
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "read"],
        input=stdin, capture_output=True, text=True, cwd=cwd, env=_env(),
    )


def test_matcher_targets_read_and_glob():
    assert _read_matcher()["matcher"] == "Read|Glob"


def test_command_has_no_shell_syntax():
    # #522: the command must be a plain exe invocation, not POSIX bash.
    cmd = _read_matcher()["hooks"][0]["command"]
    for token in ("$(", "case ", "[ -f", "&&", "||", ";;", "echo '"):
        assert token not in cmd, f"shell syntax {token!r} leaked into the hook"
    assert "graphify" in cmd and "hook-guard read" in cmd


def test_silent_without_graph(tmp_path):
    out = _run({"file_path": "src/app.py"}, tmp_path, graph=False).stdout
    assert out.strip() == ""


def test_nudges_on_source_read_with_graph(tmp_path):
    out = _run({"file_path": "src/app.py"}, tmp_path, graph=True).stdout
    assert "graphify query" in out


def test_nudge_payload_is_valid_pretooluse_json(tmp_path):
    out = _run({"file_path": "pkg/mod.ts"}, tmp_path, graph=True).stdout
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "graphify query" in payload["hookSpecificOutput"]["additionalContext"]


def test_silent_on_graphify_out_targets(tmp_path):
    """Reading the graph's own report must not start a go-read-the-graph loop."""
    out = _run({"file_path": "graphify-out/GRAPH_REPORT.md"}, tmp_path, graph=True).stdout
    assert out.strip() == ""


def test_silent_on_non_source_files(tmp_path):
    for path in ("uv.lock", "logo.png", "data.bin", ".gitignore"):
        out = _run({"file_path": path}, tmp_path, graph=True).stdout
        assert out.strip() == "", f"{path} should not nudge"


def test_glob_pattern_nudges(tmp_path):
    out = _run({"pattern": "**/*.py", "path": "src"}, tmp_path, graph=True).stdout
    assert "graphify query" in out


def test_nudges_on_framework_source(tmp_path):
    """.astro/.vue/.svelte are real source types and must nudge (regression)."""
    for path in ("src/components/Hero.astro", "src/App.vue", "src/Card.svelte"):
        out = _run({"file_path": path}, tmp_path, graph=True).stdout
        assert "graphify query" in out, f"{path} should nudge"


def test_astro_glob_nudges(tmp_path):
    out = _run({"pattern": "**/*.astro"}, tmp_path, graph=True).stdout
    assert "graphify query" in out


def test_silent_on_json_config(tmp_path):
    """Config files must stay silent: '.json' must not match the '.js' extension."""
    for path in ("package.json", "tsconfig.json", "data.geojson"):
        out = _run({"file_path": path}, tmp_path, graph=True).stdout
        assert out.strip() == "", f"{path} should not nudge"


def test_nudges_on_multi_dot_source(tmp_path):
    """A real trailing extension must win on multi-dot names (the segment split):
    a.test.tsx -> .tsx (nudge), foo.min.js -> .js (nudge)."""
    for path in ("src/a.test.tsx", "lib/foo.min.js"):
        out = _run({"file_path": path}, tmp_path, graph=True).stdout
        assert "graphify query" in out, f"{path} should nudge"


def test_windows_path_nudges(tmp_path):
    """Backslash-separated paths split on the real final segment, then its ext."""
    out = _run({"file_path": r"src\components\app.py"}, tmp_path, graph=True).stdout
    assert "graphify query" in out


def test_silent_when_extension_is_on_a_directory_segment(tmp_path):
    """An extension that sits on a directory component, not the final segment,
    must not fire: my.ts/file -> tail is 'file' (no dot), silent."""
    out = _run({"file_path": "my.ts/file"}, tmp_path, graph=True).stdout
    assert out.strip() == ""


def test_fails_open_on_malformed_stdin(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "read"],
        input="this is not json", capture_output=True, text=True, cwd=tmp_path, env=_env(),
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_never_blocks(tmp_path):
    """A nudge is additionalContext only - the guard must exit 0, never deny."""
    r = _run({"file_path": "src/app.py"}, tmp_path, graph=True)
    assert r.returncode == 0
    assert '"permissionDecision"' not in r.stdout
    assert '"deny"' not in r.stdout
