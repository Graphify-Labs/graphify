"""Line-ending preservation for the install/uninstall markdown writers (#4360).

#3741 stopped the always-on registration and the Gemini writer from translating
line endings on *write* by passing ``newline=""``. But those paths, and every
other md writer listed in #4360, still read through ``Path.read_text``, which
opens in universal-newline mode and folds every ``\\r\\n`` to ``\\n`` before the
merge happens. A later plain ``write_text`` then re-emitted the platform
default, so a read-modify-write normalised the WHOLE file: on Windows an LF file
gained CRLF on every line, and on Linux a CRLF file lost its ``\\r``. For
``CLAUDE.md``/``AGENTS.md``, which are shared and reviewed, that buries the real
one-block change in an every-line diff and can trip line-ending checks.

These tests pin the contract for every writer: an LF file stays LF, a CRLF file
stays CRLF, and install-then-uninstall returns the exact original bytes. The bug
is observable in the file bytes on every host OS (LF input fails on Windows,
CRLF input fails on Linux), so these do not depend on the platform running them.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import install as install_mod

LF = "\n"
CRLF = "\r\n"
USER_BODY = ["# My rules", "", "some notes"]
NEWLINES = [pytest.param(LF, id="lf"), pytest.param(CRLF, id="crlf")]


def _seed(path: Path, newline: str) -> bytes:
    """Write a small user-owned file with *newline* endings; return its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((newline.join(USER_BODY) + newline).encode("utf-8"))
    return path.read_bytes()


def _assert_single_ending(data: bytes, newline: str) -> None:
    """Assert every line in *data* uses *newline* (no normalisation, no mixing)."""
    lf = data.count(b"\n")
    crlf = data.count(b"\r\n")
    if newline == CRLF:
        assert lf == crlf, f"file is not wholly CRLF: {lf} LF vs {crlf} CRLF"
    else:
        assert crlf == 0, f"an LF file gained {crlf} CRLF endings"


@pytest.fixture
def patched_home(tmp_path, monkeypatch):
    """Keep user-scope skill writes inside tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    with patch("graphify.install.Path.home", return_value=home):
        yield home


# (id, instructions file relative to the project, install, uninstall)
_WRITERS = [
    (
        "claude",
        "CLAUDE.md",
        lambda project: install_mod.claude_install(project),
        lambda project: install_mod.claude_uninstall(project, project=True),
        install_mod._CLAUDE_MD_MARKER,
    ),
    (
        "agents",
        "AGENTS.md",
        lambda project: install_mod._agents_install(project, "codex"),
        lambda project: install_mod._agents_uninstall(project, platform="codex"),
        install_mod._AGENTS_MD_MARKER,
    ),
    (
        "gemini",
        "GEMINI.md",
        lambda project: install_mod.gemini_install(project, project=True),
        lambda project: install_mod.gemini_uninstall(project, project=True),
        install_mod._GEMINI_MD_MARKER,
    ),
    (
        "codebuddy",
        "CODEBUDDY.md",
        lambda project: install_mod.codebuddy_install(project),
        lambda project: install_mod.codebuddy_uninstall(project, project=True),
        install_mod._CODEBUDDY_MD_MARKER,
    ),
    (
        "vscode",
        ".github/copilot-instructions.md",
        lambda project: install_mod.vscode_install(project),
        lambda project: install_mod.vscode_uninstall(project),
        install_mod._VSCODE_INSTRUCTIONS_MARKER,
    ),
]
_WRITER_IDS = [w[0] for w in _WRITERS]


@pytest.mark.parametrize("newline", NEWLINES)
@pytest.mark.parametrize("name,rel,install,uninstall,marker", _WRITERS, ids=_WRITER_IDS)
def test_md_writer_round_trip_preserves_line_endings(
    tmp_path, patched_home, newline, name, rel, install, uninstall, marker
):
    """Install then uninstall leaves the file byte-identical to the original."""
    project = tmp_path / "proj"
    project.mkdir()
    target = project / rel
    original = _seed(target, newline)

    install(project)
    after_install = target.read_bytes()
    assert marker in after_install.decode("utf-8"), "graphify block was not written"
    _assert_single_ending(after_install, newline)

    uninstall(project)
    assert target.read_bytes() == original


@pytest.mark.parametrize("newline", NEWLINES)
def test_always_on_registration_round_trip_preserves_line_endings(tmp_path, newline):
    """_register_always_on_block / _remove_claude_skill_registration (#4360)."""
    project = tmp_path / "proj"
    md = project / ".claude" / "CLAUDE.md"
    original = _seed(md, newline)

    install_mod._register_always_on_block(
        md, "  CLAUDE.md        ->  ", install_mod._skill_registration()
    )
    _assert_single_ending(md.read_bytes(), newline)
    assert install_mod._SKILL_REGISTRATION_MARKER in md.read_text(encoding="utf-8")

    install_mod._remove_claude_skill_registration(project)
    assert md.read_bytes() == original


@pytest.mark.parametrize("newline", NEWLINES)
def test_strip_graphify_md_section_preserves_line_endings(tmp_path, newline):
    """The CLAUDE.md-variant uninstall writer strips only graphify's section."""
    target = tmp_path / "CLAUDE.local.md"
    text = newline.join(
        ["# local", "", "## graphify", "- managed line", "", "## other", "keep me"]
    ) + newline
    target.write_bytes(text.encode("utf-8"))

    assert install_mod._strip_graphify_md_section(target) is True

    data = target.read_bytes()
    _assert_single_ending(data, newline)
    remaining = data.decode("utf-8")
    assert "## graphify" not in remaining
    assert "keep me" in remaining and "local" in remaining


def test_new_instructions_file_is_written_lf(tmp_path, patched_home):
    """A fresh file has no convention to preserve, so graphify writes LF on every
    host -- matching the other install writers (#4360/#3668)."""
    project = tmp_path / "proj"
    project.mkdir()

    install_mod.vscode_install(project)

    data = (project / ".github" / "copilot-instructions.md").read_bytes()
    assert data, "the instructions file was not created"
    assert b"\r\n" not in data, "a new file must not be written with platform CRLF"


def test_read_keep_newline_reports_and_normalises(tmp_path):
    path = tmp_path / "f.md"
    path.write_bytes(b"a\r\nb\r\n")
    text, newline = install_mod._read_keep_newline(path)
    assert text == "a\nb\n"
    assert newline == CRLF

    path.write_bytes(b"a\nb\n")
    text, newline = install_mod._read_keep_newline(path)
    assert text == "a\nb\n"
    assert newline == LF


def test_write_keep_newline_never_translates(tmp_path):
    path = tmp_path / "f.md"
    install_mod._write_keep_newline(path, "a\nb\n", CRLF)
    assert path.read_bytes() == b"a\r\nb\r\n"
    install_mod._write_keep_newline(path, "a\nb\n", LF)
    assert path.read_bytes() == b"a\nb\n"
    install_mod._write_keep_newline(path, "x\n")  # default is LF
    assert path.read_bytes() == b"x\n"
