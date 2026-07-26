"""Regression tests for the repo-wide HOME sandbox (issue #2168).

The autouse ``_sandbox_home`` fixture in conftest.py must point every
home-resolution mechanism at a throwaway directory, so installers and
uninstallers exercised by the suite can never delete or rewrite the
developer's real ~/.claude, ~/.gemini, ~/.codebuddy, ~/.copilot, etc.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.__main__ import claude_uninstall

# Module import happens during collection, before any fixture runs, so this
# captures the developer's actual home directory for comparison below.
_REAL_HOME = Path(os.path.realpath(os.path.expanduser("~")))


def test_path_home_is_sandboxed(tmp_path_factory):
    home = Path(os.path.realpath(Path.home()))
    assert home != _REAL_HOME
    assert not home.is_relative_to(_REAL_HOME / ".claude")
    assert home.name.startswith("sandbox-home")
    basetemp = Path(os.path.realpath(tmp_path_factory.getbasetemp()))
    assert home.is_relative_to(basetemp)


def test_expanduser_is_sandboxed(tmp_path_factory):
    expanded = Path(os.path.realpath(os.path.expanduser("~")))
    assert expanded != _REAL_HOME
    basetemp = Path(os.path.realpath(tmp_path_factory.getbasetemp()))
    assert expanded.is_relative_to(basetemp)


def test_claude_config_dir_escape_hatch_is_cleared():
    assert "CLAUDE_CONFIG_DIR" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ


def test_global_uninstall_is_captured_by_sandbox(tmp_path, tmp_path_factory):
    """claude_uninstall deletes the *global* ~/.claude/skills/graphify tree.

    Plant that tree inside the sandbox home, run uninstall against an
    unrelated project dir, and prove the delete landed in the sandbox
    (and therefore not in the developer's real home).
    """
    skill = Path.home() / ".claude" / "skills" / "graphify" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# graphify skill (sandbox copy)\n", encoding="utf-8")

    project_dir = tmp_path / "some-project"
    project_dir.mkdir()
    claude_uninstall(project_dir)

    assert not skill.exists(), "global skill delete was not captured by the sandbox"
    # And the sandbox home itself is still inside pytest's tmp area.
    assert Path.home().is_relative_to(tmp_path_factory.getbasetemp())
