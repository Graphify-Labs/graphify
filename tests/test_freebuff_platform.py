"""Tests for the Freebuff platform.

Freebuff (freebuff.com, the Codebuff runtime) discovers skills under
``~/.agents/skills`` / ``./.agents/skills`` and the ``.claude`` equivalents, and
has no hook API, so ``AGENTS.md`` is its only always-on mechanism. It therefore
installs the same rendered Agent-Skills bundle as ``--platform agents`` instead
of a forked body: the bytes at the shared destination are identical, which is
also what keeps ``_refresh_stale_skills`` able to refresh that directory
(#2800 is the opposite case, two different bundles at one path).

``graphify freebuff install`` is the AGENTS.md-wiring form; the bare
``graphify install --platform freebuff`` stays skill-only, exactly as
``--platform agents`` and ``--platform amp`` do.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod
import graphify.install as installmod


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


# --- destination map -----------------------------------------------------------


def test_freebuff_user_destination_is_the_agent_skills_dir():
    dst = mainmod._platform_skill_destination("freebuff", project=False)
    assert dst == Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"


def test_freebuff_project_destination_is_dot_agents(tmp_path):
    dst = mainmod._platform_skill_destination("freebuff", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md"


@pytest.mark.parametrize("project", [False, True])
def test_freebuff_and_agents_share_one_destination(tmp_path, project):
    """One directory, one bundle: the two names must never diverge, or the
    shared path becomes ambiguous for _refresh_stale_skills."""
    assert mainmod._platform_skill_destination(
        "freebuff", project=project, project_dir=tmp_path
    ) == mainmod._platform_skill_destination("agents", project=project, project_dir=tmp_path)


def test_freebuff_installs_the_agents_bundle():
    """The platform entry resolves to the generic Agent-Skills bundle verbatim."""
    cfg = installmod._PLATFORM_CONFIG["freebuff"]
    assert cfg["skill_file"] == "skill-agents.md"
    assert cfg["skill_refs"] == "agents"
    assert cfg["claude_md"] is False, "Freebuff has no CLAUDE.md; AGENTS.md is its path"


# --- end-to-end install / uninstall via the CLI --------------------------------


def test_install_platform_freebuff_writes_user_global_skill_only(tmp_path):
    """`graphify install --platform freebuff` writes ~/.agents/skills/... SKILL.md
    (+ references + version stamp) and nothing else — no AGENTS.md."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "freebuff"], home)

    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    assert not (cwd / "AGENTS.md").exists()


def test_installed_skill_bytes_match_the_packaged_agents_bundle(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "freebuff"], home)

    installed = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    packaged = Path(installmod.__file__).parent / "skill-agents.md"
    assert installed.read_bytes() == packaged.read_bytes()


def test_freebuff_subcommand_install_also_wires_agents_md(tmp_path):
    """`graphify freebuff install` is the always-on form: skill + AGENTS.md.

    Freebuff has no PreToolUse equivalent, so the AGENTS.md section is the only
    always-on mechanism and must be written by this command.
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)

    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    agents_md = cwd / "AGENTS.md"
    assert skill.exists()
    assert agents_md.exists()
    assert "## graphify" in agents_md.read_text(encoding="utf-8")

    _run(cwd, ["freebuff", "uninstall"], home)
    assert not skill.exists()
    assert not agents_md.exists() or "## graphify" not in agents_md.read_text(encoding="utf-8")


def test_freebuff_subcommand_install_is_idempotent(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    _run(cwd, ["freebuff", "install"], home)

    body = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    assert body.count("## graphify") == 1, "AGENTS.md gained a duplicate graphify section"


def test_freebuff_project_install_writes_dot_agents(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "freebuff"], home)

    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    assert not (home / ".agents" / "skills").exists(), "project install must not touch user scope"

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)
    assert not project_skill.exists()


def test_freebuff_uninstall_project_matches_agents_scope(tmp_path):
    """`--project --platform freebuff` tears down the same project skill as
    `--project --platform agents`, not the user-scope copy."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "agents"], home)
    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)
    assert not project_skill.exists()
    assert not (home / ".agents" / "skills").exists()


def test_global_uninstall_cleans_the_shared_directory(tmp_path):
    """Bare `graphify uninstall` removes the Freebuff/Agent-Skills directory
    cleanly, even though two platform names share it."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall"], home)

    assert not skill.exists()
    assert not (home / ".agents" / "skills").exists()
