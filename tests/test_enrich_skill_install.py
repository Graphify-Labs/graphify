import subprocess, sys


def test_skill_enrich_md_is_packaged():
    """skill-enrich.md must be present in the installed package."""
    from pathlib import Path
    import graphify
    pkg_dir = Path(graphify.__file__).parent
    skill_path = pkg_dir / "skill-enrich.md"
    assert skill_path.exists(), f"skill-enrich.md not found in package at {skill_path}"
