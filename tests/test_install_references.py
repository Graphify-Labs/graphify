"""Tests for the progressive-disclosure references/ sidecar install path.

The real fragment bundles do not ship in the package yet (they land in a later
phase), so these tests stage a hand-made fake bundle under
``graphify/skills/<platform>/references/`` and exercise the full install,
version-stamp, reinstall, and uninstall flow through the live code path. This
proves the net-new dir-copy plumbing without the real fragments.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify
import graphify.__main__ as mainmod


PKG_DIR = Path(graphify.__file__).parent


@pytest.fixture()
def fake_bundle():
    """Create a fake references/ bundle inside the real package for one platform.

    Yields the platform name. Cleans up the staged dir afterward so the working
    tree is left untouched. claude is used because its skill_refs bundle is
    "claude" and it has no extra plugin wiring.
    """
    platform = "claude"
    bundle = mainmod._PLATFORM_CONFIG[platform]["skill_refs"]
    skills_root = PKG_DIR / "skills"
    refs_dir = skills_root / bundle / "references"
    created_root = not skills_root.exists()
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "extraction-spec.md").write_text("# extraction spec fragment\n", encoding="utf-8")
    (refs_dir / "query.md").write_text("# query fragment\n", encoding="utf-8")
    try:
        yield platform
    finally:
        import shutil
        if created_root:
            shutil.rmtree(skills_root, ignore_errors=True)
        else:
            shutil.rmtree(skills_root / bundle, ignore_errors=True)


def _install(tmp_path, platform):
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with patch("graphify.__main__.Path.home", return_value=tmp_path):
            mainmod.install(platform=platform)
    finally:
        os.chdir(old_cwd)


def test_install_stages_references_sidecar(tmp_path, fake_bundle):
    """A progressive platform install drops references/ alongside SKILL.md."""
    platform = fake_bundle
    _install(tmp_path, platform)
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    assert (skill_dir / "SKILL.md").exists()
    refs = skill_dir / "references"
    assert refs.is_dir()
    assert (refs / "extraction-spec.md").read_text() == "# extraction spec fragment\n"
    assert (refs / "query.md").read_text() == "# query fragment\n"
    # No leftover staging dir.
    assert not (skill_dir / "references.tmp").exists()


def test_single_version_stamp_covers_skill_and_references(tmp_path, fake_bundle):
    """One .graphify_version stamp versions SKILL.md + references/ together."""
    platform = fake_bundle
    _install(tmp_path, platform)
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    stamps = list(skill_dir.rglob(".graphify_version"))
    assert len(stamps) == 1
    assert stamps[0] == skill_dir / ".graphify_version"
    assert stamps[0].read_text() == mainmod.__version__


def test_reinstall_replaces_references_atomically(tmp_path, fake_bundle):
    """Reinstall swaps references/ in place, dropping a stale fragment."""
    platform = fake_bundle
    _install(tmp_path, platform)
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    refs = skill_dir / "references"
    # Simulate a stale fragment left from an older install.
    (refs / "stale-old.md").write_text("stale\n", encoding="utf-8")
    assert (refs / "stale-old.md").exists()

    _install(tmp_path, platform)

    # The stale fragment is gone; the packaged ones are present.
    assert not (refs / "stale-old.md").exists()
    assert (refs / "extraction-spec.md").exists()
    assert (refs / "query.md").exists()
    assert not (skill_dir / "references.tmp").exists()


def test_uninstall_removes_references_then_walks_dirs(tmp_path, fake_bundle):
    """Uninstall rmtrees references/ before the dir walk so the tree is cleared."""
    platform = fake_bundle
    _install(tmp_path, platform)
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    assert (skill_dir / "references").is_dir()

    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        removed = mainmod._remove_skill_file(platform)

    assert removed
    assert not skill_dir.exists()
    # The 3-level walk collapsed the now-empty skill dirs.
    assert not (tmp_path / ".claude" / "skills").exists()


def test_check_skill_version_warns_on_missing_references(tmp_path, fake_bundle, capsys):
    """If SKILL.md links references/ but the dir is gone, warn to repair."""
    platform = fake_bundle
    _install(tmp_path, platform)
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    skill = skill_dir / "SKILL.md"
    # Force the body to reference the sidecar, then delete the sidecar.
    skill.write_text("See references/extraction-spec.md for the schema.\n", encoding="utf-8")
    import shutil
    shutil.rmtree(skill_dir / "references")

    mainmod._check_skill_version(skill)

    err = capsys.readouterr().err
    assert "references/ sidecar is missing" in err


def test_hard_fail_when_declared_bundle_missing(tmp_path, monkeypatch):
    """skills/ present but a declared bundle absent is a packaging error: exit 1."""
    # Stage a skills/ root with a DIFFERENT bundle so the root exists but
    # claude's declared references dir is missing.
    skills_root = PKG_DIR / "skills"
    created_root = not skills_root.exists()
    other = skills_root / "decoy" / "references"
    other.mkdir(parents=True, exist_ok=True)
    (other / "x.md").write_text("x\n", encoding="utf-8")
    try:
        with pytest.raises(SystemExit) as exc:
            with patch("graphify.__main__.Path.home", return_value=tmp_path):
                monkeypatch.chdir(tmp_path)
                mainmod._copy_skill_file("claude")
        assert exc.value.code == 1
    finally:
        import shutil
        if created_root:
            shutil.rmtree(skills_root, ignore_errors=True)
        else:
            shutil.rmtree(skills_root / "decoy", ignore_errors=True)


def test_no_skills_dir_ships_monolith_only(tmp_path):
    """With no skills/ root, every progressive host gets a plain SKILL.md."""
    # The package ships no skills/ dir in this phase.
    assert not (PKG_DIR / "skills").exists(), "this test assumes no bundles ship yet"
    _install(tmp_path, "claude")
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    assert (skill_dir / "SKILL.md").exists()
    assert not (skill_dir / "references").exists()
    # Byte-identical to the packaged monolithic skill.md.
    assert (skill_dir / "SKILL.md").read_bytes() == (PKG_DIR / "skill.md").read_bytes()


def test_pyproject_declares_references_globs():
    """package-data must declare the split-bundle globs so they ship once authored."""
    import tomllib

    pyproject = PKG_DIR.parent / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml not adjacent to package (installed wheel)")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    pkg_data = data["tool"]["setuptools"]["package-data"]["graphify"]
    assert "skills/*/SKILL.md" in pkg_data
    assert "skills/*/references/*.md" in pkg_data


def test_monolith_install_clears_orphan_references(tmp_path, fake_bundle):
    """A monolith platform install removes any orphan references/ left behind."""
    # aider is a monolith (no skill_refs). Seed an orphan references/ dir at its
    # destination, then install and confirm it is cleared.
    skill_dst = tmp_path / ".aider" / "graphify" / "SKILL.md"
    orphan = skill_dst.parent / "references"
    orphan.mkdir(parents=True)
    (orphan / "leftover.md").write_text("leftover\n", encoding="utf-8")
    _install(tmp_path, "aider")
    assert skill_dst.exists()
    assert not orphan.exists()


@pytest.fixture()
def fake_amp_bundle():
    """Stage a fake references/ bundle for amp inside the real package."""
    bundle = mainmod._PLATFORM_CONFIG["amp"]["skill_refs"]
    skills_root = PKG_DIR / "skills"
    refs_dir = skills_root / bundle / "references"
    created_root = not skills_root.exists()
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "exports.md").write_text("# amp exports fragment\n", encoding="utf-8")
    try:
        yield
    finally:
        import shutil
        if created_root:
            shutil.rmtree(skills_root, ignore_errors=True)
        else:
            shutil.rmtree(skills_root / bundle, ignore_errors=True)


def test_amp_user_install_carries_references(tmp_path, monkeypatch, fake_amp_bundle):
    """amp is progressive: its corrected user dir also gets the references/ sidecar."""
    from graphify.__main__ import main

    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "amp", "install"])
        main()
        skill_dir = home / ".config" / "agents" / "skills" / "graphify"
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "references" / "exports.md").exists()

        monkeypatch.setattr(sys, "argv", ["graphify", "amp", "uninstall"])
        main()

    assert not skill_dir.exists()
