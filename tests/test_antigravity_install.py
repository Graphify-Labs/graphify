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


def test_antigravity_workflow_names_no_skill_path(tmp_path):
    """The workflow must not hardcode a SKILL.md location.

    One constant serves both scopes, which install the skill to different places,
    so naming either path dangles for the other: a project-scoped install used to
    point at ~/.gemini/config/skills/graphify/SKILL.md, which it never writes.
    """
    m._project_install("antigravity", tmp_path)
    body = (tmp_path / ".agents" / "workflows" / "graphify.md").read_text(encoding="utf-8")
    assert ".gemini" not in body, "workflow must not reference the global skill dir"
    assert "SKILL.md" not in body, "workflow must not name a skill path in any scope"
    assert "~" not in body, "workflow must not reference a home directory"
    assert "graphify skill" in body, "workflow should still point at the skill by name"


def test_antigravity_global_install_workflow_names_no_skill_path(tmp_path, monkeypatch):
    """Global install shares the constant, so it must stay path-free too."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    m._antigravity_install(tmp_path)

    # The skill really does land in the global dir the old text named ...
    assert (
        tmp_path / "home" / ".gemini" / "config" / "skills" / "graphify" / "SKILL.md"
    ).exists()
    # ... but the workflow still must not hardcode it.
    body = (tmp_path / ".agents" / "workflows" / "graphify.md").read_text(encoding="utf-8")
    assert ".gemini" not in body
    assert "SKILL.md" not in body


def test_antigravity_project_uninstall_clears_rules_and_workflows(tmp_path):
    m._project_install("antigravity", tmp_path)
    m._project_uninstall("antigravity", tmp_path)
    assert not (tmp_path / ".agents" / "rules" / "graphify.md").exists()
    assert not (tmp_path / ".agents" / "workflows" / "graphify.md").exists()
    assert not (tmp_path / ".agents" / "skills" / "graphify" / "SKILL.md").exists()
