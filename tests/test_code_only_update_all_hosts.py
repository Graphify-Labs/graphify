"""#4447: a code-only ``--update`` must reach the merge with this run's AST in it.

The ``--update`` runbook says what the agent does when ``code_only`` is True. This test
reads that paragraph from the RENDERED skill, runs the blocks the paragraph names (Part A,
plus the Part B fast path and Part C only if it names them), then runs the merge and checks
what came out. The route is not hard-coded: a paragraph that names too little fails here,
which is the bug (Part A writes only ``.graphify_ast.json``; the merge reads
``.graphify_extract.json``).

Hosts: the 14 generated skills share one set of anchors (windows runs its PowerShell
here-string bodies through the interpreter on stdin: it tests the Python and the step order,
not PowerShell quoting). aider and devin are monoliths with their own anchors.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402

STALE = "stale_semantic_label"


@dataclass(frozen=True)
class Anchors:
    """Where a host keeps the blocks the code-only paragraph can name."""

    prefix: str  # directory of the .graphify_*.json files, relative to the project
    part_a: str
    fast_path: str  # anchor of the block that writes the empty semantic file (a host may have none)
    part_c: str
    merge: str


_AST = "graphify_ast.json').write_text(json.dumps(result"
_FAST = "graphify_semantic.json').write_text(json.dumps({'nodes':[]"
_PART_C = "graphify_extract.json').write_text(json.dumps(merged"

SHARED = Anchors("graphify-out/", _AST, _FAST, _PART_C, "build_merge(")
DEVIN = Anchors("graphify-out/", _AST, _FAST, _PART_C, "G_existing.update(")
AIDER = Anchors("", _AST, _FAST, _PART_C, "G_existing.update(")  # cwd-relative files

SHARED_HOSTS = ["agents", "amp", "claude", "claw", "codex", "copilot", "droid", "kilo",
                "kiro", "opencode", "pi", "trae", "vscode", "windows"]
# shared hosts: add the params back once #4313 lands
HOSTS = [pytest.param("devin", DEVIN, id="devin"), pytest.param("aider", AIDER, id="aider")]

# --- reading the paragraph -----------------------------------------------------------------

_NEGATION = re.compile(r"\b(?:skip\w*|do not|don't|never|without|not)\b", re.I)
_STEP_REF = re.compile(
    r"(?P<A>Step 3A|Part A)|(?P<B>Step 3B|Part B|fast path)|(?P<C>Step 3C|Part C)|(?P<merge>\bmerge\b)",
    re.I,
)
_ANY_REF = re.compile(r"\b(?:Step \d\w*|Part [A-Z])\b")


def steps_named(paragraph: str) -> list[str]:
    """Steps the paragraph tells the agent to run, in order: "A", "B" (fast path), "C", "merge".

    Only the first mention of a step counts; a later mention (``only after Part C has
    completed``) is not a second run. Code spans are dropped (the print message says
    "skipping"), as is any clause with a negation. A step reference this reader cannot map
    raises instead of being ignored.
    """
    text = re.sub(r"`[^`]*`", "", paragraph).split(":", 1)[1]
    found: list[str] = []
    for clause in re.split(r"[,;]|\bthen\b|\bbut\b|\.\s", text):
        if _NEGATION.search(clause):
            continue
        for ref in _ANY_REF.findall(clause):
            if not _STEP_REF.fullmatch(ref) and not re.fullmatch(r"Step [4-9]\w*", ref):
                raise ValueError(f"the paragraph names {ref!r}, which this test cannot map to a block")
        for m in _STEP_REF.finditer(clause):
            if m.lastgroup is not None and m.lastgroup not in found:
                found.append(m.lastgroup)
    return found


@pytest.mark.parametrize("sentence,expected", [
    # the text on v8
    ("If `code_only` is True: print `x - skipping y`, run only Step 3A (AST) on the changed files, "
     "skip Step 3B entirely (no subagents), then go straight to merge and Steps 4-8.", ["A", "merge"]),
    ("If `code_only` is True: run Step 3A, skip Step 3B (no subagents), then run the Part B fast path, "
     "run Part C, then go straight to merge.", ["A", "B", "C", "merge"]),
    ("If `code_only` is True: run Step 3A, do not run Part C, then go straight to merge.", ["A", "merge"]),
    # PR #4313's paragraph, verbatim: Part C is named again after the merge, which is not a second run
    ("If `code_only` is True: print `[graphify update] Code-only changes detected - skipping semantic "
     "extraction (no LLM needed)`, run Step 3A (AST) on the changed files, then follow only Part B's "
     "**Fast path** to overwrite `.graphify_semantic.json` with an empty result and run Part C to create "
     "`.graphify_extract.json` from the fresh AST result. Skip semantic cache checks/writes and subagents "
     "(Steps B0–B3); do not reuse semantic sidecars from a prior run. Continue to the incremental merge and "
     "Steps 4–8 only after Part C has completed.", ["A", "B", "C", "merge"]),
    # the issue's second route: the merge builds the extraction from the AST file
    ("If `code_only` is True: run Step 3A (AST) on the changed files, then go straight to merge, which "
     "builds the extraction from the AST file.", ["A", "merge"]),
])
def test_steps_named_reads_only_what_the_paragraph_tells_the_agent_to_run(sentence, expected):
    assert steps_named(sentence) == expected


@pytest.mark.parametrize("ref", ["Part D", "Step 3B0"])
def test_steps_named_refuses_a_step_it_cannot_map(ref):
    with pytest.raises(ValueError, match="cannot map"):
        steps_named(f"If `code_only` is True: run Step 3A, run {ref}, then merge.")


# --- rendering and running the blocks --------------------------------------------------------

def _blocks(text: str, lang: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1)) for m in re.finditer(rf"```{lang}\n(.*?)```", text, re.S)]


def _find(blocks: list[str], anchor: str) -> str:
    hits = [b for b in blocks if anchor in b]
    assert hits, f"no rendered block contains {anchor!r}"
    return hits[0]


class Runbook:
    def __init__(self, host: str, anchors: Anchors):
        artifacts = {a.path: a.content for a in gen.render_all(gen.load_platforms(), only=host)}
        core = next(c for p, c in artifacts.items() if re.fullmatch(r"graphify/skill(-\w+)?\.md", p))
        update = artifacts.get(f"graphify/skills/{host}/references/update.md")
        if update is None:  # aider, devin: the --update section is inside the one file
            core, update = core.split("## For --update", 1)
        self.stdin = host == "windows"  # PowerShell here-strings: pipe the Python body to the interpreter
        core_blocks = [b for _, b in _blocks(core, "powershell" if self.stdin else "bash")]
        update_blocks = _blocks(update, "bash")
        paragraph = re.search(r"^If `code_only` is True:.*$", update, re.M)
        assert paragraph, "no code_only paragraph in the rendered --update section"
        self.paragraph = paragraph.group(0)
        # every update-section block written before the paragraph (detect, code_only check, ...)
        self.before = [b for pos, b in update_blocks if pos < paragraph.start()]
        self.blocks = {
            "A": _find(core_blocks, anchors.part_a),
            "B": next((b for b in core_blocks if anchors.fast_path in b), None),
            "C": _find(core_blocks, anchors.part_c),
            "merge": _find([b for _, b in update_blocks], anchors.merge),
        }


def _env() -> dict[str, str]:
    # bash expands backticks inside the double-quoted `python -c "..."` blocks, and Part C has
    # a comment with `graphify update`. With graphify on PATH (uv run, pipx) bash runs it and
    # pastes its output into the Python source. That is a separate bug in the skills; this
    # test checks the code-only route, so keep graphify off PATH for the blocks it runs.
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if not (Path(p) / "graphify").exists())
    return {**os.environ, "PATH": path, "PYTHONPATH": str(REPO_ROOT)}


def _run(block: str, proj: Path, *, python_on_stdin: bool = False) -> subprocess.CompletedProcess[str]:
    block = block.replace("INPUT_PATH", proj.as_posix()).replace("IS_DIRECTED", "False")
    if python_on_stdin:
        here_string = re.search(r"@'\n(.*?)\n'@", block, re.S)
        assert here_string, "no PowerShell here-string in the block"
        body = here_string.group(1)
        return subprocess.run([sys.executable, "-"], input=body, cwd=proj, env=_env(),
                              capture_output=True, text=True, timeout=300)
    return subprocess.run(["bash", "-c", block], cwd=proj, env=_env(),
                          capture_output=True, text=True, timeout=300)


def _tail(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join((result.stdout + result.stderr).strip().splitlines()[-8:])


def _project(tmp_path: Path) -> tuple[Path, int]:
    """A built two-file project, a.py then edited to add f_new(). Returns (path, baseline node count)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (proj / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    where = subprocess.run([sys.executable, "-c", "import graphify; print(graphify.__file__)"], cwd=proj,
                           env=_env(), capture_output=True, text=True, check=True).stdout.strip()
    assert Path(where).is_relative_to(REPO_ROOT), f"graphify imported from {where}, not this checkout"
    subprocess.run([sys.executable, "-m", "graphify", "update", str(proj)], cwd=proj, env=_env(),
                   check=True, capture_output=True, text=True)
    (proj / "graphify-out" / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    baseline = len(json.loads((proj / "graphify-out" / "graph.json").read_text(encoding="utf-8"))["nodes"])
    (proj / "a.py").write_text("def f():\n    return 1\n\ndef f_new():\n    return 3\n", encoding="utf-8")
    return proj, baseline


def _semantic_cache(proj: Path) -> dict[str, bytes]:
    root = proj / "graphify-out" / "cache"
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for d in root.glob("semantic*") for p in d.rglob("*") if p.is_file()}


@pytest.mark.parametrize("host,anchors", HOSTS)
def test_code_only_update_follows_its_paragraph_and_merges_the_new_function(host, anchors, tmp_path):
    book = Runbook(host, anchors)
    plan = steps_named(book.paragraph)
    assert plan and plan[0] == "A" and plan[-1] == "merge", (
        f"the code-only paragraph names {plan}; expected Part A first and the merge last")

    proj, baseline = _project(tmp_path)
    out = proj / anchors.prefix

    # State after a normal full build's cleanup: no extract/ast/semantic files. Seed a semantic
    # cache entry that must not move (the stale semantic file is seeded below, after detection:
    # aider keeps its .graphify_*.json in the project root, where detection would scan it).
    assert not (out / ".graphify_extract.json").exists()
    entry = proj / "graphify-out" / "cache" / "semantic" / ("ab" * 32 + ".json")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps({"nodes": [{"id": "cached_notes", "label": "cached"}],
                                 "edges": [], "hyperedges": []}), encoding="utf-8")
    cache_before = _semantic_cache(proj)
    assert cache_before

    ran = []
    for block in book.before:  # detect_incremental, (populate detect.json,) code_only check
        result = _run(block, proj)
        assert result.returncode == 0, f"update section block failed:\n{_tail(result)}"
        ran.append(result.stdout)
    assert any("code_only: True" in text for text in ran), "the code_only check did not report True"

    # Part A reads it, and Step 9 deleted it: the --update section has to write it again.
    assert (out / ".graphify_detect.json").exists(), "the --update section never wrote .graphify_detect.json"

    # A sidecar left by an earlier run, where this host keeps it: must not reach the result.
    (out / ".graphify_semantic.json").write_text(json.dumps({
        "nodes": [{"id": "stale_semantic", "label": STALE, "source_file": "notes.md"}],
        "edges": [], "hyperedges": []}), encoding="utf-8")

    result = None
    for name in plan:
        block = book.blocks[name]
        if block is None:
            pytest.fail(f"the paragraph names the Part B fast path, but {host} has no block "
                        "that writes the empty semantic file")
        result = _run(block, proj, python_on_stdin=book.stdin and name != "merge")
        assert result.returncode == 0, f"step {name!r} failed (plan {plan}):\n{_tail(result)}"

    assert result is not None
    merged = re.search(r"Merged: (\d+) nodes", result.stdout + result.stderr)
    assert merged, f"the merge printed no 'Merged: N nodes' line:\n{_tail(result)}"
    # The merge prints counts only on aider and devin, so "the new function is there" is judged
    # from them: baseline + f_new. A leaked stale semantic node would make it baseline + 2.
    assert int(merged.group(1)) == baseline + 1, f"{merged.group(0)}; expected {baseline + 1} nodes"

    extract = out / ".graphify_extract.json"
    if extract.exists():  # the generated hosts' merge writes the merged extraction back
        labels = {n.get("label") for n in json.loads(extract.read_text(encoding="utf-8"))["nodes"]}
        assert "f_new()" in labels
        assert STALE not in labels

    assert _semantic_cache(proj) == cache_before, "the code-only update touched the semantic cache"
