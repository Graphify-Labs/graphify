"""Tests for the OMP (Oh My Pi) install platform.

`graphify install --platform omp` installs the skill into OMP's agent
directory — ``~/.omp/agent/skills`` globally, ``./.omp/agent/skills`` in
project scope — reusing pi's skill bundle, because OMP mirrors pi's agent
layout. The ``graphify omp`` subcommand is the plugin installer (PR #3506), so skill removal rides ``uninstall_all``.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod


# --- destination map -----------------------------------------------------------


def test_omp_user_destination_is_omp_agent_skills(tmp_path):
    """Global omp skill lands at ~/.omp/agent/skills — the active OMP agent
    directory, NOT the legacy ~/.pi path OMP no longer reads."""
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = mainmod._platform_skill_destination("omp", project=False)
    assert dst == tmp_path / ".omp" / "agent" / "skills" / "graphify" / "SKILL.md"


def test_omp_project_destination_is_omp_agent_skills(tmp_path):
    """Project omp skill lands at ./.omp/agent/skills."""
    dst = mainmod._platform_skill_destination("omp", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".omp" / "agent" / "skills" / "graphify" / "SKILL.md"


def test_omp_reuses_the_pi_bundle():
    """omp installs pi's skill file and references sidecar verbatim: OMP is a
    pi successor with the same skill format, so a second bundle would only
    drift."""
    cfg = mainmod._PLATFORM_CONFIG["omp"]
    assert cfg["skill_file"] == mainmod._PLATFORM_CONFIG["pi"]["skill_file"]
    assert cfg["skill_refs"] == "pi"
    assert cfg["claude_md"] is False


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


def test_install_platform_omp_writes_user_skill(tmp_path):
    """`graphify install --platform omp` writes ~/.omp/agent/skills/...
    SKILL.md (+ pi's references) and nothing else — no CLAUDE.md (skill-only)."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "omp"], home)

    skill = home / ".omp" / "agent" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    # Skill-only: the --platform path must not write a CLAUDE.md.
    assert not (cwd / "CLAUDE.md").exists()


def test_uninstall_platform_flag_global_removes_skill(tmp_path):
    """`graphify uninstall --platform omp` (global) clears ~/.omp/agent/skills.

    The global uninstall dispatch always runs uninstall_all, which carries
    `_remove_skill_file("omp")` (the `graphify omp` subcommand is the plugin
    installer, so the skill's removal rides uninstall_all, like amp/agents).
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "omp"], home)
    skill = home / ".omp" / "agent" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall", "--platform", "omp"], home)
    assert not skill.exists()


def test_install_platform_omp_project_writes_omp_agent_skills(tmp_path):
    """`graphify install --project --platform omp` writes ./.omp/agent/skills and
    leaves user scope untouched."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "omp"], home)

    project_skill = proj / ".omp" / "agent" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    # User scope was not touched.
    assert not (home / ".omp" / "agent").exists()

    _run(proj, ["uninstall", "--project", "--platform", "omp"], home)
    assert not project_skill.exists()


def test_unknown_platform_error_lists_omp(capsys, tmp_path):
    """The unknown-platform error is built from _PLATFORM_CONFIG, so the new
    platform must appear in its choices — a guard against a config entry the
    CLI error path cannot see."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    with pytest.raises(SystemExit):
        _run(cwd, ["install", "--platform", "not-a-platform"], home)

    assert "omp" in capsys.readouterr().err
