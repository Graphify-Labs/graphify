"""The runbook's temp-file cleanup must not depend on a shell.

Cleanup was the only part of the pipeline that shelled out, with `rm -f` and
`find ... -delete`. On a host that gates the agent's shell, destructive verbs are
exactly what the policy withholds, so both calls were denied, the pipeline had no
fallback, and the intermediates stayed on disk (#2790). That is not just clutter:
Part C and Step B3 read `.graphify_chunk_*.json` and `.graphify_semantic_new.json`
unconditionally, so a stale chunk from a previous run can be merged into the next
`--update`.

It is the third reported cause of one symptom -- #1172 was the fish/zsh no-match
glob, #464 the Codex/Windows leftovers -- and unlike those, retrying or switching
shell does not help, because the cause is a permission policy.

These tests assert the property that kills the whole class: no shipped skill asks
a shell to delete anything, and the Python that replaced it actually removes the
files it names.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parent.parent / "graphify"
SKILL_FILES = sorted(SKILLS_DIR.glob("skill*.md"))
REFERENCE_FILES = sorted((SKILLS_DIR / "skills").rglob("*.md"))

# Shell verbs that delete. `cp` and `mkdir` are deliberately absent: they are not
# destructive, so they are not what a permission policy withholds, and #2790 is
# specifically about the delete step.
_DELETE_VERBS = (
    re.compile(r"(?<![\w-])rm\s+-[a-zA-Z]*f"),
    re.compile(r"(?<![\w-])rm\s+-[a-zA-Z]*r"),
    re.compile(r"\bfind\b[^\n]*-delete"),
    re.compile(r"\bRemove-Item\b"),
    re.compile(r"\bdel\s+/[qQfF]"),
)


def _offending(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        for pat in _DELETE_VERBS
        if pat.search(line)
    ]


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.name)
def test_no_shipped_skill_deletes_through_a_shell(path):
    assert not _offending(path.read_text(encoding="utf-8")), (
        f"{path.name} deletes through a shell verb; a permission-gated host will "
        f"deny it: {_offending(path.read_text(encoding='utf-8'))}"
    )


@pytest.mark.parametrize("path", REFERENCE_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_no_shipped_reference_deletes_through_a_shell(path):
    assert not _offending(path.read_text(encoding="utf-8")), (
        f"{path} deletes through a shell verb"
    )


def test_every_skill_still_cleans_the_chunk_files():
    """The guard above passes trivially if cleanup were simply deleted. Every
    skill that dispatches chunks must still remove them, in Python."""
    checked = 0
    for path in SKILL_FILES:
        text = path.read_text(encoding="utf-8")
        if ".graphify_chunk_" not in text:
            continue
        checked += 1
        assert re.search(r"for _chunk in .*glob\('\.graphify_chunk_\*\.json'\):", text), (
            f"{path.name} dispatches chunks but never cleans them up"
        )
        assert "_chunk.unlink(missing_ok=True)" in text, path.name
    assert checked >= 10, f"expected most skills to dispatch chunks, saw {checked}"


# ---------------------------------------------------------------------------
# The replacement actually works
# ---------------------------------------------------------------------------

_CLEANUP = """
from pathlib import Path
_out = Path('graphify-out')
for _tmp in ['.graphify_detect.json', '.graphify_extract.json', '.graphify_ast.json', '.graphify_semantic.json', '.graphify_analysis.json', '.needs_update']:
    (_out / _tmp).unlink(missing_ok=True)
for _chunk in _out.glob('.graphify_chunk_*.json'):
    _chunk.unlink(missing_ok=True)
"""


def test_the_cleanup_block_shipped_in_skill_md_is_the_one_under_test():
    """Pin the snippet below to what skill.md actually ships, so this file cannot
    drift into testing something the runbook no longer says."""
    text = (SKILLS_DIR / "skill.md").read_text(encoding="utf-8")
    for line in _CLEANUP.strip().splitlines()[1:]:  # skip the import
        assert line in text, f"skill.md no longer contains: {line!r}"


def _seed(root: Path) -> None:
    out = root / "graphify-out"
    out.mkdir(parents=True)
    for name in (".graphify_detect.json", ".graphify_extract.json", ".graphify_ast.json",
                 ".graphify_semantic.json", ".graphify_analysis.json", ".needs_update",
                 ".graphify_chunk_01.json", ".graphify_chunk_02.json"):
        (out / name).write_text("{}", encoding="utf-8")
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    (out / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")


def test_cleanup_removes_every_intermediate_and_keeps_the_outputs(tmp_path):
    _seed(tmp_path)
    subprocess.run([sys.executable, "-c", _CLEANUP], cwd=tmp_path, check=True)

    left = sorted(p.name for p in (tmp_path / "graphify-out").iterdir())
    assert left == ["GRAPH_REPORT.md", "graph.json"], left


def test_cleanup_is_idempotent_when_nothing_is_there(tmp_path):
    """`rm -f` tolerated missing files; `unlink(missing_ok=True)` must too, or a
    --no-viz / cluster-only run that never wrote a chunk would crash Step 9."""
    (tmp_path / "graphify-out").mkdir()
    subprocess.run([sys.executable, "-c", _CLEANUP], cwd=tmp_path, check=True)
    subprocess.run([sys.executable, "-c", _CLEANUP], cwd=tmp_path, check=True)


def test_cleanup_does_not_need_the_output_dir_to_exist(tmp_path):
    """glob() on a missing directory yields nothing rather than raising."""
    subprocess.run([sys.executable, "-c", _CLEANUP], cwd=tmp_path, check=True)
