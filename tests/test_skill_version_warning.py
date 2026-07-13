"""Direction-aware skill-version mismatch warning (#1568).

`_check_skill_version` used to advise `graphify install` on ANY version
mismatch. But `install` writes the package's OWN bundled skill and re-stamps
the version, so when the skill on disk is NEWER than the package, following
that advice silently DOWNGRADES the skill. These tests pin that the warning is
now direction-aware: skill-older -> recommend install; skill-newer -> recommend
upgrading the package instead.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import graphify.__main__ as mainmod


def _make_skill(tmp_path: Path, stamped: str) -> Path:
    skill_dst = tmp_path / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    skill_dst.write_text("# graphify skill\n", encoding="utf-8")
    (skill_dst.parent / ".graphify_version").write_text(stamped, encoding="utf-8")
    return skill_dst


def test_version_tuple_orders_numerically():
    vt = mainmod._version_tuple
    assert vt("0.9.2") > vt("0.8.27")     # 9 > 8, not string-compared
    assert vt("0.10.0") > vt("0.9.0")     # 10 > 9
    assert vt("0.9.3") == vt("0.9.3")
    assert vt("1.0.0rc1") == vt("1.0.0")  # pre-release suffix compares by core
    assert vt("") == (0,)                 # malformed stamp degrades, no raise


def test_skill_older_than_package_recommends_install(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mainmod, "__version__", "0.9.3")
    skill_dst = _make_skill(tmp_path, "0.8.27")
    mainmod._check_skill_version(skill_dst)
    err = capsys.readouterr().err
    assert "Run 'graphify install' to update" in err
    assert "downgrade" not in err


def test_skill_newer_than_package_recommends_upgrade_not_install(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mainmod, "__version__", "0.8.27")
    skill_dst = _make_skill(tmp_path, "0.9.2")
    mainmod._check_skill_version(skill_dst)
    err = capsys.readouterr().err
    # must NOT tell the user to run install (that would downgrade the skill)
    assert "Run 'graphify install' to update" not in err
    assert "downgrade" in err
    assert "upgrade" in err.lower()


def test_matching_version_is_silent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mainmod, "__version__", "0.9.3")
    skill_dst = _make_skill(tmp_path, "0.9.3")
    mainmod._check_skill_version(skill_dst)
    assert capsys.readouterr().err == ""
