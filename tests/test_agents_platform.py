"""Tests for the generic `agents` platform and its `skills` alias (#1432).

`graphify install --platform agents` (and the friendly `--platform skills`
alias) installs the skill to the cross-framework Agent-Skills locations: the
spec's user-global ``~/.agents/skills`` and project ``./.agents/skills`` — the
directories ``npx skills`` and spec-compliant frameworks read.

The bare ``graphify install`` behaviour (claude/windows only) is unchanged; the
named platform is opt-in. The ``graphify agents install`` subcommand is the
amp-twin: it also wires AGENTS.md, matching the rendered hooks reference.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod


# --- destination map -----------------------------------------------------------


def test_agents_user_destination_is_user_global_dot_agents(tmp_path):
    """Global agents skill lands at ~/.agents/skills (the spec's user-global dir),
    NOT amp's ~/.config/agents/skills."""
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = mainmod._platform_skill_destination("agents", project=False)
    assert dst == tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md"


def test_agents_project_destination_is_dot_agents(tmp_path):
    """Project agents skill lands at ./.agents/skills."""
    dst = mainmod._platform_skill_destination("agents", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md"


# --- the skills alias ----------------------------------------------------------


def test_skills_alias_resolves_to_agents():
    assert mainmod._canonical_platform("skills") == "agents"
    assert mainmod._canonical_platform("agents") == "agents"
    # A non-aliased platform is returned unchanged.
    assert mainmod._canonical_platform("amp") == "amp"


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


@pytest.mark.parametrize("platform_arg", ["agents", "skills"])
def test_install_platform_agents_writes_user_global_skill_only(tmp_path, platform_arg):
    """`graphify install --platform agents|skills` writes ~/.agents/skills/...
    SKILL.md (+ references) and nothing else — no AGENTS.md (skill-only, like
    `--platform amp`)."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", platform_arg], home)

    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    # Skill-only: the --platform path must not write an AGENTS.md.
    assert not (cwd / "AGENTS.md").exists()


def test_uninstall_platform_agents_removes_user_global_skill(tmp_path):
    """Bare `graphify uninstall` clears the ~/.agents/skills skill the AGENTS.md and
    amp cleanups never reach."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "agents"], home)
    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall"], home)
    assert not skill.exists()
    # The now-empty skill tree is walked away.
    assert not (home / ".agents" / "skills").exists()


@pytest.mark.parametrize("platform_arg", ["agents", "skills"])
def test_uninstall_platform_flag_global_removes_skill(tmp_path, platform_arg):
    """`graphify uninstall --platform agents|skills` (global) clears ~/.agents/skills.

    The global uninstall dispatch ignores the selected platform and always runs
    uninstall_all; this locks in that the CLI form is accepted and that
    uninstall_all's `_remove_skill_file("agents")` reaches the skill.
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", platform_arg], home)
    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall", "--platform", platform_arg], home)
    assert not skill.exists()


def test_project_uninstall_all_removes_agents_skill(tmp_path):
    """`graphify uninstall --project` (no platform) removes the agents project skill
    via the _PLATFORM_CONFIG loop — cleanly, despite agents/amp/antigravity sharing
    the ./.agents/skills path (the loop hits an already-removed tree harmlessly)."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "agents"], home)
    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()

    _run(proj, ["uninstall", "--project"], home)
    assert not project_skill.exists()


def test_install_platform_agents_project_writes_dot_agents(tmp_path):
    """`graphify install --project --platform agents` writes ./.agents/skills and
    leaves user scope untouched."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "agents"], home)

    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    # User scope was not touched.
    assert not (home / ".agents" / "skills").exists()

    _run(proj, ["uninstall", "--project", "--platform", "agents"], home)
    assert not project_skill.exists()


# --- the amp-twin subcommand (graphify agents install) -------------------------


def test_agents_subcommand_install_also_wires_agents_md(tmp_path):
    """`graphify agents install` is the amp-twin: skill at ~/.agents/skills PLUS a
    `## graphify` section in AGENTS.md (so the rendered hooks reference, which
    points at `graphify agents install`, stays honest)."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["agents", "install"], home)

    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    agents_md = cwd / "AGENTS.md"
    assert skill.exists()
    assert agents_md.exists()
    assert "## graphify" in agents_md.read_text(encoding="utf-8")

    _run(cwd, ["agents", "uninstall"], home)
    assert not skill.exists()
    # The section is stripped unconditionally: the file is either removed (it held
    # only our section) or no longer contains the marker.
    assert not agents_md.exists() or "## graphify" not in agents_md.read_text(encoding="utf-8")


def test_agents_subcommand_install_is_idempotent(tmp_path):
    """Running `graphify agents install` twice leaves a single AGENTS.md section."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["agents", "install"], home)
    _run(cwd, ["agents", "install"], home)

    body = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    assert body.count("## graphify") == 1, "AGENTS.md gained a duplicate graphify section"


def test_skills_subcommand_is_the_agents_subcommand(tmp_path):
    """`graphify skills install`/`uninstall` behaves exactly like the agents form:
    skill at ~/.agents/skills (with references) PLUS the AGENTS.md section."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["skills", "install"], home)
    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    agents_md = cwd / "AGENTS.md"
    assert skill.exists()
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    assert agents_md.exists()
    assert "## graphify" in agents_md.read_text(encoding="utf-8")

    # The `skills` alias of the uninstall subcommand tears it back down.
    _run(cwd, ["skills", "uninstall"], home)
    assert not skill.exists()
    assert not agents_md.exists() or "## graphify" not in agents_md.read_text(encoding="utf-8")


# --- bare install is unchanged -------------------------------------------------


def test_bare_install_does_not_touch_dot_agents(tmp_path):
    """`graphify install` (no platform) stays single-platform claude/windows and
    never populates ~/.agents/skills (the #1432 out-of-scope guarantee)."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install"], home)
    assert not (home / ".agents" / "skills").exists()
