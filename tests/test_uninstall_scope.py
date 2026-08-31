"""Scope regression tests for the uninstall API trap (issue #2215).

`X_uninstall(project_dir)` used to delete the USER-GLOBAL skill tree because
`_platform_skill_destination` honors ``project_dir`` only when ``project=True``.
These tests pin the fixed contract:

- bare call            -> global skill removed (CLI behavior unchanged)
- fn(pd)               -> project-scoped, global untouched (trap closed)
- fn(pd, project=True) -> project only
- fn(pd, remove_user_skill=True) -> global removed, project tree untouched
- `graphify uninstall --project` for codebuddy no longer nukes the global skill
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.install import (
    _project_uninstall,
    claude_uninstall,
    codebuddy_uninstall,
    gemini_uninstall,
)

PLATFORMS = [
    pytest.param(claude_uninstall, "claude", ".claude", id="claude"),
    pytest.param(gemini_uninstall, "gemini", ".gemini", id="gemini"),
    pytest.param(codebuddy_uninstall, "codebuddy", ".codebuddy", id="codebuddy"),
]


def _plant_skill_tree(root: Path, dot_dir: str) -> Path:
    """Create <root>/<dot_dir>/skills/graphify/{SKILL.md, references/x.md, .graphify_version}."""
    skill_dir = root / dot_dir / "skills" / "graphify"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# graphify skill\n", encoding="utf-8")
    (skill_dir / "references" / "x.md").write_text("ref\n", encoding="utf-8")
    (skill_dir / ".graphify_version").write_text("0.0.0-test", encoding="utf-8")
    return skill_dir


@pytest.mark.parametrize("uninstall_fn,platform,dot_dir", PLATFORMS)
def test_project_dir_call_never_touches_global(uninstall_fn, platform, dot_dir, tmp_path):
    """fn(project_dir) removes only the project skill tree (#2215 trap closed)."""
    global_tree = _plant_skill_tree(Path.home(), dot_dir)
    proj_dir = tmp_path / "proj"
    project_tree = _plant_skill_tree(proj_dir, dot_dir)

    uninstall_fn(proj_dir)

    assert (global_tree / "SKILL.md").exists(), "global skill deleted by project-scoped uninstall"
    assert (global_tree / "references" / "x.md").exists()
    assert (global_tree / ".graphify_version").exists()
    assert not (project_tree / "SKILL.md").exists()
    assert not project_tree.exists()


@pytest.mark.parametrize("uninstall_fn,platform,dot_dir", PLATFORMS)
def test_bare_call_still_removes_global(uninstall_fn, platform, dot_dir, tmp_path, monkeypatch):
    """fn() with no args keeps the historical CLI behavior: global skill removed."""
    global_tree = _plant_skill_tree(Path.home(), dot_dir)
    cwd = tmp_path / "empty-cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    uninstall_fn()

    assert not (global_tree / "SKILL.md").exists()
    assert not global_tree.exists()


@pytest.mark.parametrize("uninstall_fn,platform,dot_dir", PLATFORMS)
def test_remove_user_skill_opt_in_with_project_dir(uninstall_fn, platform, dot_dir, tmp_path):
    """fn(pd, remove_user_skill=True) removes the global skill, leaves the project tree."""
    global_tree = _plant_skill_tree(Path.home(), dot_dir)
    proj_dir = tmp_path / "proj"
    project_tree = _plant_skill_tree(proj_dir, dot_dir)

    uninstall_fn(proj_dir, remove_user_skill=True)

    assert not (global_tree / "SKILL.md").exists()
    assert not global_tree.exists()
    assert (project_tree / "SKILL.md").exists()
    assert (project_tree / "references" / "x.md").exists()


@pytest.mark.parametrize("uninstall_fn,platform,dot_dir", PLATFORMS)
def test_project_true_removes_only_project_tree(uninstall_fn, platform, dot_dir, tmp_path):
    """fn(pd, project=True) removes only the project skill tree."""
    global_tree = _plant_skill_tree(Path.home(), dot_dir)
    proj_dir = tmp_path / "proj"
    project_tree = _plant_skill_tree(proj_dir, dot_dir)

    uninstall_fn(proj_dir, project=True)

    assert (global_tree / "SKILL.md").exists()
    assert not (project_tree / "SKILL.md").exists()
    assert not project_tree.exists()


def test_project_uninstall_codebuddy_spares_global(tmp_path):
    """`graphify uninstall --project` (codebuddy branch) must not delete ~/.codebuddy (#2215)."""
    global_tree = _plant_skill_tree(Path.home(), ".codebuddy")
    proj_dir = tmp_path / "proj"
    project_tree = _plant_skill_tree(proj_dir, ".codebuddy")

    _project_uninstall("codebuddy", proj_dir)

    assert (global_tree / "SKILL.md").exists(), "CLI --project uninstall deleted the global codebuddy skill"
    assert (global_tree / ".graphify_version").exists()
    assert not (project_tree / "SKILL.md").exists()
    assert not project_tree.exists()
