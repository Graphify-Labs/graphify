"""Tests for `graphify inspect` CLI."""
from __future__ import annotations

import pytest

import graphify.__main__ as mainmod


def _mixed_corpus(tmp_path):
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nEntry point.\n")
    (tmp_path / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


def _code_only_corpus(tmp_path):
    (tmp_path / "auth.py").write_text("def login():\n    return True\n")
    return tmp_path


def test_inspect_lists_counts_and_semantic_paths(monkeypatch, tmp_path, capsys):
    corpus = _mixed_corpus(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(corpus)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "code:" in out
    assert "docs:" in out
    assert "images:" in out
    assert "Documents:" in out
    assert "README.md" in out
    assert "Images:" in out
    assert "diagram.png" in out


def test_inspect_code_only_exits_zero_without_llm_note(monkeypatch, tmp_path, capsys):
    corpus = _code_only_corpus(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(corpus)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "code:" in out
    assert "LLM" not in out
    assert "semantic" not in out.lower()


def test_inspect_semantic_corpus_mentions_llm_note(monkeypatch, tmp_path, capsys):
    corpus = _mixed_corpus(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(corpus)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "LLM API key" in out
    assert "graphify extract" in out


def test_inspect_missing_path_exits_nonzero(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "nope"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(missing)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    assert "path not found" in capsys.readouterr().err


def test_inspect_empty_dir_prints_message_and_exits_zero(monkeypatch, tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(empty)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert out.strip() == "No supported files found."


def test_inspect_without_path_prints_usage_and_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "inspect"])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    assert "Usage: graphify inspect <path>" in capsys.readouterr().err


def test_inspect_does_not_create_graphify_out(monkeypatch, tmp_path):
    corpus = _mixed_corpus(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "inspect", str(corpus)],
    )

    mainmod.main()

    assert not (corpus / "graphify-out").exists()
