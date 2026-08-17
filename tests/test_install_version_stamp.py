"""Regression test for #2694 (version-stamp half).

`graphify install --platform X` must only advance `.graphify_version` for the
platform whose skill content it actually (re)writes. Previously it also bumped
the stamp of every *other* already-installed platform, so a platform whose
SKILL.md was left untouched carried a current stamp and its "skill is from
graphify A, package is B" staleness warning was suppressed even though the
content really was stale.
"""
from __future__ import annotations

from unittest.mock import patch

import graphify.__main__ as mainmod

# A prior graphify version stamped into an unrelated, not-reinstalled platform.
_STALE_STAMP = "0.0.1-old"


def test_install_does_not_bump_other_platforms_stamp(tmp_path, monkeypatch):
    """Installing one platform must leave a different, already-installed
    platform's `.graphify_version` untouched, so its staleness warning stays
    truthful (#2694)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    with patch("graphify.__main__.Path.home", return_value=home):
        # Simulate "codex" installed earlier at a stale version: its SKILL.md
        # content is old, and its stamp reflects that old version.
        codex_skill = mainmod._platform_skill_destination("codex", project=False)
        codex_skill.parent.mkdir(parents=True, exist_ok=True)
        codex_skill.write_text("stale skill body", encoding="utf-8")
        codex_stamp = codex_skill.parent / ".graphify_version"
        codex_stamp.write_text(_STALE_STAMP, encoding="utf-8")

        # Upgrade only the claude platform.
        mainmod.install("claude")

        # The platform we installed is stamped at the current version...
        claude_skill = mainmod._platform_skill_destination("claude", project=False)
        assert (claude_skill.parent / ".graphify_version").read_text() == mainmod.__version__

        # ...but the untouched codex platform keeps its stale stamp, so its
        # refresh warning still fires.
        assert codex_stamp.read_text() == _STALE_STAMP, (
            "installing claude must not advance codex's version stamp (#2694)"
        )


def test_stale_untouched_platform_still_emits_warning(tmp_path, monkeypatch, capsys):
    """End-to-end (#2694): after installing one platform, a different stale
    platform must actually EMIT the staleness warning — the behavior the
    over-stamping bug suppressed."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    real_check = mainmod._check_skill_version  # keep the real warner for the assertion

    with patch("graphify.__main__.Path.home", return_value=home):
        codex_skill = mainmod._platform_skill_destination("codex", project=False)
        codex_skill.parent.mkdir(parents=True, exist_ok=True)
        codex_skill.write_text("stale skill body", encoding="utf-8")
        (codex_skill.parent / ".graphify_version").write_text(_STALE_STAMP, encoding="utf-8")

        with patch.object(mainmod, "_check_skill_version", lambda _: None):
            mainmod.install("claude")  # install noise silenced

        capsys.readouterr()  # drop install output
        real_check(codex_skill)  # now run the real warner on the untouched platform

    err = capsys.readouterr().err
    assert _STALE_STAMP in err and "update" in err, (
        f"stale codex platform should warn, got stderr: {err!r}"
    )
