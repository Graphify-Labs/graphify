"""The OpenCode plugin mirrors the Claude Code hook-guard contract.

The plugin ships as the `_OPENCODE_PLUGIN_JS` string in graphify.install and is
written to .opencode/plugins/graphify.js at install time. Its decision logic is
a JS port of the Python guards (cli.py `_run_hook_guard`, #3121 token analysis,
#1840 staleness softening). These tests extract the plugin body to disk, load
it with the system node, and drive `tool.execute.before` / `tool.execute.after`
with the same cases the Python hook-guard tests use, so the two harnesses stay
in lockstep.

Skipped on hosts without a `node` binary (environmental precondition).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from graphify.install import _OPENCODE_PLUGIN_JS

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node binary not installed")

_NODE = shutil.which("node")


def _run_plugin(
    plugin_file: str, calls: list[dict], tmp_path: Path, *, env: dict[str, str] | None = None, graph: bool = True
) -> list[dict]:
    """Load the plugin in node and run a batch of tool-call fixtures.

    Each call: {hook, tool, args|command, sid}. Returns the post-hook output
    payloads, with bash commands unwrapped so tests can assert on the command
    itself.
    """
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir(exist_ok=True)
    if graph:
        if not (graph_dir / "graph.json").exists():
            (graph_dir / "graph.json").write_text("{}", encoding="utf-8")
        # A manifest listing AGENTS.md, so targetIsIndexed can be exercised.
        (graph_dir / "manifest.json").write_text(
            json.dumps({"AGENTS.md": [], "src/main.py": []}), encoding="utf-8"
        )
    src = tmp_path / "AGENTS.md"
    if not src.exists():
        src.write_text("hello", encoding="utf-8")
    src_py = tmp_path / "main.py"
    src_py.parent.joinpath("src").mkdir(exist_ok=True)
    if not (tmp_path / "src" / "main.py").exists():
        (tmp_path / "src" / "main.py").write_text("x = 1", encoding="utf-8")
    if graph and not (graph_dir / ".seeded").exists():
        # Backdate the source files so they predate graph.json: without this,
        # files written after the graph read as stale (#1840 softening). Only
        # on first seed per tmp_path — a test that touches a file afterwards
        # to simulate staleness must not be undone here.
        import os

        past = (graph_dir / "graph.json").stat().st_mtime - 60
        os.utime(src, (past, past))
        os.utime(tmp_path / "src" / "main.py", (past, past))
        (graph_dir / ".seeded").write_text("", encoding="utf-8")

    driver = tmp_path / "drive.mjs"
    driver.write_text(
        json.dumps({
            "directory": str(tmp_path),
            "env": env or {},
            "calls": calls,
        }),
        encoding="utf-8",
    )
    script = tmp_path / "run_driver.mjs"
    script.write_text(
        "import { readFileSync } from 'fs';\n"
        "import { pathToFileURL } from 'url';\n"
        "const cfg = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "for (const [k, v] of Object.entries(cfg.env)) process.env[k] = v;\n"
        "const mod = await import(pathToFileURL(process.argv[3]).href);\n"
        "const plugin = await mod.GraphifyPlugin({ directory: cfg.directory });\n"
        "const out = [];\n"
        "for (const c of cfg.calls) {\n"
        "  if (c.hook === 'before') {\n"
        "    const output = { args: { command: c.command } };\n"
        "    await plugin['tool.execute.before']({ tool: c.tool, sessionID: c.sid }, output);\n"
        "    out.push({ command: output.args.command });\n"
        "  } else {\n"
        "    const output = { args: c.args, output: '' };\n"
        "    await plugin['tool.execute.after']({ tool: c.tool, sessionID: c.sid }, output);\n"
        "    out.push({ output: output.output });\n"
        "  }\n"
        "}\n"
        "console.log(JSON.stringify(out));\n",
        encoding="utf-8",
    )
    import subprocess

    res = subprocess.run(
        [_NODE, str(script), str(driver), plugin_file],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode == 0, f"node driver failed:\n{res.stderr}"
    return json.loads(res.stdout)


@pytest.fixture(scope="module")
def extracted_js(tmp_path_factory) -> str:
    out = tmp_path_factory.mktemp("extract")
    js = out / "extracted_graphify.js"
    js.write_text(_OPENCODE_PLUGIN_JS, encoding="utf-8")
    return str(js)


def _plugin_path(extracted_js: str, tmp_path: Path) -> str:
    """Copy the extracted plugin into this test's tmp dir (node resolves it
    relative to the driver's tmp tree) and return the path."""
    dst = tmp_path / "extracted_graphify.js"
    dst.write_text(Path(extracted_js).read_text(encoding="utf-8"), encoding="utf-8")
    return str(dst)


