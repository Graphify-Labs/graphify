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
import json
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


def _installed_tree(base: Path) -> dict[str, bytes]:
    skill_dir = base / ".agents" / "skills" / "graphify"
    return {
        str(path.relative_to(skill_dir)): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file() and path.name != ".graphify_platforms"
    }


@pytest.mark.parametrize("project", [False, True])
def test_shared_destination_installs_identical_bytes(tmp_path, project):
    """Sharing one directory is only safe because the bytes are identical.

    A path-only equality check would still pass if the two installers diverged
    (different artifact, different references, different stamp), so compare the
    installed trees byte for byte.
    """
    trees = []
    for name in ("freebuff", "agents"):
        home = tmp_path / name / "home"
        work = tmp_path / name / "work"
        home.mkdir(parents=True)
        work.mkdir()
        argv = ["install", *(["--project"] if project else []), "--platform", name]
        _run(work, argv, home)
        trees.append(_installed_tree(work if project else home))

    assert trees[0] == trees[1], "shared skill directory holds different bytes per platform"
    assert "SKILL.md" in trees[0]
    assert any(part.endswith("extraction-spec.md") for part in trees[0])

    # The only per-platform file is the claim marker, which records who installed.
    for name in ("freebuff", "agents"):
        claim = tmp_path / name / ("work" if project else "home")
        claim = claim / ".agents" / "skills" / "graphify" / ".graphify_platforms"
        assert json.loads(claim.read_text(encoding="utf-8")) == [name]


def test_project_install_names_the_platform_it_replaces(tmp_path, capsys):
    """`./.agents/skills` is also antigravity's project destination, with a
    different bundle, so a Freebuff install there replaces its skill."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "antigravity"], home)
    installed = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    claude_bundle = installed.read_bytes()
    capsys.readouterr()

    _run(proj, ["install", "--project", "--platform", "freebuff"], home)

    out = capsys.readouterr().out
    assert "replacing" in out
    assert "the `antigravity` skill" in out
    assert installed.read_bytes() != claude_bundle


def test_platform_project_uninstall_removes_the_freebuff_section(tmp_path):
    """`uninstall --project --platform freebuff` must remove the AGENTS.md
    section that `freebuff install --project` wrote, not just the skill."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["freebuff", "install", "--project"], home)
    agents_md = proj / "AGENTS.md"
    assert "## graphify" in agents_md.read_text(encoding="utf-8")

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)

    assert not (proj / ".agents" / "skills" / "graphify" / "SKILL.md").exists()
    body = agents_md.read_text(encoding="utf-8") if agents_md.exists() else ""
    assert "## graphify" not in body


def test_freebuff_project_uninstall_drops_the_section_when_agents_is_skill_only(tmp_path):
    """Freebuff wrote the project section; a later skill-only agents install did
    not. Uninstalling Freebuff must therefore remove that section, while the skill
    stays because agents still claims it."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["freebuff", "install", "--project"], home)
    agents_md = proj / "AGENTS.md"
    assert "## graphify" in agents_md.read_text(encoding="utf-8")

    _run(proj, ["install", "--project", "--platform", "agents"], home)

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)

    assert (proj / ".agents" / "skills" / "graphify" / "SKILL.md").exists(), (
        "agents still claims the shared skill"
    )
    body = agents_md.read_text(encoding="utf-8") if agents_md.exists() else ""
    assert "## graphify" not in body


def test_project_uninstall_all_is_quiet_about_the_shared_pair(tmp_path, capsys):
    """Tearing every platform down must not add a "nothing to remove" line for
    the second half of the shared agents/freebuff directory."""
    def missing_lines(with_freebuff: bool) -> int:
        home = tmp_path / ("home-b" if with_freebuff else "home-a")
        proj = tmp_path / ("proj-b" if with_freebuff else "proj-a")
        home.mkdir()
        proj.mkdir()
        if with_freebuff:
            _run(proj, ["freebuff", "install", "--project"], home)
        capsys.readouterr()
        _run(proj, ["uninstall", "--project"], home)
        return capsys.readouterr().out.count("nothing to remove")

    assert missing_lines(with_freebuff=True) == missing_lines(with_freebuff=False)


def test_shared_bundle_install_does_not_warn_about_replacing(tmp_path, capsys):
    """agents and freebuff ship identical bytes, so swapping them is not a
    replacement of anything."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "agents"], home)
    capsys.readouterr()

    _run(proj, ["install", "--project", "--platform", "freebuff"], home)

    assert "replacing" not in capsys.readouterr().out


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


