"""D32: shipped POSIX runbooks execute only the recorded interpreter identity.

Use package resources, not generator imports, so the same regression runs against
an installed wheel. A harmless selected interpreter records actual shell argv;
the Python bodies remain real shell input but never execute corpus/provider work.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import graphify
import pytest

from tests.shell_portability import select_shell_executable


BARE = '$(cat graphify-out/.graphify_python)'
QUOTED = '"' + BARE + '"'


def statements():
    """Read every complete recorded-interpreter statement from shipped bash fences."""
    package = Path(graphify.__file__).parent
    resources = sorted(set(package.glob("skill*.md")) | set((package / "skills").rglob("*.md")))
    found = []
    for resource in resources:
        for block in re.findall(r"^```bash\n(.*?)^```[ \t]*$", resource.read_text(encoding="utf-8"), re.S | re.M):
            lines = iter(block.splitlines())
            for line in lines:
                if not line.lstrip().startswith((BARE + " ", QUOTED + " ")):
                    continue
                statement = line
                if line.endswith(' -c "'):
                    for body_line in lines:
                        statement += "\n" + body_line
                        if re.fullmatch(r'"[ \t]*(?:>.*)?', body_line):
                            break
                    else:
                        raise AssertionError("unterminated shipped interpreter invocation")
                found.append((resource.relative_to(package).as_posix(), statement))
    assert len(found) >= 400 and len({path for path, _ in found}) >= 80
    return found


def shell_fixture(tmp_path):
    """Record selected/split/PATH invocations using the explicitly admitted real Bash."""
    shell = select_shell_executable("bash")
    output = tmp_path / "graphify-out"
    output.mkdir()
    trace = tmp_path / "trace"
    selected = tmp_path / "selected interpreter" / "python"
    selected.parent.mkdir()
    decoys = tmp_path / "decoys"
    decoys.mkdir()

    def stub(path, name):
        path.write_text('#!/bin/sh\nprintf "%s:%s\\n" "' + name + '" "$1" >> "$GRAPHIFY_INVOKE_TRACE"\n'
                        'exit "${GRAPHIFY_INVOKE_STATUS:-0}"\n', encoding="utf-8")
        path.chmod(0o755)

    stub(selected, "selected")
    stub(tmp_path / "selected", "split")
    for name in ("python", "python3", "graphify"):
        stub(decoys / name, "PATH-" + name)
    marker = output / ".graphify_python"
    marker.write_text(selected.as_posix(), encoding="utf-8")
    env = {**os.environ, "PATH": str(decoys) + os.pathsep + os.environ.get("PATH", ""),
           "GRAPHIFY_INVOKE_TRACE": trace.as_posix()}

    def run(program, **overrides):
        return subprocess.run([shell, "-s"], input=program, cwd=tmp_path,
                              env={**env, **overrides}, capture_output=True, text=True)

    return marker, trace, run


def test_req_core001_ac01_every_shipped_head_quotes_the_recorded_identity():
    """Every emitted invocation must treat the entire selected path as one token."""
    for resource, statement in statements():
        assert statement.lstrip().startswith(QUOTED + " "), resource


def test_req_core001_ac01_actual_shipped_statements_use_spaced_selected_interpreter(tmp_path):
    """Execute all emitted heads/bodies with active split-prefix and PATH decoys."""
    _marker, trace, run = shell_fixture(tmp_path)
    commands = [statement for _, statement in statements()]
    result = run("\n".join(command + "\nif [ $? -ne 0 ]; then exit 91; fi" for command in commands))
    assert result.returncode == 0, result.stderr
    entries = trace.read_text(encoding="utf-8").splitlines()
    assert len(entries) == len(commands)
    assert all(entry in {"selected:-c", "selected:-m"} for entry in entries)


@pytest.mark.parametrize("state", ["missing", "empty", "failure"])
def test_req_core001_ac01_invalid_selected_interpreter_never_falls_back(tmp_path, state):
    """Missing/empty selection and interpreter failure reject without invoking PATH tools."""
    marker, trace, run = shell_fixture(tmp_path)
    if state == "missing":
        marker.unlink()
    elif state == "empty":
        marker.write_text("", encoding="utf-8")
    command = statements()[0][1]
    result = run(command, GRAPHIFY_INVOKE_STATUS="61" if state == "failure" else "0")
    assert result.returncode != 0
    entries = trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []
    assert entries == (["selected:-c"] if state == "failure" else [])


def test_req_core001_ac01_shell_harness_detects_unquoted_selection(tmp_path):
    """A quote-removal negative control demonstrably executes the wrong split identity."""
    _marker, trace, run = shell_fixture(tmp_path)
    command = statements()[0][1].replace(QUOTED, BARE, 1)
    run(command)
    entries = trace.read_text(encoding="utf-8").splitlines()
    assert entries and entries[0].startswith("split:")
