import subprocess, sys


def test_skill_enrich_md_is_packaged():
    """skill-enrich.md must be present in the installed package."""
    from pathlib import Path
    import graphify
    pkg_dir = Path(graphify.__file__).parent
    skill_path = pkg_dir / "skill-enrich.md"
    assert skill_path.exists(), f"skill-enrich.md not found in package at {skill_path}"


import os
from pathlib import Path


def test_enrich_skill_install_copies_file(tmp_path, monkeypatch):
    """graphify enrich-skill install copies skill-enrich.md to ~/.claude/skills/graphify-enrich/SKILL.md"""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "enrich-skill", "install"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(fake_home)},
    )
    assert result.returncode == 0, result.stderr
    skill_dst = fake_home / ".claude" / "skills" / "graphify-enrich" / "SKILL.md"
    assert skill_dst.exists(), f"SKILL.md not found at {skill_dst}"
    content = skill_dst.read_text()
    assert "graphify-enrich" in content