def test_freebuff_project_install_appends_to_an_existing_agents_md(tmp_path):
    """`freebuff install --project` wires AGENTS.md like the user-scope command.

    Existing project instructions must survive: the section is appended (or
    replaced in place), never written over the whole file.
    """
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    agents_md = proj / "AGENTS.md"
    agents_md.write_text("# My Project\n\nKeep these rules.\n", encoding="utf-8")

    _run(proj, ["freebuff", "install", "--project"], home)

    body = agents_md.read_text(encoding="utf-8")
    assert body.startswith("# My Project\n\nKeep these rules.\n"), body[:80]
    assert body.count("## graphify") == 1
    assert (proj / ".agents" / "skills" / "graphify" / "SKILL.md").exists()

    _run(proj, ["freebuff", "install", "--project"], home)
    assert agents_md.read_text(encoding="utf-8").count("## graphify") == 1, "duplicate section"

    _run(proj, ["freebuff", "uninstall", "--project"], home)

    after = agents_md.read_text(encoding="utf-8")
    assert "## graphify" not in after
    assert "# My Project\n\nKeep these rules.\n" in after
    assert not (proj / ".agents" / "skills" / "graphify" / "SKILL.md").exists()


def test_freebuff_project_install_writes_dot_agents(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "freebuff"], home)

    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert not (proj / "AGENTS.md").exists(), "--platform freebuff stays skill-only (parity with agents)"
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    assert not (home / ".agents" / "skills").exists(), "project install must not touch user scope"

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)
    assert not project_skill.exists()


def test_freebuff_project_uninstall_keeps_an_agents_install(tmp_path, capsys):
    """One directory, two claimants: uninstalling freebuff must leave the skill
    (and its AGENTS.md section) that `--project --platform agents` installed."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "agents"], home)
    project_skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    capsys.readouterr()

    _run(proj, ["uninstall", "--project", "--platform", "freebuff"], home)

    assert project_skill.exists(), "agents still claims the shared skill"
    out = capsys.readouterr().out
    assert "skill kept" in out
    assert "`agents`" in out
    assert not (home / ".agents" / "skills").exists()

    _run(proj, ["uninstall", "--project", "--platform", "agents"], home)
    assert not project_skill.exists()


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


def test_uninstalling_one_shared_platform_keeps_the_skill(tmp_path, capsys):
    """The bot-reported P2: removing freebuff must not take out an agents install.

    Both names write one directory, so the claim file records who installed it:
    the last claimant to uninstall removes the skill, the first one only drops
    its own claim.
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    # The subcommand form: it writes the same AGENTS.md section, unlike
    # `install --platform agents`, which is skill-only.
    _run(cwd, ["agents", "install"], home)

    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"
    claim = home / ".agents" / "skills" / "graphify" / ".graphify_platforms"
    assert json.loads(claim.read_text(encoding="utf-8")) == ["agents", "freebuff"]
    capsys.readouterr()

    _run(cwd, ["freebuff", "uninstall"], home)

    out = capsys.readouterr().out
    assert "skill kept" in out, out
    assert "`agents`" in out
    assert skill.exists(), "agents still claims the shared skill"
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    assert json.loads(claim.read_text(encoding="utf-8")) == ["agents"]
    assert "## graphify" in (cwd / "AGENTS.md").read_text(encoding="utf-8"), (
        "the shared AGENTS.md section must survive while agents is installed"
    )

    _run(cwd, ["agents", "uninstall"], home)
    assert not skill.exists()
    assert not (home / ".agents" / "skills").exists()


