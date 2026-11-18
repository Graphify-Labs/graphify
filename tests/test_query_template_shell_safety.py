"""#5234: query blocks must carry free text to graphify byte-exact through a real bash.

The skill tells the agent to paste answers, questions and node names into the
bash blocks below. Inside ``"..."`` bash still runs backticks and ``$(...)``, and
inside ``-c "...'NODE'..."`` an apostrophe ends the Python string. These tests
render each block the way an agent does (plain text substitution) and run it
through bash, which is the layer the older ``exec``-based fallback tests skip.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FRAGMENTS = {
    "query": REPO / "tools/skillgen/fragments/references/query/default.md",
    "devin": REPO / "tools/skillgen/fragments/core/devin.md",
    "aider": REPO / "tools/skillgen/fragments/core/aider.md",
}
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

HOSTILE = 'run `touch PWNED` then $(touch PWNED2), $HOME, "q", user\'s \\ end\\'
NAME = "user's session"
OTHER = "login `touch PWNED3` handler"


def _blocks(path: Path) -> list[str]:
    return re.findall(r"```bash\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)


def _project(tmp_path: Path) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    graph = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": "a", "label": NAME}, {"id": "b", "label": OTHER}],
        "links": [{"source": "a", "target": "b", "relation": "calls",
                   "confidence": "EXTRACTED"}],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return tmp_path


def _bash(cmd: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "PYTHONPATH": str(REPO)}
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=60)


def _render(block: str) -> str:
    for key, value in (("ORIGINAL_QUESTION", HOSTILE), ("QUESTION", HOSTILE),
                       ("ANSWER", HOSTILE), ("NODE1 NODE2", NAME), ("NODE1", NAME),
                       ("NODE_A", NAME), ("NODE_B", OTHER), ("NODE_NAME", NAME)):
        block = block.replace(key, value)
    return block


def _assert_nothing_ran(cwd: Path) -> None:
    assert not list(cwd.glob("PWNED*")), "free text was executed as a shell command"


@pytest.mark.parametrize("frag", FRAGMENTS, ids=str)
@pytest.mark.parametrize("qtype", ["query", "path_query", "explain"])
def test_save_result_block_stores_hostile_text_verbatim(tmp_path, frag, qtype):
    cwd = _project(tmp_path)
    block = next(b for b in _blocks(FRAGMENTS[frag])
                 if "save-result" in b and f"--type {qtype}" in b)
    r = _bash(_render(block), cwd)
    assert r.returncode == 0, r.stderr
    _assert_nothing_ran(cwd)
    saved = next((cwd / "graphify-out" / "memory").glob("*.md")).read_text(encoding="utf-8")
    assert HOSTILE in saved
    assert NAME in saved


@pytest.mark.parametrize("frag", FRAGMENTS, ids=str)
@pytest.mark.parametrize("marker", [r"\ba_term\b", r"^term\b"], ids=["path", "explain"])
def test_fallback_reads_names_with_quotes_and_backticks(tmp_path, frag, marker):
    cwd = _project(tmp_path)
    block = next(b for b in _blocks(FRAGMENTS[frag]) if re.search(marker, b, re.M))
    r = _bash(_render(block), cwd)
    assert r.returncode == 0, r.stderr
    assert "SyntaxError" not in r.stderr
    _assert_nothing_ran(cwd)
    assert NAME in r.stdout
    if marker == r"\ba_term\b":
        assert "1 hops" in r.stdout, r.stdout


@pytest.mark.parametrize("frag", ["devin", "aider"])
def test_query_fallback_reads_raw_question_from_stdin(tmp_path, frag):
    """devin/aider have no vocab step, so `QUESTION` there is the user's raw question."""
    cwd = _project(tmp_path)
    block = next(b for b in _blocks(FRAGMENTS[frag]) if re.search(r"^question\b", b, re.M))
    cmd = _render(block).replace("MODE", "bfs").replace("BUDGET", "2000")
    cmd = cmd.replace(HOSTILE, f"{HOSTILE} session")
    r = _bash(cmd, cwd)
    assert r.returncode == 0, r.stderr
    _assert_nothing_ran(cwd)
    assert NAME in r.stdout, r.stdout


@pytest.mark.parametrize("sub", ["path", "explain"])
def test_cli_path_and_explain_blocks_pass_names_verbatim(tmp_path, sub):
    """`graphify path "NODE_A" "NODE_B"` / `graphify explain "NODE_NAME"` (not in the issue)."""
    cwd = _project(tmp_path)
    block = next(b for b in _blocks(FRAGMENTS["query"])
                 if re.match(rf"graphify {sub}\b", b))
    cmd = _render(block.replace("NODE_NAME", OTHER))
    cmd = cmd.replace("graphify ", f'"{sys.executable}" -m graphify ', 1)
    r = _bash(cmd, cwd)
    _assert_nothing_ran(cwd)
    assert NAME in r.stdout and "PWNED3" in r.stdout, r.stdout + r.stderr


FREE_TEXT = r"ORIGINAL_QUESTION|ANSWER|NODE_A|NODE_B|NODE_NAME|NODE1|the right answer"


@pytest.mark.parametrize("frag", FRAGMENTS, ids=str)
def test_no_free_text_placeholder_inside_quotes(frag):
    """Checks code only. Bare `QUESTION` stays allowed in query.md: it holds Step 0's letter-only vocab tokens."""
    text = "\n".join(_blocks(FRAGMENTS[frag]))
    quoted = re.findall(rf"""(["'])([^"'\n]*\b(?:{FREE_TEXT})\b[^"'\n]*)\1""", text)
    flags = re.findall(r"""--(?:question|answer|correction) ["']""", text)
    assert [q for _, q in quoted] == [] and flags == []


def test_cli_question_correction_and_nodes_files(tmp_path):
    for name, body in (("q", HOSTILE), ("a", "ans"), ("c", HOSTILE), ("n", f"{NAME}\n{OTHER}\n")):
        (tmp_path / name).write_text(body, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "graphify", "save-result",
         "--question-file", str(tmp_path / "q"), "--answer-file", str(tmp_path / "a"),
         "--outcome", "corrected", "--correction-file", str(tmp_path / "c"),
         "--nodes-file", str(tmp_path / "n"), "--memory-dir", str(tmp_path / "m")],
        capture_output=True, text=True, cwd=tmp_path,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    saved = next((tmp_path / "m").glob("*.md")).read_text(encoding="utf-8")
    assert saved.count(HOSTILE) >= 2
    assert NAME in saved and OTHER in saved