# Mirrors tests/test_hook_guard_token_match.py (the same #3121 contract).
FIRE = [
    "grep -rn foo .",
    "rg foo",
    "rg.exe foo src",
    "/usr/bin/grep -c x f",
    "egrep 'a|b' f",
    "fd -e py",
    "ack pattern",
    "ag pattern src/",
    "find . -name '*.py'",
    "git grep TODO",
    "git -C repo grep TODO",
    "cat f.txt | grep needle",
    "make build && grep -q ok build.log",
    "sudo grep root /etc/passwd",
    "xargs -0 grep -l pattern",
    "FOO=1 grep x f",
    "echo done; rg leftover",
    "result=$(grep -c x f)",
]
QUIET = [
    "git commit -m x",
    "git log -S foo",
    'git commit -m "add flag support"',
    'gh pr create --body "you can find it here"',
    'echo "see grep docs"',
    "cat asdfd file",
    "python manage.py runserver",
    "cargo build --release",
    "./gradlew test",
    "echo 'grep is a fine tool'",
    "printf 'use find sparingly'",
    "magick convert x.png y.jpg",
]


@pytest.mark.parametrize("cmd", FIRE)
def test_js_search_guard_fires_on_real_searches(tmp_path, extracted_js, cmd):
    (out,) = _run_plugin(_plugin_path(extracted_js, tmp_path), [{"hook": "before", "tool": "bash", "command": cmd, "sid": "s"}], tmp_path)
    assert "MANDATORY" in out["command"]


@pytest.mark.parametrize("cmd", QUIET)
def test_js_search_guard_stays_quiet_on_prose(tmp_path, extracted_js, cmd):
    (out,) = _run_plugin(_plugin_path(extracted_js, tmp_path), [{"hook": "before", "tool": "bash", "command": cmd, "sid": "s"}], tmp_path)
    assert "MANDATORY" not in out["command"]


def test_js_search_guard_heredoc_cases(tmp_path, extracted_js):
    quiet = (
        "cat > docs/design.md <<'EOF'\n"
        "# Search strategy\n"
        "We use grep and rg for quick scans; find . -name works too.\n"
        "EOF\n"
    )
    fires = (
        "cat > notes.txt <<'EOF'\nnothing here\nEOF\n"
        "grep -rn needle src/\n"
    )
    unterminated = "cat <<'EOF'\nall of this is grep prose with find . in it\n"
    quoted = 'echo "grep -rn foo ."'
    (q, f, u) = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [
            {"hook": "before", "tool": "bash", "command": quiet, "sid": "s"},
            {"hook": "before", "tool": "bash", "command": fires, "sid": "s"},
            {"hook": "before", "tool": "bash", "command": quoted, "sid": "s"},
        ],
        tmp_path,
    )
    assert "MANDATORY" not in q["command"]
    assert "MANDATORY" in f["command"]
    assert "MANDATORY" not in u["command"]
    (u2,) = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [{"hook": "before", "tool": "bash", "command": unterminated, "sid": "s"}],
        tmp_path,
    )
    assert "MANDATORY" not in u2["command"]


