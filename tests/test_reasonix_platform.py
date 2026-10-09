import sys
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
import graphify.install as installmod


@pytest.fixture
def host(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)
    monkeypatch.delenv("REASONIX_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "1")
    return home, project


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["graphify", *args])
    mainmod.main()


@pytest.mark.parametrize("system", ["Linux", "Darwin", "Windows"])
def test_native_install_and_uninstall(host, monkeypatch, system):
    home, project = host
    monkeypatch.setattr(installmod.platform, "system", lambda: system)
    expected_home = home / ".reasonix"
    if system == "Windows":
        expected_home = home / "AppData" / "Roaming" / "reasonix"
    run(monkeypatch, "reasonix", "install")
    skill = expected_home / "skills" / "graphify" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert 'task(prompt=' in content
    assert 'write_paths=' in content
    assert 'Task(description=' not in content
    assert (skill.parent / "references" / "extraction-spec.md").exists()
    assert (skill.parent / ".graphify_version").exists()
    assert "## graphify" in (project / "AGENTS.md").read_text(encoding="utf-8")
    if system == "Windows":
        assert "```powershell" in content
        assert "```bash" not in content
    run(monkeypatch, "reasonix", "uninstall")
    assert not skill.exists()
    assert not (project / "AGENTS.md").exists()


def test_windows_appdata_and_home_override(host, monkeypatch):
    home, _ = host
    monkeypatch.setattr(installmod.platform, "system", lambda: "Windows")
    roaming = home / "roaming"
    monkeypatch.setenv("APPDATA", str(roaming))
    assert mainmod._platform_skill_destination("reasonix") == (
        roaming / "reasonix" / "skills" / "graphify" / "SKILL.md"
    )
    custom = home / "custom"
    monkeypatch.setenv("REASONIX_HOME", str(custom))
    run(monkeypatch, "install", "--platform", "reasonix")
    skill = custom / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert not (roaming / "reasonix").exists()
    run(monkeypatch, "reasonix", "uninstall")
    assert not skill.exists()


def test_project_scope_preserves_global_skill_and_existing_guidance(host, monkeypatch):
    home, project = host
    monkeypatch.setattr(installmod.platform, "system", lambda: "Linux")
    custom = home / "custom"
    monkeypatch.setenv("REASONIX_HOME", str(custom))
    run(monkeypatch, "install", "--platform", "reasonix")
    global_skill = custom / "skills" / "graphify" / "SKILL.md"
    original = "# Project\n\nKeep this guidance.\n"
    (project / "AGENTS.md").write_text(original, encoding="utf-8")
    run(monkeypatch, "reasonix", "install", "--project")
    project_skill = project / ".reasonix" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert global_skill.exists()
    run(monkeypatch, "reasonix", "uninstall", "--project")
    assert not project_skill.exists()
    assert global_skill.exists()
    assert "Keep this guidance." in (project / "AGENTS.md").read_text(encoding="utf-8")
