"""CLI help routing keeps detailed handlers reachable without weakening the guard."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


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