def test_js_orientation_echo_fires_once_per_session(tmp_path, extracted_js):
    outs = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [
            {"hook": "before", "tool": "bash", "command": "ls", "sid": "a"},
            {"hook": "before", "tool": "bash", "command": "ls", "sid": "a"},
            {"hook": "before", "tool": "bash", "command": "ls", "sid": "b"},
        ],
        tmp_path,
    )
    assert "knowledge graph at graphify-out" in outs[0]["command"]
    assert "knowledge graph at graphify-out" not in outs[1]["command"]
    assert "knowledge graph at graphify-out" in outs[2]["command"]


def test_js_read_guard_gates(tmp_path, extracted_js):
    outs = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [
            # graphify-out read: exempt
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "graphify-out" / "GRAPH_REPORT.md")}, "sid": "s"},
            # non-source ext: exempt
            {"hook": "after", "tool": "read", "args": {"file_path": "/tmp/x.png"}, "sid": "s"},
            # out-of-project: exempt
            {"hook": "after", "tool": "read", "args": {"file_path": "/etc/hostname"}, "sid": "s"},
            # in-project source: nudge
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "AGENTS.md")}, "sid": "s"},
        ],
        tmp_path,
    )
    assert outs[0]["output"] == ""
    assert outs[1]["output"] == ""
    assert outs[2]["output"] == ""
    assert "MANDATORY" in outs[3]["output"]


def test_js_read_guard_stale_softens(tmp_path, extracted_js):
    # The fixture writes AGENTS.md then backdates it; touch it again AFTER the
    # graph exists so its mtime is newer -> stale nudge, not mandatory (#1840).
    target = tmp_path / "AGENTS.md"
    outs = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [{"hook": "after", "tool": "read", "args": {"file_path": str(target)}, "sid": "s"}],
        tmp_path,
    )
    # Sanity: backdated read gets the mandatory nudge, not stale.
    assert "MANDATORY" in outs[0]["output"]
    target.write_text("changed", encoding="utf-8")
    (out,) = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [{"hook": "after", "tool": "read", "args": {"file_path": str(target)}, "sid": "s"}],
        tmp_path,
    )
    assert "STALE" in out["output"]


def test_js_strict_fires_once_per_session(tmp_path, extracted_js):
    outs = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "AGENTS.md")}, "sid": "s1"},
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "AGENTS.md")}, "sid": "s1"},
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "AGENTS.md")}, "sid": "s2"},
        ],
        tmp_path,
        env={"GRAPHIFY_HOOK_STRICT": "1", "GRAPHIFY_HOOK_STRICT_TTL": "0"},
    )
    assert "strict mode" in outs[0]["output"]
    assert "strict mode" not in outs[1]["output"]
    assert "MANDATORY" in outs[1]["output"]
    assert "strict mode" in outs[2]["output"]


def test_js_grep_tool_gets_search_nudge(tmp_path, extracted_js):
    (out,) = _run_plugin(_plugin_path(extracted_js, tmp_path), [{"hook": "after", "tool": "grep", "args": {"pattern": "p"}, "sid": "s"}], tmp_path)
    assert "MANDATORY" in out["output"]


def test_js_no_graph_no_nudges(tmp_path, extracted_js):
    outs = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [
            {"hook": "before", "tool": "bash", "command": "grep -rn foo .", "sid": "s"},
            {"hook": "after", "tool": "read", "args": {"file_path": str(tmp_path / "AGENTS.md")}, "sid": "s"},
        ],
        tmp_path,
        graph=False,
    )
    assert outs[0]["command"] == "grep -rn foo ."
    assert outs[1]["output"] == ""


def test_js_echo_is_shell_inert(tmp_path, extracted_js):
    (out,) = _run_plugin(
        _plugin_path(extracted_js, tmp_path),
        [{"hook": "before", "tool": "bash", "command": "grep -rn foo .", "sid": "s"}],
        tmp_path,
    )
    cmd = out["command"]
    assert cmd.startswith("echo '")
    echo_part = cmd[: cmd.index("' ; ")]
    assert "`" not in echo_part
    assert "$" not in echo_part.replace("' ;", "")
    assert cmd.split("' ; ", 1)[1] == "grep -rn foo ."