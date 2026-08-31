"""#3144: the stale-skill warning must be actionable, and local SKILL.md
edits must not vanish without a trace.

A plain `graphify install` refreshes only the detected platform, so a stale
`.graphify_version` at ANOTHER platform's destination made the warning
permanent: it named no path, its advice ("run graphify install") did not
touch that copy, and only editing the marker by hand cleared it. And a
reinstall replaced a user-edited SKILL.md wholesale — no diff, no prompt,
no backup — while printing a line that read like a successful no-op.
"""
from __future__ import annotations

import sys

import pytest

import graphify.__main__ as mainmod
from graphify.install import __version__
from graphify.install import _copy_skill_file, _platform_skill_destination


# ---------------------------------------------------------------------------
# The warning
# ---------------------------------------------------------------------------

def _stale(tmp_path):
    d = tmp_path / "skills" / "graphify"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: graphify\n---\nbody\n", encoding="utf-8")
    (d / ".graphify_version").write_text("0.8.36", encoding="utf-8")
    return d / "SKILL.md"


def test_the_warning_names_the_stale_destination_and_the_exact_command(tmp_path, capsys):
    mainmod._check_skill_version(_stale(tmp_path), platform_names=["antigravity"])
    err = capsys.readouterr().err
    assert "0.8.36" in err and __version__ in err
    assert str(tmp_path / "skills" / "graphify") in err, "the stale path must be named"
    assert "graphify install --platform antigravity" in err
    assert "only the detected platform" in err


def test_without_a_platform_name_the_generic_command_is_kept(tmp_path, capsys):
    mainmod._check_skill_version(_stale(tmp_path))
    err = capsys.readouterr().err
    assert "graphify install" in err


def test_a_current_skill_stays_silent(tmp_path, capsys):
    skill = _stale(tmp_path)
    (skill.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    mainmod._check_skill_version(skill, platform_names=["claude"])
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# The backup
# ---------------------------------------------------------------------------

@pytest.fixture
def sandbox_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    if sys.platform == "win32":
        monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    return home


def test_a_locally_edited_skill_is_backed_up_and_announced(sandbox_home, capsys):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    assert dst.exists()
    original = dst.read_text(encoding="utf-8")
    dst.write_text(original + "\nCUSTOM LOCAL EDIT\n", encoding="utf-8")
    capsys.readouterr()

    _copy_skill_file("claude")
    out = capsys.readouterr().out
    backup = dst.with_suffix(dst.suffix + ".bak")
    assert backup.exists(), "the previous copy must be kept"
    assert "CUSTOM LOCAL EDIT" in backup.read_text(encoding="utf-8")
    assert "CUSTOM LOCAL EDIT" not in dst.read_text(encoding="utf-8")
    assert "previous copy" in out and str(backup) in out


def test_an_unmodified_reinstall_writes_no_backup(sandbox_home, capsys):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    capsys.readouterr()
    _copy_skill_file("claude")
    out = capsys.readouterr().out
    assert not dst.with_suffix(dst.suffix + ".bak").exists()
    assert "previous copy" not in out


def test_the_version_stamp_is_written_beside_the_skill(sandbox_home):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    assert (dst.parent / ".graphify_version").read_text(encoding="utf-8") == __version__
