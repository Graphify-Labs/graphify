"""tools.contributors: core areas, one person per account, and titles from the first core commit."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools import contributors as c


@pytest.fixture(autouse=True)
def _no_ambient_git_config(monkeypatch):
    # A developer's own git config (a global mailmap, commit signing) must not change the result.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                   env=env)


def _commit(repo: Path, name: str, email: str, path: str, n: int) -> None:
    """``n`` commits by one author, each changing ``path``."""
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00"}
    for i in range(n):
        f = repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{name} {i}\n", encoding="utf-8")
        _git(repo, "add", "-A", env=env)
        _git(repo, "commit", "-qm", f"change {path} {i}", env=env)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, "maker", "maker@example.com", "graphify/build.py", 10)
    # Detection first, then extraction: the title follows the first core commit.
    _commit(repo, "det", "det@example.com", "graphify/detect.py", 1)
    _commit(repo, "det", "det@example.com", "graphify/extractors/go.py", 9)
    # One commit short of core.
    _commit(repo, "few", "few@example.com", "graphify/export.py", c.MIN_COMMITS - 1)
    # Tests and docs are not core, however many commits they take.
    _commit(repo, "docs", "docs@example.com", "docs/guide.md", 20)
    # One account, two emails: 5 + 5 core commits make one core contributor.
    _commit(repo, "split", "split@work.example", "graphify/cache.py", 5)
    _commit(repo, "split", "split@home.example", "graphify/watch.py", 5)
    return repo


def test_area_of_follows_the_pipeline_map():
    assert c.area_of("graphify/extractors/csharp.py") == "Extraction"
    assert c.area_of("graphify/ruby_resolution.py") == "Extraction"
    assert c.area_of("graphify/skills/claude/SKILL.md") == "Agent skills"
    assert c.area_of("tools/skillgen/gen.py") == "Agent skills"
    assert c.area_of("graphify/serve.py") == "MCP server"
    assert c.area_of("tests/test_detect.py") is None
    assert c.area_of("README.md") is None


def test_core_contributors_titles_and_identities(tmp_path):
    repo = _repo(tmp_path)
    mailmap = tmp_path / "contributors.mailmap"
    mailmap.write_text("# test\nsplitter <split@work.example> <split@work.example>\n"
                       "splitter <split@work.example> <split@home.example>\n", encoding="utf-8")
    commits = c.read_log(repo, mailmap=mailmap)
    core = {p.name: p for p in c.people(commits)}

    assert set(core) == {"maker", "det", "splitter"}
    first = commits[0].sha
    assert core["maker"].title(first) == "Creator"
    assert core["det"].title(first) == "Detection"
    assert core["det"].areas == {"Detection": 1, "Extraction": 9}
    assert core["splitter"].title(first) == "Cache and updates"
    assert len(core["splitter"].commits) == 10

    logins = c.mailmap_logins(mailmap)
    assert logins == {"splitter"}
    text = c.render(c.people(commits), "abc1234", first, logins)
    assert "[splitter](https://github.com/splitter)" in text
    assert "| det | Detection |" in text
    assert "| few |" not in text and "| docs |" not in text
    # The same history renders the same file.
    assert text == c.render(c.people(c.read_log(repo, mailmap=mailmap)), "abc1234", first, logins)


def test_without_a_mailmap_each_email_is_its_own_person(tmp_path):
    repo = _repo(tmp_path)
    names = {p.name for p in c.people(c.read_log(repo))}
    assert names == {"maker", "det"}
