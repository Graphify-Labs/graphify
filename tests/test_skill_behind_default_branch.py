"""#4427: Step 1 warns when the input checkout is behind; Steps 4/5 pass built_at_commit."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "graphify").glob("skill*.md"))


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"],
                        "HOME": str(cwd)})


def _step1_snippet() -> str:
    text = (ROOT / "graphify" / "skill.md").read_text(encoding="utf-8")
    m = re.search(r'\$\(cat graphify-out/\.graphify_python\) -c "\n(import subprocess\n.*?)\n"\n', text, re.S)
    assert m, "Step 1 git check missing"
    return m.group(1).replace('\\"', '"')


def _run(snippet: str, workdir: Path, target: Path) -> str:
    (workdir / "graphify-out").mkdir(exist_ok=True)
    (workdir / "graphify-out" / ".graphify_root").write_text(str(target), encoding="utf-8")
    return subprocess.run([sys.executable, "-c", snippet], cwd=workdir, capture_output=True,
                          text=True, check=True).stdout


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_every_skill_has_check_and_commit(skill):
    text = skill.read_text(encoding="utf-8")
    assert "commit(s) behind" in text
    assert text.count("built_at_commit=built_at_commit)") == 2


def test_step1_snippet_behind_uptodate_nongit(tmp_path):
    snippet = _step1_snippet()
    up = tmp_path / "up"
    up.mkdir()
    _git(up, "init", "-q", "-b", "main")
    for i in range(3):
        _git(up, "commit", "-q", "--allow-empty", "-m", f"c{i}")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(up), str(clone))
    work = tmp_path / "w"
    work.mkdir()
    assert "0 commit(s) behind origin/main" in _run(snippet, work, clone)
    _git(clone, "reset", "-q", "--hard", "HEAD~2")
    out = _run(snippet, work, clone)
    assert "on main, 2 commit(s) behind origin/main" in out and "WARNING" in out
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _run(snippet, work, plain) == ""
    assert _run(snippet, work, up) == ""  # git repo, no remote/upstream


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_no_skip_to_step2_before_check(skill):
    text = skill.read_text(encoding="utf-8")
    before = text[:text.index("commit(s) behind")]
    assert "move straight to Step 2" not in before
    assert "If the import succeeds, print nothing and continue below." in before
