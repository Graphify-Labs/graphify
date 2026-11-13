"""`graphify clone` multi-URL support (#2703).

The clone command used to silently swallow every URL after the first: a user
who typed `graphify clone url1 url2` got only url1 cloned and no indication
that url2 was dropped. Multi-repo analysis is the exact workflow issue #2703
asks about, so extra URLs are now cloned in turn and each destination path is
printed on its own line. Unknown flags are rejected instead of skipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from graphify import cli


def _stub_clone(monkeypatch):
    calls: list[tuple[str, str | None, Path | None]] = []

    def fake(url, branch=None, out_dir=None):
        calls.append((url, branch, out_dir))
        return Path(f"/tmp/fake/{url.rsplit('/', 1)[-1]}")

    monkeypatch.setattr(cli, "_clone_repo", fake)
    return calls


def test_clone_multiple_urls_are_all_cloned(monkeypatch, capsys):
    calls = _stub_clone(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "clone",
            "https://github.com/foo/bar",
            "https://github.com/baz/qux",
        ],
    )
    cli.dispatch_command("clone")
    assert [c[0] for c in calls] == [
        "https://github.com/foo/bar",
        "https://github.com/baz/qux",
    ]
    out = capsys.readouterr().out.splitlines()
    assert "/tmp/fake/bar" in out
    assert "/tmp/fake/qux" in out


def test_clone_single_url_still_works(monkeypatch, capsys):
    calls = _stub_clone(monkeypatch)
    monkeypatch.setattr(
        sys, "argv", ["graphify", "clone", "https://github.com/foo/bar"]
    )
    cli.dispatch_command("clone")
    assert calls == [("https://github.com/foo/bar", None, None)]
    assert "/tmp/fake/bar" in capsys.readouterr().out


def test_clone_branch_flag_applies_to_all(monkeypatch):
    calls = _stub_clone(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "clone",
            "https://github.com/foo/bar",
            "https://github.com/baz/qux",
            "--branch",
            "dev",
        ],
    )
    cli.dispatch_command("clone")
    assert [c[1] for c in calls] == ["dev", "dev"]


def test_clone_rejects_out_with_multiple_urls(monkeypatch, capsys):
    _stub_clone(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "clone",
            "https://github.com/foo/bar",
            "https://github.com/baz/qux",
            "--out",
            "/tmp/dest",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.dispatch_command("clone")
    assert exc.value.code == 1
    assert "--out" in capsys.readouterr().err


def test_clone_rejects_unknown_flag(monkeypatch, capsys):
    _stub_clone(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "clone", "https://github.com/foo/bar", "--nope"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.dispatch_command("clone")
    assert exc.value.code == 1
    assert "--nope" in capsys.readouterr().err