def test_freebuff_uninstall_drops_the_section_an_agents_skill_install_did_not_write(
    tmp_path,
):
    """Bot-reported P2 at user scope: the skill claim is not a section claim.

    `install --platform agents` is skill-only, so it never wrote the AGENTS.md
    section that `freebuff install` added. Uninstalling freebuff must remove that
    section while the skill stays for agents.
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    _run(cwd, ["install", "--platform", "agents"], home)
    agents_md = cwd / "AGENTS.md"
    skill = home / ".agents" / "skills" / "graphify" / "SKILL.md"

    _run(cwd, ["freebuff", "uninstall"], home)

    assert skill.exists(), "agents still claims the shared skill"
    body = agents_md.read_text(encoding="utf-8") if agents_md.exists() else ""
    assert "## graphify" not in body


def test_agents_uninstall_keeps_the_section_freebuff_wrote(tmp_path):
    """Both subcommands write the section, so the first one to uninstall keeps it."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["agents", "install"], home)
    _run(cwd, ["freebuff", "install"], home)

    _run(cwd, ["agents", "uninstall"], home)

    assert (home / ".agents" / "skills" / "graphify" / "SKILL.md").exists()
    assert "## graphify" in (cwd / "AGENTS.md").read_text(encoding="utf-8")

    _run(cwd, ["freebuff", "uninstall"], home)
    assert not (home / ".agents" / "skills" / "graphify" / "SKILL.md").exists()
    # The section was the only content, so AGENTS.md itself is removed.
    body = (cwd / "AGENTS.md").read_text(encoding="utf-8") if (cwd / "AGENTS.md").exists() else ""
    assert "## graphify" not in body


def _agents_md_text(project: Path) -> str:
    """AGENTS.md body, tolerating the file being removed with its last section."""
    target = project / "AGENTS.md"
    return target.read_text(encoding="utf-8") if target.exists() else ""


def test_user_scope_uninstall_cleans_the_project_it_runs_in(tmp_path, capsys):
    """The section claim is global but AGENTS.md is per project: uninstalling in
    one project must not be held back by a claim another project recorded."""
    home, project_a, project_b = tmp_path / "home", tmp_path / "a", tmp_path / "b"
    for directory in (home, project_a, project_b):
        directory.mkdir()

    _run(project_a, ["freebuff", "install"], home)
    _run(project_b, ["agents", "install"], home)
    capsys.readouterr()

    _run(project_a, ["freebuff", "uninstall"], home)

    assert "## graphify" not in _agents_md_text(project_a)
    assert "## graphify" in _agents_md_text(project_b)
    # The skill stays: `agents` still claims the shared directory.
    assert (home / ".agents" / "skills" / "graphify" / "SKILL.md").exists()


def test_uninstalling_one_project_leaves_no_section_in_it(tmp_path, capsys):
    """A second project installed by the same name must not keep this project's
    section alive."""
    home, project_a, project_b = tmp_path / "home", tmp_path / "a", tmp_path / "b"
    for directory in (home, project_a, project_b):
        directory.mkdir()

    _run(project_a, ["freebuff", "install"], home)
    _run(project_b, ["freebuff", "install"], home)
    capsys.readouterr()

    _run(project_a, ["freebuff", "uninstall"], home)

    assert "## graphify" not in _agents_md_text(project_a)
    assert "## graphify" in _agents_md_text(project_b)


def test_freebuff_project_uninstall_keeps_the_section_codex_wrote(tmp_path, capsys):
    """The claim that keeps a section alive is per platform, and codex records it
    in .codex, not in the shared .agents directory freebuff uninstalls from."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()

    _run(project, ["codex", "install", "--project"], home)
    _run(project, ["freebuff", "install", "--project"], home)
    capsys.readouterr()

    _run(project, ["freebuff", "uninstall", "--project"], home)

    assert "## graphify" in _agents_md_text(project)
    assert (project / ".codex" / "skills" / "graphify").exists()

    _run(project, ["codex", "uninstall", "--project"], home)
    assert "## graphify" not in _agents_md_text(project)


def test_codex_uninstall_keeps_the_section_freebuff_wrote(tmp_path, capsys):
    """The reverse direction: codex leaving must not strip freebuff's rules."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()

    _run(project, ["freebuff", "install", "--project"], home)
    _run(project, ["codex", "install", "--project"], home)
    capsys.readouterr()

    _run(project, ["codex", "uninstall", "--project"], home)

    assert "## graphify" in _agents_md_text(project)


