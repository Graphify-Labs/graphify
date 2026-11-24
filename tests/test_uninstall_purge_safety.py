"""`graphify uninstall --purge` must only ever delete the output directory.

Regression: a set-but-empty ``GRAPHIFY_OUT`` (``GRAPHIFY_OUT=`` in a ``.env``,
docker-compose or CI config) or ``GRAPHIFY_OUT=.`` made the purge target
``<project>/""`` == the project itself, and ``rmtree`` deleted the whole project.
Two independent layers guard against it: ``paths._out_from_env`` never yields
the project (or a parent) as the output dir, and ``uninstall_all`` refuses to
purge a target that would take the project, home or a filesystem root with it,
even when an absolute ``GRAPHIFY_OUT`` bypasses the first layer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import graphify.hooks as hooks_mod
import graphify.install as install_mod
from graphify import paths

_PLATFORM_UNINSTALLERS = [
    "claude_uninstall",
    "codebuddy_uninstall",
    "gemini_uninstall",
    "vscode_uninstall",
    "_cursor_uninstall",
    "_kiro_uninstall",
    "_antigravity_uninstall",
    "_agents_uninstall",
    "_remove_skill_file",
    "_uninstall_opencode_plugin",
    "_uninstall_codex_hook",
]


@pytest.fixture
def env(tmp_path, monkeypatch, _sandbox_home):
    """A throwaway project and every platform uninstaller stubbed so only the
    purge step can touch the filesystem. HOME / USERPROFILE / Path.home() already
    point at the conftest sandbox home. Returns the stub call log."""
    home = _sandbox_home
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)

    project = tmp_path / "parent" / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "important.py").write_text("x = 1\n", encoding="utf-8")
    (project / "graphify-out").mkdir()
    (project / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    calls: list[str] = []
    for name in _PLATFORM_UNINSTALLERS:
        monkeypatch.setattr(install_mod, name, lambda *a, _n=name, **k: calls.append(_n))
    monkeypatch.setattr(hooks_mod, "uninstall", lambda *a, **k: calls.append("hooks.uninstall"))
    # Run from outside the project: Windows cannot rmtree the current directory.
    monkeypatch.chdir(tmp_path)
    return {"project": project, "home": home, "calls": calls, "tmp": tmp_path}


def _purge_with_env(monkeypatch, project, value):
    """Run the real purge with GRAPHIFY_OUT resolved exactly as paths.py does at
    import time (no module reload, so no state leaks into other tests)."""
    monkeypatch.setenv("GRAPHIFY_OUT", value)
    monkeypatch.setattr(install_mod, "_GRAPHIFY_OUT", paths._out_from_env())
    install_mod.uninstall_all(project_dir=project, purge=True)


def _assert_project_intact(project):
    assert project.is_dir()
    assert (project / "src" / "important.py").is_file()


# -- Layer 1: paths._out_from_env -----------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_graphify_out_falls_back_to_default(monkeypatch, value):
    monkeypatch.setenv("GRAPHIFY_OUT", value)
    assert paths._out_from_env() == "graphify-out"


@pytest.mark.parametrize("value", [".", "./", "..", "../..", " . "])
def test_project_or_parent_graphify_out_falls_back_with_warning(monkeypatch, capsys, value):
    monkeypatch.setenv("GRAPHIFY_OUT", value)
    assert paths._out_from_env() == "graphify-out"
    assert "warning: GRAPHIFY_OUT=" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["custom-out", "../shared-out", "out/graphify"])
def test_valid_relative_graphify_out_is_kept(monkeypatch, capsys, value):
    monkeypatch.setenv("GRAPHIFY_OUT", value)
    assert paths._out_from_env() == value
    assert capsys.readouterr().err == ""


def test_graphify_out_is_stripped(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_OUT", "  custom-out  ")
    assert paths._out_from_env() == "custom-out"


def test_absolute_graphify_out_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHIFY_OUT", str(tmp_path / "shared-out"))
    assert paths._out_from_env() == str(tmp_path / "shared-out")


def test_unset_graphify_out_is_default(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    assert paths._out_from_env() == "graphify-out"


# -- End to end: the purge never deletes the project ------------------------


@pytest.mark.parametrize("value", ["", "   ", ".", ".."])
def test_purge_with_bad_graphify_out_only_removes_default_out(env, monkeypatch, value):
    project = env["project"]
    _purge_with_env(monkeypatch, project, value)
    _assert_project_intact(project)
    assert not (project / "graphify-out").exists()
    # ".." must not have reached the parent of the project either.
    assert project.parent.is_dir()


def test_purge_default_removes_only_graphify_out(env):
    project = env["project"]
    install_mod.uninstall_all(project_dir=project, purge=True)
    _assert_project_intact(project)
    assert not (project / "graphify-out").exists()


def test_purge_custom_relative_out(env, monkeypatch):
    project = env["project"]
    (project / "custom-out").mkdir()
    (project / "custom-out" / "graph.json").write_text("{}", encoding="utf-8")
    _purge_with_env(monkeypatch, project, "custom-out")
    _assert_project_intact(project)
    assert not (project / "custom-out").exists()
    assert (project / "graphify-out").exists()  # not the configured dir


def test_purge_custom_absolute_out_outside_project(env, monkeypatch):
    """A shared output dir outside the project (#686, #1423) stays purgeable."""
    project = env["project"]
    shared = env["tmp"] / "shared-out"
    shared.mkdir()
    (shared / "graph.json").write_text("{}", encoding="utf-8")
    _purge_with_env(monkeypatch, project, str(shared))
    _assert_project_intact(project)
    assert not shared.exists()


# -- Layer 2: unsafe targets are refused before anything changes ------------


def _assert_refused(env, capsys, excinfo):
    assert excinfo.value.code == 1
    assert "refusing --purge" in capsys.readouterr().err
    _assert_project_intact(env["project"])
    assert (env["project"] / "graphify-out" / "graph.json").is_file()
    assert env["calls"] == [], "a refused purge must not run any uninstaller"


def test_purge_refuses_absolute_out_equal_to_project(env, monkeypatch, capsys):
    with pytest.raises(SystemExit) as excinfo:
        _purge_with_env(monkeypatch, env["project"], str(env["project"]))
    _assert_refused(env, capsys, excinfo)


def test_purge_refuses_absolute_out_parent_of_project(env, monkeypatch, capsys):
    with pytest.raises(SystemExit) as excinfo:
        _purge_with_env(monkeypatch, env["project"], str(env["project"].parent))
    _assert_refused(env, capsys, excinfo)
    assert env["project"].parent.is_dir()


def test_purge_refuses_home(env, monkeypatch, capsys):
    (env["home"] / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _purge_with_env(monkeypatch, env["project"], str(env["home"]))
    _assert_refused(env, capsys, excinfo)
    assert (env["home"] / "keep.txt").is_file()


def test_unsafe_purge_reason_rejects_filesystem_roots(env):
    """Checked on the pure helper only: a regression here must never be able to
    hand a real filesystem root to rmtree."""
    project = env["project"]
    root = Path(project.resolve().anchor)
    assert install_mod._unsafe_purge_reason(root, project) is not None
    if sys.platform == "win32":
        # A root on another drive is not a parent of the project, but still refused.
        assert install_mod._unsafe_purge_reason(Path("Z:\\"), project) == "a filesystem root"


def test_unsafe_purge_reason_allows_out_dirs(env):
    project = env["project"]
    assert install_mod._unsafe_purge_reason(project / "graphify-out", project) is None
    assert install_mod._unsafe_purge_reason(env["tmp"] / "shared-out", project) is None


@pytest.mark.parametrize("value", ["", "."])
def test_purge_refuses_project_when_layer_one_is_bypassed(env, monkeypatch, capsys, value):
    """The safety net must hold on its own, even if a bad value reaches install."""
    monkeypatch.setattr(install_mod, "_GRAPHIFY_OUT", value)
    with pytest.raises(SystemExit) as excinfo:
        install_mod.uninstall_all(project_dir=env["project"], purge=True)
    _assert_refused(env, capsys, excinfo)


def test_uninstall_without_purge_ignores_unsafe_out(env, monkeypatch):
    """The safety check gates only the purge; plain uninstall is unchanged."""
    monkeypatch.setattr(install_mod, "_GRAPHIFY_OUT", "")
    install_mod.uninstall_all(project_dir=env["project"], purge=False)
    _assert_project_intact(env["project"])
    assert "claude_uninstall" in env["calls"]
