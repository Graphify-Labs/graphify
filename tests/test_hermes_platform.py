"""Tests for the hermes platform and HERMES_HOME support.

`graphify install --platform hermes` installs the skill to:
  1. $HERMES_HOME/skills/graphify/SKILL.md  (if HERMES_HOME is set)
  2. %LOCALAPPDATA%/hermes/skills/graphify/SKILL.md  (Windows fallback)
  3. ~/.hermes/skills/graphify/SKILL.md  (POSIX fallback)
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod


# --- destination map -----------------------------------------------------------

def test_hermes_destination_respects_hermes_home(tmp_path):
    """HERMES_HOME env var overrides the default skill destination."""
    hermes_home = tmp_path / "custom-hermes"
    with patch.dict(os.environ, {"HERMES_HOME": str(hermes_home)}, clear=False):
        dst = mainmod._platform_skill_destination("hermes", project=False)
    assert dst == hermes_home / "skills" / "graphify" / "SKILL.md"


def test_hermes_destination_falls_back_windows(tmp_path):
    """Without HERMES_HOME on Windows, falls back to LOCALAPPDATA."""
    local_appdata = tmp_path / "AppData" / "Local"
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata), "HERMES_HOME": ""}):
        with patch("platform.system", return_value="Windows"):
            dst = mainmod._platform_skill_destination("hermes", project=False)
    assert dst == local_appdata / "hermes" / "skills" / "graphify" / "SKILL.md"


def test_hermes_destination_falls_back_posix(tmp_path):
    """Without HERMES_HOME on POSIX, falls back to ~/.hermes."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("platform.system", return_value="Linux"):
            with patch("graphify.__main__.Path.home", return_value=tmp_path):
                dst = mainmod._platform_skill_destination("hermes", project=False)
    assert dst == tmp_path / ".hermes" / "skills" / "graphify" / "SKILL.md"


def test_hermes_project_destination_is_dot_hermes(tmp_path):
    """Project-scope hermes skill lands at ./.hermes/skills (no HERMES_HOME impact)."""
    dst = mainmod._platform_skill_destination("hermes", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".hermes" / "skills" / "graphify" / "SKILL.md"


# --- end-to-end install --------------------------------------------------------

def _run(tmp_path, argv, home, hermes_home=None):
    """Drive main() with argv, cwd at tmp_path, and Path.home redirected."""
    old_cwd = Path.cwd()
    old_env = os.environ.copy()
    try:
        os.chdir(tmp_path)
        if hermes_home:
            os.environ["HERMES_HOME"] = str(hermes_home)
        elif "HERMES_HOME" in os.environ:
            del os.environ["HERMES_HOME"]

        with patch.object(sys, "argv", ["graphify", *argv]):
            with patch("graphify.__main__.Path.home", return_value=home):
                with patch("platform.system", return_value="Windows"):
                    mainmod.main()
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        os.chdir(old_cwd)


def test_install_platform_hermes_respects_hermes_home(tmp_path):
    """`graphify install --platform hermes` writes to $HERMES_HOME/skills/..."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    hermes_home = tmp_path / "my-hermes"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "hermes"], home, hermes_home=hermes_home)

    skill = hermes_home / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__


def test_install_platform_hermes_falls_back_windows(tmp_path):
    """Without HERMES_HOME on Windows, installs to LOCALAPPDATA/hermes/skills/..."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    local_appdata = tmp_path / "AppData" / "Local"
    home.mkdir()
    cwd.mkdir()
    local_appdata.mkdir(parents=True)

    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}, clear=False):
        _run(cwd, ["install", "--platform", "hermes"], home, hermes_home=None)

    skill = local_appdata / "hermes" / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()


def test_uninstall_platform_hermes_removes_from_hermes_home(tmp_path):
    """`graphify uninstall` clears the skill from $HERMES_HOME."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    hermes_home = tmp_path / "my-hermes"
    home.mkdir()
    cwd.mkdir()

    _run(cwd, ["install", "--platform", "hermes"], home, hermes_home=hermes_home)
    skill = hermes_home / "skills" / "graphify" / "SKILL.md"
    assert skill.exists()

    _run(cwd, ["uninstall"], home, hermes_home=hermes_home)
    assert not skill.exists()