def test_skill_only_project_install_does_not_keep_the_section(tmp_path, capsys):
    """Only platforms that write the AGENTS.md section count as holders: a claude
    or copilot skill installed beside AGENTS.md never touched it."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()

    _run(project, ["claude", "install", "--project"], home)
    _run(project, ["freebuff", "install", "--project"], home)
    capsys.readouterr()

    _run(project, ["freebuff", "uninstall", "--project"], home)

    assert "## graphify" not in _agents_md_text(project)
    assert "section kept" not in capsys.readouterr().out


def test_legacy_holders_do_not_keep_a_section_that_is_absent(tmp_path, capsys):
    """No section in the file means nothing to keep, whatever skill dirs exist."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()
    legacy = project / ".codex" / "skills" / "graphify"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("---\nname: graphify\n---\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# My Project\n", encoding="utf-8")

    _run(project, ["freebuff", "uninstall", "--project"], home)

    out = capsys.readouterr().out
    assert "section kept" not in out
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# My Project\n"


def test_opencode_uninstall_removes_its_plugin_while_the_section_stays(tmp_path, capsys):
    """Keeping the shared section must not keep the uninstalling platform's own
    sidecars: the OpenCode plugin belongs to OpenCode, not to AGENTS.md."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()

    _run(project, ["freebuff", "install", "--project"], home)
    _run(project, ["opencode", "install", "--project"], home)
    plugin = project / ".opencode" / "plugins" / "graphify.js"
    assert plugin.exists()
    capsys.readouterr()

    _run(project, ["opencode", "uninstall", "--project"], home)

    assert not plugin.exists()
    assert "## graphify" in _agents_md_text(project)


def test_kilo_uninstall_removes_its_plugin_while_the_section_stays(tmp_path, capsys):
    """Same for Kilo, whose plugin is written next to AGENTS.md as well."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()

    _run(project, ["freebuff", "install", "--project"], home)
    _run(project, ["kilo", "install"], home)
    plugin = project / ".kilo" / "plugins" / "graphify.js"
    assert plugin.exists()
    capsys.readouterr()

    _run(project, ["kilo", "uninstall"], home)

    assert not plugin.exists()
    assert "## graphify" in _agents_md_text(project)


def test_uninstall_keeps_the_section_for_a_pre_tracking_install(tmp_path, capsys):
    """A skill installed before section claims existed is the only evidence that
    this project's AGENTS.md was wired; deleting its rules would turn that
    host's always-on mechanism off."""
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()
    legacy = project / ".codex" / "skills" / "graphify"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("---\nname: graphify\n---\n", encoding="utf-8")

    _run(project, ["freebuff", "install", "--project"], home)
    capsys.readouterr()
    _run(project, ["freebuff", "uninstall", "--project"], home)

    assert "## graphify" in _agents_md_text(project)
    assert "section kept" in capsys.readouterr().out

    # Removing that legacy install is what relinquishes the section.
    _run(project, ["codex", "uninstall", "--project"], home)
    assert "## graphify" not in _agents_md_text(project)


def test_full_uninstall_removes_a_doubly_claimed_directory(tmp_path, capsys):
    """A full teardown ignores the claims it is about to drop: no "skill kept"
    line for a directory the same command goes on to delete."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    _run(cwd, ["agents", "install"], home)
    capsys.readouterr()

    _run(cwd, ["uninstall"], home)

    out = capsys.readouterr().out
    assert "skill kept" not in out
    assert not (home / ".agents" / "skills").exists()


def test_legacy_install_without_a_claim_file_still_uninstalls(tmp_path, capsys):
    """An install made before the claim file existed keeps the old behavior, and
    still says that the directory is shared."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["freebuff", "install"], home)
    skill_dir = home / ".agents" / "skills" / "graphify"
    (skill_dir / ".graphify_platforms").unlink()
    capsys.readouterr()

    _run(cwd, ["freebuff", "uninstall"], home)

    out = capsys.readouterr().out
    assert not (skill_dir / "SKILL.md").exists()
    assert "shared path" in out
    # `.agents/skills` itself contains "agents", so match the notice's wording.
    assert "is also the `agents` install target" in out


def test_project_uninstall_of_the_sole_claim_cleans_the_directory(tmp_path, capsys):
    """Only freebuff claims the project skill, so its uninstall removes it."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["freebuff", "install", "--project"], home)
    skill = proj / ".agents" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    capsys.readouterr()

    _run(proj, ["freebuff", "uninstall", "--project"], home)

    assert not skill.exists()
    assert not (proj / ".agents" / "skills").exists()
