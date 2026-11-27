"""Tests for graphify install / uninstall with --platform pi (#5011)."""
from pathlib import Path
from unittest.mock import patch


def _project_skill(project_dir: Path) -> Path:
    return project_dir / ".pi" / "skills" / "graphify" / "SKILL.md"


def _user_skill(home: Path) -> Path:
    return home / ".pi" / "agent" / "skills" / "graphify" / "SKILL.md"


def test_pi_install_project_writes_to_pi_skills(tmp_path):
    """Pi reads project skills from .pi/skills, not the user-scope .pi/agent/skills."""
    from graphify.install import install
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    with patch("graphify.install.Path.home", return_value=home):
        install(platform="pi", project=True, project_dir=project)
    assert _project_skill(project).exists()
    assert not (project / ".pi" / "agent").exists()
    assert not _user_skill(home).exists()


def test_pi_install_user_keeps_agent_skills_path(tmp_path):
    """User-scope install still goes to ~/.pi/agent/skills/graphify/SKILL.md."""
    from graphify.install import install
    home = tmp_path / "home"
    with patch("graphify.install.Path.home", return_value=home):
        install(platform="pi")
    assert _user_skill(home).exists()


def test_pi_remove_skill_project_resolves_the_same_path(tmp_path):
    """Removal resolves the same project path as install, so nothing is left behind."""
    from graphify.install import _remove_skill_file, install
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    with patch("graphify.install.Path.home", return_value=home):
        install(platform="pi", project=True, project_dir=project)
        assert _project_skill(project).exists()
        assert _remove_skill_file("pi", project=True, project_dir=project)
    assert not _project_skill(project).exists()


def test_pi_destinations(tmp_path):
    """The resolver itself: project -> .pi/skills, user -> ~/.pi/agent/skills."""
    from graphify.install import _platform_skill_destination
    project = tmp_path / "project"
    assert _platform_skill_destination("pi", project=True, project_dir=project) == _project_skill(project)
    with patch("graphify.install.Path.home", return_value=tmp_path):
        assert _platform_skill_destination("pi") == _user_skill(tmp_path)
