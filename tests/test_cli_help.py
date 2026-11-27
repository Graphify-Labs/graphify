"""CLI help routing keeps detailed handlers reachable without weakening the guard."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

PYTHON = sys.executable


def _invoke_main(monkeypatch, capsys, tmp_path, args: list[str]):
    from graphify.__main__ import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", *args])
    with patch("graphify.__main__._check_skill_version"):
        main()
    return capsys.readouterr()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["tree", "--help"], "Usage: graphify tree"),
        (["tree", "-h"], "Usage: graphify tree"),
        (["reflect", "--help"], "usage: graphify reflect"),
        (["reflect", "-h"], "usage: graphify reflect"),
        (["export", "callflow-html", "--help"], "Usage: graphify export callflow-html"),
        (["export", "callflow-html", "-h"], "Usage: graphify export callflow-html"),
        (["prs", "--help"], "graphify prs — graph-aware PR dashboard"),
        (["prs", "-h"], "graphify prs — graph-aware PR dashboard"),
        (["tree", "--output", "custom.html", "--help"], "Usage: graphify tree"),
        (["reflect", "--out", "custom.md", "--help"], "usage: graphify reflect"),
        (
            ["export", "callflow-html", "--output", "custom.html", "--help"],
            "Usage: graphify export callflow-html",
        ),
        (["prs", "--repo", "owner/repo", "--help"], "graphify prs — graph-aware PR dashboard"),
        (["tree", "--output", "--help"], "Usage: graphify tree"),
        (["reflect", "--out", "--help"], "usage: graphify reflect"),
        (
            ["export", "callflow-html", "--output", "--help"],
            "Usage: graphify export callflow-html",
        ),
        (["prs", "--repo", "--help"], "graphify prs — graph-aware PR dashboard"),
    ],
)
def test_help_reaches_detailed_handler_before_argument_parsing(
    tmp_path, monkeypatch, capsys, args, expected
):
    captured = _invoke_main(monkeypatch, capsys, tmp_path, args)

    assert expected in captured.out
    assert "Run 'graphify --help'" not in captured.out
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "args",
    [
        ["tree", "-?"],
        ["benchmark", "--help"],
        ["export", "html", "--help"],
    ],
)
def test_other_help_shapes_remain_behind_universal_guard(
    tmp_path, monkeypatch, capsys, args
):
    captured = _invoke_main(monkeypatch, capsys, tmp_path, args)

    assert captured.out == "Run 'graphify --help' for full usage.\n"
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


def test_help_lists_prs_provider_and_export_formats():
    """#3140: `graphify --help` must advertise prs, provider, and all export formats."""
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"--help should exit 0: {r.stderr}"
    out = r.stdout
    assert "  prs" in out, "`graphify --help` must list prs (#3140)"
    assert "provider" in out, "`graphify --help` must list provider (#3140)"
    for fmt in (
        "html",
        "callflow-html",
        "obsidian",
        "wiki",
        "svg",
        "graphml",
        "neo4j",
        "falkordb",
    ):
        assert f"export {fmt}" in out, (
            f"`graphify --help` must list export {fmt} (#3140)"
        )
    # Silent hook internals — deliberately excluded from user-facing help.
    assert "hook-check" not in out
    assert "hook-guard" not in out


def test_help_lists_every_install_platform():
    """#4655: the `install [--platform P]` line must advertise every accepted
    `--platform` value. It is derived from the same source as `graphify install`
    usage (`[*_PLATFORM_CONFIG, "gemini", "cursor"]`), so this guards against the
    list silently drifting again (amp, copilot, kilo, kimi, antigravity-windows
    had all gone missing)."""
    import re

    from graphify.install import _PLATFORM_CONFIG

    r = subprocess.run(
        [PYTHON, "-m", "graphify", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"--help should exit 0: {r.stderr}"
    m = re.search(r"install \[--platform P\][^(]*\(([^)]*)\)", r.stdout)
    assert m, "could not find the install --platform list in `graphify --help`"
    listed = set(m.group(1).split("|"))
    for platform_name in [*_PLATFORM_CONFIG, "gemini", "cursor"]:
        assert platform_name in listed, (
            f"`graphify --help` must list the --platform value {platform_name!r} (#4655)"
        )


def test_help_lists_project_query_defaults_and_depth_range():
    result = subprocess.run([PYTHON, "-m", "graphify", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--budget N, --budget=N" in result.stdout
    assert "--depth N, --depth=N" in result.stdout
    assert "1-6 (default 2)" in result.stdout
    assert "tokens (default 2000)" in result.stdout
    assert "query_budget" in result.stdout and "query_depth" in result.stdout
    assert "selected graph project's .graphifyrc" in result.stdout
    assert "Explicit options override project values" in result.stdout
