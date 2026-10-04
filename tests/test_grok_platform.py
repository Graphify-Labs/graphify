"""Tests for the Grok Build (`grok`) platform.

Scoping mirrors amp / agents: `graphify install --platform grok` writes only the
user-global skill at ``$GROK_HOME/skills/graphify/SKILL.md`` (default
``~/.grok/skills``). ``graphify grok install`` writes that skill plus the
``## graphify`` AGENTS.md section in the current directory; ``--project`` (on
either command) writes ``./.grok/skills/graphify/SKILL.md`` plus the AGENTS.md
section instead. ``graphify grok uninstall [--project]`` removes them.
No hook is wired for Grok in this change.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod
from tools.skillgen import gen


@pytest.fixture(autouse=True)
def _no_ambient_grok_home(monkeypatch):
    # Tests must not depend on the contributor's shell (CONTRIBUTING #11).
    monkeypatch.delenv("GROK_HOME", raising=False)


def _run(cwd, argv, home):
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        with patch.object(sys, "argv", ["graphify", *argv]):
            with patch("graphify.__main__.Path.home", return_value=home):
                mainmod.main()
    finally:
        os.chdir(old_cwd)


def _dirs(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()
    return home, cwd


# --- destination map -----------------------------------------------------------


def test_grok_global_destination_defaults_to_home_dot_grok(tmp_path):
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = mainmod._platform_skill_destination("grok")
    assert dst == tmp_path / ".grok" / "skills" / "graphify" / "SKILL.md"


def test_grok_global_destination_honors_grok_home(tmp_path, monkeypatch):
    grok_home = tmp_path / "custom grok home"  # path with a space (Windows-style)
    monkeypatch.setenv("GROK_HOME", str(grok_home))
    with patch("graphify.__main__.Path.home", return_value=tmp_path / "home"):
        dst = mainmod._platform_skill_destination("grok")
    assert dst == grok_home / "skills" / "graphify" / "SKILL.md"


def test_grok_project_destination_ignores_grok_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "elsewhere"))
    dst = mainmod._platform_skill_destination("grok", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".grok" / "skills" / "graphify" / "SKILL.md"


# --- graphify install --platform grok [--project] -----------------------------


def test_install_platform_grok_writes_global_skill_only(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["install", "--platform", "grok"], home)
    skill = home / ".grok" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert skill.read_bytes() == (Path(mainmod.__file__).parent / "skill-grok.md").read_bytes()
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert not (cwd / "AGENTS.md").exists()
    assert not (cwd / ".grok").exists()


def test_install_platform_grok_global_under_grok_home_with_space(tmp_path, monkeypatch):
    home, cwd = _dirs(tmp_path)
    grok_home = tmp_path / "Program Data" / "grok"
    monkeypatch.setenv("GROK_HOME", str(grok_home))
    _run(cwd, ["install", "--platform", "grok"], home)
    assert (grok_home / "skills" / "graphify" / "SKILL.md").exists()
    assert not (home / ".grok").exists()


def test_install_platform_grok_project_writes_project_skill_and_agents_md(tmp_path):
    # Same as `install --project --platform amp`: _project_install's AGENTS.md group.
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["install", "--project", "--platform", "grok"], home)
    assert (cwd / ".grok" / "skills" / "graphify" / "SKILL.md").exists()
    assert (cwd / "AGENTS.md").read_text(encoding="utf-8").count("## graphify") == 1
    assert not (home / ".grok").exists()


# --- graphify grok install / uninstall ----------------------------------------


def test_grok_install_writes_global_skill_and_agents_md(tmp_path, capsys):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install"], home)
    assert (home / ".grok" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (cwd / ".grok").exists()  # global skill, like `graphify amp install`
    agents = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("## graphify") == 1
    out = capsys.readouterr().out
    assert "no PreToolUse hook equivalent" not in out
    assert "grok --trust" in out and "/hooks-trust" in out


def test_grok_install_honors_grok_home(tmp_path, monkeypatch):
    home, cwd = _dirs(tmp_path)
    grok_home = tmp_path / "Program Data" / "grok"
    monkeypatch.setenv("GROK_HOME", str(grok_home))
    _run(cwd, ["grok", "install"], home)
    assert (grok_home / "skills" / "graphify" / "SKILL.md").exists()
    assert not (home / ".grok").exists()


def test_grok_install_project_writes_project_skill_and_agents_md(tmp_path, capsys):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install", "--project"], home)
    assert (cwd / ".grok" / "skills" / "graphify" / "SKILL.md").exists()
    assert (cwd / "AGENTS.md").read_text(encoding="utf-8").count("## graphify") == 1
    assert not (home / ".grok").exists()
    out = capsys.readouterr().out
    assert "grok --trust" in out
    # Never writes a .grok/rules file (Grok loads those IN ADDITION to AGENTS.md).
    assert not (cwd / ".grok" / "rules").exists()


def test_grok_install_is_idempotent_and_preserves_user_content(tmp_path):
    home, cwd = _dirs(tmp_path)
    (cwd / "AGENTS.md").write_text("# My rules\n\n- keep me\n", encoding="utf-8")
    _run(cwd, ["grok", "install"], home)
    first = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    _run(cwd, ["grok", "install"], home)
    second = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    assert second.count("## graphify") == 1
    assert "- keep me" in second


def test_grok_uninstall_removes_global_skill_and_section_idempotently(tmp_path):
    home, cwd = _dirs(tmp_path)
    (cwd / "AGENTS.md").write_text("# My rules\n\n- keep me\n", encoding="utf-8")
    _run(cwd, ["grok", "install"], home)
    _run(cwd, ["grok", "uninstall"], home)
    assert not (home / ".grok" / "skills" / "graphify").exists()
    agents = (cwd / "AGENTS.md").read_text(encoding="utf-8")
    assert "## graphify" not in agents
    assert "- keep me" in agents
    # Second uninstall is a harmless no-op.
    _run(cwd, ["grok", "uninstall"], home)
    assert (cwd / "AGENTS.md").read_text(encoding="utf-8") == agents


def test_grok_uninstall_project_removes_project_skill_and_section(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["grok", "install", "--project"], home)
    _run(cwd, ["grok", "uninstall", "--project"], home)
    assert not (cwd / ".grok").exists()
    agents = cwd / "AGENTS.md"  # removed outright when graphify's section was all it held
    assert not agents.exists() or "## graphify" not in agents.read_text(encoding="utf-8")


def test_grok_install_unknown_subcommand_exits_nonzero(tmp_path):
    home, cwd = _dirs(tmp_path)
    with pytest.raises(SystemExit) as exc:
        _run(cwd, ["grok", "bogus"], home)
    assert exc.value.code == 1


def test_bare_uninstall_removes_global_grok_skill(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["install", "--platform", "grok"], home)
    skill = home / ".grok" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    _run(cwd, ["uninstall"], home)
    assert not skill.exists()


def test_project_uninstall_all_removes_grok_project_skill(tmp_path):
    home, cwd = _dirs(tmp_path)
    _run(cwd, ["install", "--project", "--platform", "grok"], home)
    assert (cwd / ".grok" / "skills" / "graphify" / "SKILL.md").exists()
    _run(cwd, ["uninstall", "--project"], home)
    assert not (cwd / ".grok" / "skills" / "graphify" / "SKILL.md").exists()


def test_help_lists_grok(capsys):
    with patch.object(sys, "argv", ["graphify", "--help"]):
        try:
            mainmod.main()
        except SystemExit:
            pass
    out = capsys.readouterr().out
    assert "|pi|grok|devin)" in out
    assert "grok install" in out


# --- skillgen render ------------------------------------------------------------


def _grok_artifacts():
    platform = gen.load_platforms()["grok"]
    return {a.path: a.content for a in gen.render(platform)}


def test_grok_render_uses_sequential_dispatch_and_grok_hooks_wording():
    arts = _grok_artifacts()
    core = arts["graphify/skill-grok.md"]
    hooks = arts["graphify/skills/grok/references/hooks.md"]
    assert "Extract each chunk sequentially (Grok Build)" in core
    assert "#### Part B - Semantic extraction (sequential, in-session)" in core
    assert "Dispatch ALL subagents in a single message" not in core
    assert "graphify grok install" in hooks
    assert "graphify grok uninstall" in hooks
    # Grok Build has PreToolUse hooks; do not carry trae's "no PreToolUse" caveat.
    assert "does NOT support PreToolUse" not in hooks


def test_grok_audit_baseline_is_amp_and_clean():
    assert gen._v8_baseline_ref("grok").endswith(":graphify/skill-amp.md")
    if not gen._v8_available():
        pytest.skip("baseline commit not available (shallow clone)")
    assert gen.audit_coverage(gen.load_platforms()["grok"]) == []


_AGENT_TOOL_MARKERS = (
    "Agent tool",
    "Agent call",
    "subagent_type",
    "general-purpose",
    "Explore type",
    "MANDATORY: You MUST use the Agent tool",
    "`usage` field",
    "subagent",
    "Subagent",
)


def test_grok_skill_has_no_agent_tool_or_subagent_instructions():
    """Grok's skill extracts in-session; it must never tell the model to call an
    Agent tool, pass subagent_type, or read an Agent result's `usage` field. Checked
    on the committed artifacts (what ships) and on the live render."""
    pkg = Path(mainmod.__file__).parent
    shipped = [pkg / "skill-grok.md", *sorted((pkg / "skills" / "grok" / "references").glob("*.md"))]
    assert len(shipped) == 9
    rendered = _grok_artifacts()
    for path in shipped:
        text = path.read_text(encoding="utf-8")
        for marker in _AGENT_TOOL_MARKERS:
            assert marker not in text, f"{path.name} contains {marker!r}"
    for rel, text in rendered.items():
        for marker in _AGENT_TOOL_MARKERS:
            assert marker not in text, f"{rel} contains {marker!r}"


def test_subagent_hosts_keep_the_agent_tool_mandate():
    """The semantic slots default to today's text: subagent hosts still carry it."""
    platforms = gen.load_platforms()
    claude_core = gen.render(platforms["claude"])[0].content
    assert "**MANDATORY: You MUST use the Agent tool here." in claude_core
    assert 'ensure `subagent_type="general-purpose"` is used' in claude_core
    assert "#### Part B - Semantic extraction (parallel subagents)" in claude_core


def test_every_semantic_mode_defines_every_slot():
    root = gen.FRAGMENTS_DIR / "semantic"
    expected = {f"{name}.md" for name in gen._SEMANTIC_SLOTS}
    for mode in gen._SEMANTIC_MODES:
        assert {p.name for p in (root / mode).glob("*.md")} == expected, mode


def test_unknown_semantic_mode_is_rejected():
    import dataclasses

    grok = gen.load_platforms()["grok"]
    with pytest.raises(ValueError, match="unknown semantic mode"):
        gen.render(dataclasses.replace(grok, semantic="bogus"))
