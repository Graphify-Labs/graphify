"""Tests for the zcode platform (`graphify install --platform zcode`).

ZCode discovers skills from ``~/.zcode/skills`` (user) and ``.zcode/skills``
(project) — https://zcode.z.ai/en/docs/skill — and reads AGENTS.md natively,
so the platform rides claude's split bundle (Agent-tool dispatch) and wires
the AGENTS.md always-on section like codex/opencode: skill-only for a global
install, skill + AGENTS.md + a SessionStart reminder hook in
``.zcode/config.json`` for ``--project`` (AGENTS.md rules alone proved too
easy to skip in practice — the passive rule needs an active nudge).
"""
import json
import os
import subprocess
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


# --- SessionStart reminder hook -------------------------------------------------


def _session_start_entries(cfg):
    groups = cfg["hooks"]["events"]["SessionStart"]
    return [e for g in groups if isinstance(g, dict) for e in g.get("hooks", [])]


def test_project_zcode_install_registers_sessionstart_hook(tmp_path):
    """A `--project` install also registers a SessionStart reminder hook in
    .zcode/config.json — ZCode runs config-file hooks only with
    hooks.enabled=true, so the install sets it."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)

    cfg = json.loads((proj / ".zcode" / "config.json").read_text(encoding="utf-8"))
    assert cfg["hooks"]["enabled"] is True
    ours = [e for e in _session_start_entries(cfg) if e.get("command") == "graphify"]
    assert len(ours) == 1
    # A committed config must not embed the installing machine's paths (#3129):
    # bare command + a template variable ZCode expands per session.
    assert ours[0]["type"] == "process"
    assert ours[0]["args"] == ["hook-guard", "zcode", "${CLAUDE_PROJECT_DIR}"]


def test_project_zcode_install_preserves_foreign_config(tmp_path):
    """The hook merge preserves unrelated top-level keys and foreign
    SessionStart hooks."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    (proj / ".zcode").mkdir(parents=True)
    (proj / ".zcode" / "config.json").write_text(json.dumps({
        "plugins": {"enabledPlugins": {"demo@marketplace": True}},
        "hooks": {"events": {"SessionStart": [
            {"hooks": [{"type": "process", "command": "other-tool", "args": ["x"]}]}
        ]}},
    }), encoding="utf-8")

    _run(proj, ["install", "--project", "--platform", "zcode"], home)

    cfg = json.loads((proj / ".zcode" / "config.json").read_text(encoding="utf-8"))
    assert cfg["plugins"] == {"enabledPlugins": {"demo@marketplace": True}}
    commands = [e.get("command") for e in _session_start_entries(cfg)]
    assert "other-tool" in commands
    assert commands.count("graphify") == 1


def test_project_zcode_install_hook_is_idempotent(tmp_path):
    """Two project installs leave exactly one graphify SessionStart entry."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)
    _run(proj, ["install", "--project", "--platform", "zcode"], home)

    cfg = json.loads((proj / ".zcode" / "config.json").read_text(encoding="utf-8"))
    ours = [e for e in _session_start_entries(cfg) if e.get("command") == "graphify"]
    assert len(ours) == 1, ".zcode/config.json gained a duplicate graphify hook"


def test_uninstall_project_zcode_prunes_hook_and_keeps_foreign_keys(tmp_path):
    """Uninstall strips our entry and the now-empty hooks containers, but
    leaves every key that is not ours."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "zcode"], home)
    cfg_path = proj / ".zcode" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["plugins"] = {"enabledPlugins": {"demo@marketplace": True}}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    _run(proj, ["uninstall", "--project", "--platform", "zcode"], home)

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "hooks" not in cfg, "empty hooks containers were left behind"
    assert cfg["plugins"] == {"enabledPlugins": {"demo@marketplace": True}}


def test_uninstall_project_zcode_keeps_foreign_sessionstart_hooks(tmp_path):
    """A foreign SessionStart hook survives our uninstall."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    (proj / ".zcode").mkdir(parents=True)
    (proj / ".zcode" / "config.json").write_text(json.dumps({
        "hooks": {"events": {"SessionStart": [
            {"hooks": [{"type": "process", "command": "other-tool", "args": ["x"]}]}
        ]}},
    }), encoding="utf-8")

    _run(proj, ["install", "--project", "--platform", "zcode"], home)
    _run(proj, ["uninstall", "--project", "--platform", "zcode"], home)

    cfg = json.loads((proj / ".zcode" / "config.json").read_text(encoding="utf-8"))
    commands = [e.get("command") for e in _session_start_entries(cfg)]
    assert commands == ["other-tool"]


def test_install_platform_zcode_global_writes_no_hook(tmp_path):
    """The global install stays skill-only: no .zcode/config.json in the
    project and none in the user's ~/.zcode/cli/."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "zcode"], home)

    assert not (cwd / ".zcode" / "config.json").exists()
    assert not (home / ".zcode" / "cli" / "config.json").exists()


# --- hook-guard zcode (the SessionStart payload) -------------------------------


def _run_guard(proj, *extra):
    env = dict(os.environ)
    env.pop("GRAPHIFY_OUT", None)
    return subprocess.run(
        [sys.executable, "-m", "graphify", "hook-guard", "zcode", *extra],
        input="", capture_output=True, text=True, cwd=str(proj), env=env,
    )


def test_hook_guard_zcode_nudges_when_graph_exists(tmp_path):
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    r = _run_guard(tmp_path)

    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert set(payload) == {"additionalContext"}, "ZCode validates hook stdout strictly"
    assert "graphify query" in payload["additionalContext"]


def test_hook_guard_zcode_silent_without_graph(tmp_path):
    r = _run_guard(tmp_path)

    assert r.returncode == 0
    assert r.stdout == ""


def test_hook_guard_zcode_unexpanded_project_dir_falls_back_to_cwd(tmp_path):
    """A process hook may hand ${CLAUDE_PROJECT_DIR} through unexpanded; the
    guard then falls back to the env vars / cwd instead of a literal path."""
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    r = _run_guard(tmp_path, "${CLAUDE_PROJECT_DIR}")

    assert r.returncode == 0
    assert "graphify query" in json.loads(r.stdout)["additionalContext"]
