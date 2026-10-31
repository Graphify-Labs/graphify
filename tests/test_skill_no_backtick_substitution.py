"""No command may run from a backtick inside a skill's double-quoted `-c "..."` block.

Bash expands backticks (and $(...)) inside double quotes. A comment such as
``# `graphify update` deleted it ...`` inside ``$(cat graphify-out/.graphify_python) -c "..."``
therefore ran graphify before Python started and pasted its output into the Python source
(#4461): a SyntaxError, plus an unrequested rebuild of the user's graph.

Two checks over the generated skill files (graphify/skill*.md and graphify/skills/**):

* static: no backtick inside any double-quoted -c block. PowerShell @' ... '@ here-strings
  are skipped, because nothing inside a single-quoted here-string is expanded.
* runtime: each ``$(cat graphify-out/.graphify_python) -c "..."`` statement of the files that
  hold Part C or the --update merge is run under bash with a stub interpreter, so it needs no
  inputs. A fake `graphify` and a fake `changed` log their calls and print three lines. The
  shell traces every command it runs (set -x) and PATH holds only the fakes, a `cat` link and
  the stub, so a backtick that names ANY other command shows up as a trace line the test does
  not allow.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN = REPO_ROOT / "graphify"
GENERATED = sorted(GEN.glob("skill*.md")) + sorted(GEN.glob("skills/**/*.md"))

_FENCE = re.compile(r"^```(\w*)\s*$")
_DQ = re.compile(r'(?<!\\)"')                  # an unescaped double quote
OPENER = '$(cat graphify-out/.graphify_python) -c "'
OPENER_RE = re.compile(r'^"?\$\(cat graphify-out/\.graphify_python\)"? -c "')
PART_C = "merged_edges = ast['edges'] + sem['edges']"
UPDATE = "from graphify.build import build_merge"
BASH = shutil.which("bash")
CAT = shutil.which("cat")
needs_bash = pytest.mark.skipif(
    BASH is None or CAT is None or sys.platform == "win32",
    reason="needs bash and cat on a POSIX host",
)


def _rel(path: Path) -> str:
    return path.relative_to(GEN).as_posix()


# --- static ---------------------------------------------------------------------------

def backtick_lines_in_dq_blocks(text: str) -> list[tuple[int, str]]:
    """(line number, line) for each backtick inside a -c "..." string of a fenced block."""
    hits = []
    in_fence = in_here = in_dq = False
    for no, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence, in_here, in_dq = not in_fence, False, False
            continue
        if not in_fence:
            continue
        if in_here:                            # inside @' ... '@ : never expanded, skip
            in_here = not line.startswith("'@")
            continue
        if not in_dq:
            if line.rstrip().endswith("@'"):
                in_here = True
                continue
            m = re.search(r'-c "', line)
            if not m:
                continue
            rest = line[m.end():]
            if len(_DQ.findall(rest)) % 2:     # the string closes on the same line
                continue
            in_dq = True
            if "`" in rest:
                hits.append((no, line))
            continue
        if "`" in line:
            hits.append((no, line))
        if len(_DQ.findall(line)) % 2:         # the closing quote
            in_dq = False
    return hits


@pytest.mark.parametrize("path", GENERATED, ids=_rel)
def test_no_backtick_in_double_quoted_c_block(path):
    hits = backtick_lines_in_dq_blocks(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.name}: backtick inside a double-quoted -c block: {hits[:3]}"


def test_scanner_flags_a_backtick_in_a_dq_block():
    text = '```bash\npy -c "\nx = 1\n# run `graphify update` now\n"\n```\n'
    assert backtick_lines_in_dq_blocks(text) == [(4, "# run `graphify update` now")]


def test_scanner_skips_single_quoted_here_string():
    text = "```powershell\n@'\nimport os  # -c \"\n# `graphify update`\n'@ | py -\n```\n"
    assert backtick_lines_in_dq_blocks(text) == []


def test_scanner_ignores_backticks_outside_the_quotes():
    text = '```bash\n# Save root so `graphify update` knows\npy -c "x"\n```\n'
    assert backtick_lines_in_dq_blocks(text) == []


# --- runtime --------------------------------------------------------------------------

def bash_statements(text: str) -> list[str]:
    """Each fenced-bash `$(cat ...) -c "..."` statement (the $(...) may be quoted), opener
    line to closing-quote line."""
    out, lang, cur = [], None, None
    for line in text.splitlines():
        m = _FENCE.match(line)
        if m:
            lang = None if lang is not None else (m.group(1) or "none")
            cur = None
            continue
        if lang != "bash":
            continue
        if cur is None:
            op = OPENER_RE.match(line)
            if op:
                if len(_DQ.findall(line[op.end():])) % 2:
                    out.append(line)           # a one-liner
                else:
                    cur = [line]
            continue
        cur.append(line)
        if len(_DQ.findall(line)) % 2:
            out.append("\n".join(cur))
            cur = None
    return out


def _merge_files() -> list[Path]:
    """The generated files whose bash holds Part C or the --update merge block."""
    found = []
    for p in GENERATED:
        stmts = bash_statements(p.read_text(encoding="utf-8"))
        if any(PART_C in s or UPDATE in s for s in stmts):
            found.append(p)
    return found


MERGE_FILES = _merge_files()


def _exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def run_statements(
    stmts: list[str], tmp_path: Path
) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    """Run each statement with a stub interpreter.

    Returns (calls the fakes logged, trace lines other than cat and the stub, bad exit codes).
    """
    assert BASH and CAT
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log, trace = tmp_path / "calls.log", tmp_path / "trace.txt"
    log.write_text("")
    for name in ("graphify", "changed"):
        _exe(
            bin_ / name,
            f'#!/bin/sh\necho "RAN {name} $*" >> "{log}"\necho l1\necho l2\necho l3\n',
        )
    stub = bin_ / "stubpy"
    _exe(stub, "#!/bin/sh\nexit 0\n")
    (bin_ / "cat").symlink_to(CAT)
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / ".graphify_python").write_text(str(stub))
    bad_exits = []
    for stmt in stmts:
        script = f"exec 9>>{trace}\nBASH_XTRACEFD=9\nPS4='+T '\nset -x\n{stmt}\n"
        r = subprocess.run(
            [BASH, "-c", script], cwd=tmp_path, env={"PATH": str(bin_)},
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            bad_exits.append((r.returncode, stmt.splitlines()[0]))
    allowed = (
        re.compile(r"^\+\+T cat graphify-out/\.graphify_python$"),
        re.compile(rf"^\+T {re.escape(str(stub))} -c "),
    )
    traced = [ln for ln in trace.read_text().splitlines() if re.match(r"^\++T ", ln)]
    other = [ln for ln in traced if not any(a.match(ln) for a in allowed)]
    return log.read_text().splitlines(), other, bad_exits


def test_part_c_and_update_files_are_found():
    names = {_rel(p) for p in MERGE_FILES}
    assert "skill.md" in names and "skills/claude/references/update.md" in names


@needs_bash
@pytest.mark.parametrize("path", MERGE_FILES, ids=_rel)
def test_no_command_runs_while_bash_expands_the_blocks(path, tmp_path):
    stmts = bash_statements(path.read_text(encoding="utf-8"))
    calls, other, bad_exits = run_statements(stmts, tmp_path)
    assert calls == [], f"a fake was called: {calls}"
    assert other == [], f"bash ran something besides cat and the interpreter: {other[:3]}"
    assert bad_exits == []


@needs_bash
def test_control_a_backticked_fake_is_caught(tmp_path):
    stmt = OPENER + '\n# run `graphify update` now\nprint(1)\n"'
    calls, _, _ = run_statements([stmt], tmp_path)
    assert calls == ["RAN graphify update"]


@needs_bash
def test_control_a_backticked_unknown_command_is_caught(tmp_path):
    stmt = OPENER + '\n# run `somethingelse now` here\nprint(1)\n"'
    calls, other, _ = run_statements([stmt], tmp_path)
    assert calls == [] and other and "somethingelse" in other[0]
