"""Tests for the zcode platform (`graphify install --platform zcode`).

ZCode discovers skills from ``~/.zcode/skills`` (user) and ``.zcode/skills``
(project) — https://zcode.z.ai/en/docs/skill — and reads AGENTS.md natively,
so the platform rides claude's split bundle (Agent-tool dispatch) and wires
the AGENTS.md always-on section like codex/opencode: skill-only for a global
install, skill + AGENTS.md for ``--project``.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import graphify.__main__ as mainmod


# --- destination map -----------------------------------------------------------


def test_zcode_user_destination_is_home_dot_zcode(tmp_path):
    """Global zcode skill lands at ~/.zcode/skills/graphify/SKILL.md."""
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = mainmod._platform_skill_destination("zcode", project=False)
    assert dst == tmp_path / ".zcode" / "skills" / "graphify" / "SKILL.md"


def test_zcode_project_destination_is_dot_zcode(tmp_path):
    """Project zcode skill lands at ./.zcode/skills."""
    dst = mainmod._platform_skill_destination("zcode", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".zcode" / "skills" / "graphify" / "SKILL.md"


# --- end-to-end install / uninstall via the CLI --------------------------------


def _run(tmp_path, argv, home):
    """Drive main() with argv, cwd at tmp_path, and Path.home redirected."""
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch.object(sys, "argv", ["graphify", *argv]):
            with patch("graphify.__main__.Path.home", return_value=home):
                mainmod.main()
    finally:
        os.chdir(old_cwd)


def test_install_platform_zcode_writes_user_skill_only(tmp_path):
    """`graphify install --platform zcode` writes ~/.zcode/skills SKILL.md
    (+ claude references + version stamp) and nothing else — no AGENTS.md,
    matching the global codex/opencode shape."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "zcode"], home)

    skill = home / ".zcode" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    # ZCode loads SKILL.md with a flat frontmatter parser that requires
    # name + description (description over 1024 chars drops the skill).
    body = skill.read_text(encoding="utf-8")
    assert body.startswith("---")
    assert "name: graphify" in body
    description = next(
        line for line in body.splitlines() if line.startswith("description:")
    )
    assert len(description) <= 1024 + len("description: ")
    # Global install is skill-only: no AGENTS.md section.
    assert not (cwd / "AGENTS.md").exists()


def test_install_platform_zcode_project_writes_skill_and_agents_md(tmp_path):
    """`graphify install --project --platform zcode` writes ./.zcode/skills
    PLUS the `## graphify` AGENTS.md always-on section, and leaves user scope
    untouched."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)

    project_skill = proj / ".zcode" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    agents_md = proj / "AGENTS.md"
    assert agents_md.exists()
    assert "## graphify" in agents_md.read_text(encoding="utf-8")
    # User scope was not touched.
    assert not (home / ".zcode" / "skills").exists()


def test_project_zcode_install_is_idempotent(tmp_path):
    """Running the project install twice leaves a single AGENTS.md section."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)
    _run(proj, ["install", "--project", "--platform", "zcode"], home)

    body = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert body.count("## graphify") == 1, "AGENTS.md gained a duplicate graphify section"


def test_uninstall_platform_zcode_project_removes_skill_and_agents_md(tmp_path):
    """`graphify uninstall --project --platform zcode` removes both the project
    skill and the AGENTS.md section."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)
    assert (proj / ".zcode" / "skills" / "graphify" / "SKILL.md").exists()

    _run(proj, ["uninstall", "--project", "--platform", "zcode"], home)
    assert not (proj / ".zcode" / "skills" / "graphify" / "SKILL.md").exists()
    agents_md = proj / "AGENTS.md"
    assert not agents_md.exists() or "## graphify" not in agents_md.read_text(encoding="utf-8")


def test_bare_uninstall_removes_zcode_user_skill(tmp_path):
    """Bare `graphify uninstall` clears the ~/.zcode/skills skill, which no
    other cleanup reaches (mirrors the agents/amp user-scope removals)."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "zcode"], home)
    skill = home / ".zcode" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall"], home)
    assert not skill.exists()
    assert not (home / ".zcode" / "skills").exists()
