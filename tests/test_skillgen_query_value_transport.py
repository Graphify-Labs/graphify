"""Query/path/explain runbooks must never paste free-text values into code.

The skill query flows ask the agent for values it does not control: the
user's question, the expanded query string, its own answer text, node names
and cited-node lists. Before this fix those values were literal placeholders
the agent substituted into quoted shell arguments and Python string literals
(``--answer "ANSWER"``, ``question = 'QUESTION'``, ``a_term = 'NODE_A'``).
Any value containing a quote, ``$()`` or a backtick then executed as code
instead of data — the same injection class the INPUT_PATH sidecar fixed for
the scan root (#4762, ``test_skillgen_input_path_injection.py``), but firing
on ordinary use because answers and node labels routinely carry those
characters.

Every value now travels through a sidecar file under ``graphify-out/`` that
the agent writes before the block runs: ``.graphify_question``,
``.graphify_answer``, ``.graphify_nodes``, ``.graphify_expanded``,
``.graphify_node_a``, ``.graphify_node_b``, ``.graphify_node_name`` and
``.graphify_correction``. Python blocks read them back with
``Path(...).read_text``, shell lines with ``"$(cat ...)"`` or
``--answer-file``, and the cited-node list through a ``while read`` array.
``MODE`` and ``BUDGET`` stay substituted literals: one is a fixed
``bfs``/``dfs`` enum, the other a number.

These tests pin both directions over the committed generated artifacts:
the paste-the-value placeholders must be absent everywhere, and the
file-transport mechanism must be present where the flows live
(``references/query.md`` for the split hosts, inline for the Aider/Devin
monoliths). One runtime check feeds shell-hostile bytes through the
question file and proves they arrive in argv verbatim.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN = REPO_ROOT / "graphify"
BODIES = sorted(GEN.glob("skill*.md")) + sorted(GEN.glob("skills/*/references/*.md"))
QUERY_BODIES = ("skill-aider.md", "skill-devin.md", "skills/claude/references/query.md")

BASH = shutil.which("bash")

# Every placeholder the runbooks used to substitute straight into shell or
# Python source. None may appear anywhere in a generated body — not only as
# a quoted literal, but bare in prose too, because "Replace `QUESTION` with
# ..." is the instruction that makes an agent paste a value into code.
BANNED_TOKENS = (
    "'QUESTION'",
    '"QUESTION"',
    '"ANSWER"',
    '"ORIGINAL_QUESTION"',
    "'NODE_A'",
    "'NODE_B'",
    "'NODE_NAME'",
    "`QUESTION`",
    "`ANSWER`",
    "`ORIGINAL_QUESTION`",
    "`NODE_A`",
    "`NODE_B`",
    "`NODE_NAME`",
    "`SOURCE_NODES`",
    "NODE1 NODE2",
    "--answer ",
    '--correction "the right answer"',
    # Space-separated value forms: argparse eats a leading-dash value as a flag,
    # so question/correction/nodes must travel via --opt="$(cat f)" or a file.
    '--question "',
    '--correction "',
    '--nodes "',
    '"${_nodes[@]}"',
)


def test_no_generated_skill_substitutes_query_values_into_code():
    """No query-flow placeholder may survive in any generated skill body."""
    assert len(BODIES) >= 15, f"expected the generated skill bodies, found {len(BODIES)}"
    offenders = []
    for body in BODIES:
        text = body.read_text(encoding="utf-8")
        for token in BANNED_TOKENS:
            if token in text:
                offenders.append(f"{body.relative_to(REPO_ROOT)}: {token}")
    assert not offenders, (
        "a paste-the-value placeholder survived in generated skills:\n  "
        + "\n  ".join(offenders)
        + "\n— free-text values must travel through the graphify-out/ sidecar "
        "files, never into the command line or a Python string literal"
    )


@pytest.mark.parametrize("skill_file", QUERY_BODIES)
def test_query_flows_read_values_from_sidecar_files(skill_file: str):
    """Every query-flow body must use the file transport end to end."""
    text = (GEN / skill_file).read_text(encoding="utf-8")

    # Questions and node terms are read back, never pasted.
    assert "graphify-out/.graphify_question" in text
    assert "graphify-out/.graphify_node_a" in text
    assert "graphify-out/.graphify_node_b" in text
    assert "graphify-out/.graphify_node_name" in text

    # Answers always go through --answer-file; --answer never takes a value.
    for line in text.splitlines():
        if "graphify save-result" not in line:
            continue
        assert "--answer-file graphify-out/.graphify_answer" in line, (
            f"{skill_file} save-result line does not use --answer-file: {line!r}"
        )
        # --opt=value form, so a leading-dash question parses as data, not a flag.
        assert '--question="$(cat graphify-out/.graphify_question)"' in line, (
            f"{skill_file} save-result line must use --question=<value>: {line!r}"
        )
        # The cited-node list arrives through a file; it never touches argv.
        assert "--nodes-file graphify-out/.graphify_nodes" in line, (
            f"{skill_file} save-result line does not use --nodes-file: {line!r}"
        )


def test_windows_skill_query_reads_question_via_get_content():
    """skill-windows must emit an evaluated subexpression, not literal text.

    ``(Get-Content ...)`` inside a double-quoted PowerShell string is a
    literal; only the ``$``-prefixed ``$((...)`` form evaluates. ``TrimEnd``
    is CR/LF-only so boundary spaces in the question survive, matching bash
    ``$(cat ...)`` semantics.
    """
    text = (GEN / "skill-windows.md").read_text(encoding="utf-8")
    assert "$(cat " not in text
    assert '$((Get-Content graphify-out\\.graphify_question -Raw).TrimEnd("`r","`n"))' in text


def test_split_query_reference_covers_every_sidecar():
    """The shared query reference must carry all eight transport files."""
    text = (GEN / "skills/claude/references/query.md").read_text(encoding="utf-8")
    for name in (
        ".graphify_expanded",
        ".graphify_question",
        ".graphify_answer",
        ".graphify_nodes",
        ".graphify_node_a",
        ".graphify_node_b",
        ".graphify_node_name",
        ".graphify_correction",
    ):
        assert f"graphify-out/{name}" in text, (
            f"references/query.md never uses graphify-out/{name}"
        )


def _extract_save_result_block(text: str, type_tag: str) -> str:
    """Pull the fenced bash block containing one save-result line."""
    for match in re.finditer(r"```bash\n(.*?)\n```", text, re.DOTALL):
        block = match.group(1)
        if "save-result" in block and f"--type {type_tag}" in block:
            return block
    raise AssertionError(f"no save-result --type {type_tag} bash block found")


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_save_result_carries_hostile_bytes_as_data(tmp_path: Path):
    """A question/node value with $(), backticks and quotes must not execute.

    The block is run verbatim under bash with a stub interpreter on PATH, so
    the argv the real save-result would receive is captured instead of a
    graph being touched. If command substitution re-expanded file contents,
    the payload would run and the sentinel would appear.
    """
    text = (GEN / "skills/claude/references/query.md").read_text(encoding="utf-8")
    block = _extract_save_result_block(text, "query")

    out = tmp_path / "graphify-out"
    out.mkdir()
    sentinel = tmp_path / "PWNED_QUERY_VALUE"
    # Leading dash: with `--question value` argparse would eat this as a flag;
    # the `--question=value` form must carry it through as data.
    hostile_q = f'--update q"; touch {sentinel}; $(touch {sentinel}); `touch {sentinel}`'
    hostile_n = f"n; touch {sentinel}"
    last_n = "last-node-no-trailing-newline"
    (out / ".graphify_question").write_text(hostile_q, encoding="utf-8")
    (out / ".graphify_answer").write_text(hostile_q, encoding="utf-8")
    # No trailing newline and a leading-dash label: the CLI's splitlines
    # reader must still deliver the final line, and argparse must not eat
    # a `-`-prefixed entry as a flag.
    (out / ".graphify_nodes").write_text(
        f"{hostile_n}\n-dash-node\n{last_n}", encoding="utf-8"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "fakepy"
    stub.write_text(
        "#!/bin/sh\nfor a in \"$@\"; do printf '%s\\n' \"$a\"; done > argv.txt\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    (out / ".graphify_python").write_text("fakepy", encoding="utf-8")

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        [BASH, "-c", block.replace("\r\n", "\n")],
        cwd=tmp_path, capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 0, (
        f"the save-result block itself must run cleanly; stderr={result.stderr!r}"
    )

    assert not sentinel.exists(), (
        "a hostile value delivered through the sidecar file executed as "
        "shell code — file transport is not isolating data from the command line"
    )
    argv = (tmp_path / "argv.txt").read_text(encoding="utf-8")
    assert f"--question={hostile_q}" in argv, (
        f"the question value must arrive verbatim as one --question= arg; got {argv!r}"
    )
    # Node labels never touch argv at all — the file path does.
    assert "--nodes-file" in argv
    assert "graphify-out/.graphify_nodes" in argv
    assert hostile_n not in argv and last_n not in argv, (
        f"node content must travel inside the file, never in argv; got {argv!r}"
    )


@pytest.mark.skipif(
    shutil.which("python3") is None, reason="python3 not available"
)
def test_save_result_nodes_file_end_to_end(tmp_path: Path):
    """`graphify save-result --nodes-file` reads labels back as data.

    A leading-dash label and an unterminated final line must both land in the
    saved doc — argparse cannot see them because they never touch argv.
    """
    pytest.importorskip("networkx")
    nodes = tmp_path / "nodes.txt"
    nodes.write_text("real-node\n-dash-node\nlast-no-newline", encoding="utf-8")
    answer = tmp_path / "answer.txt"
    answer.write_text("the answer", encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [
            "python3", "-B", "-m", "graphify", "save-result",
            "--question=--update vs --cluster-only",
            f"--answer-file={answer}",
            f"--nodes-file={nodes}",
            f"--memory-dir={tmp_path / 'memory'}",
        ],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"save-result failed: {result.stderr!r}"
    docs = list((tmp_path / "memory").glob("*.md"))
    assert docs, "save-result wrote no memory doc"
    body = docs[0].read_text(encoding="utf-8")
    for label in ("real-node", "-dash-node", "last-no-newline"):
        assert label in body, f"{label} missing from saved doc: {body!r}"
    assert "--update vs --cluster-only" in body
