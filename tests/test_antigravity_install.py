"""Antigravity install lays down its full always-on layer, not just the skill.

Regression: project-scoped `install --project --platform antigravity` previously
went through the skill-only branch (grouped with copilot/pi/kimi), so it copied
the SKILL.md but never wrote `.agents/rules/graphify.md` or
`.agents/workflows/graphify.md` - even though the uninstall path removes them.
"""
import graphify.__main__ as m


from unittest.mock import patch

def test_antigravity_project_install_writes_rules_and_workflows(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    with patch("graphify.__main__.Path.home", return_value=home):
        m._project_install("antigravity", proj)
    
    skill = home / ".gemini" / "config" / "skills" / "graphify" / "SKILL.md"
    rules = proj / ".agents" / "rules" / "graphify.md"
    workflow = proj / ".agents" / "workflows" / "graphify.md"
    
    assert skill.exists(), "skill should be installed globally under ~/.gemini/config/skills/"
    assert rules.exists(), "antigravity rules (always-on) must be written"
    assert workflow.exists(), "antigravity workflow must be written"
    # native tool-discovery frontmatter is injected into the skill
    assert skill.read_text(encoding="utf-8").startswith("---\n")


def test_antigravity_project_uninstall_clears_rules_and_workflows(tmp_path):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    with patch("graphify.__main__.Path.home", return_value=home):
        m._project_install("antigravity", proj)
        m._project_uninstall("antigravity", proj)
    
    assert not (proj / ".agents" / "rules" / "graphify.md").exists()
    assert not (proj / ".agents" / "workflows" / "graphify.md").exists()
    # The global skill should remain intact after a project uninstall.
    assert (home / ".gemini" / "config" / "skills" / "graphify" / "SKILL.md").exists()
