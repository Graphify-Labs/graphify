"""Antigravity install lays down its full always-on layer, not just the skill.

Regression: project-scoped `install --project --platform antigravity` previously
went through the skill-only branch (grouped with copilot/pi/kimi), so it copied
the SKILL.md but never wrote `.agents/rules/graphify.md` or
`.agents/workflows/graphify.md` - even though the uninstall path removes them.
"""
import graphify.__main__ as m


def test_antigravity_project_install_writes_rules_and_workflows(tmp_path):
    m._project_install("antigravity", tmp_path)
    skill = tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md"
    rules = tmp_path / ".agents" / "rules" / "graphify.md"
    workflow = tmp_path / ".agents" / "workflows" / "graphify.md"
    assert skill.exists(), "skill should be installed under .agents/skills/"
    assert rules.exists(), "antigravity rules (always-on) must be written"
    assert workflow.exists(), "antigravity workflow must be written"
    # native tool-discovery frontmatter is injected into the skill
    assert skill.read_text(encoding="utf-8").startswith("---\n")


def test_antigravity_project_uninstall_clears_rules_and_workflows(tmp_path):
    m._project_install("antigravity", tmp_path)
    m._project_uninstall("antigravity", tmp_path)
    assert not (tmp_path / ".agents" / "rules" / "graphify.md").exists()
    assert not (tmp_path / ".agents" / "workflows" / "graphify.md").exists()
    assert not (tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md").exists()
