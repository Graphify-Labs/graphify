from __future__ import annotations

from pathlib import Path

from graphify.detect import FileType, _is_ignored, _looks_like_paper, detect


def test_looks_like_paper_3000_char_boundary(tmp_path: Path) -> None:
    """Only the first 3000 characters are scanned for paper signals."""
    early_paper = tmp_path / "early.md"
    early_paper.write_text(
        "Abstract: we propose a method in arXiv:2401.00001.\n" + ("word " * 1000),
        encoding="utf-8",
    )
    assert _looks_like_paper(early_paper) is True

    late_signals = tmp_path / "late.md"
    late_signals.write_text(
        ("a" * 3005) + "\nAbstract: we propose a method in arXiv:2401.00001.\n",
        encoding="utf-8",
    )
    assert _looks_like_paper(late_signals) is False


def test_is_ignored_lexical_relative_boundaries(tmp_path: Path) -> None:
    """_is_ignored handles in-root, root-itself, and out-of-root paths."""
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    (root / "ignored").mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")

    patterns = [(root, "ignored/"), (root, "*.log")]
    cache: dict[Path, bool] = {}

    assert _is_ignored(root / "ignored" / "a.py", root, patterns, _cache=cache) is True
    assert _is_ignored(root / "sub" / "app.log", root, patterns, _cache=cache) is True
    assert _is_ignored(root / "sub" / "app.py", root, patterns, _cache=cache) is False
    assert _is_ignored(outside, root, patterns, _cache=cache) is False


def test_detect_rejects_outside_symlink_and_keeps_regular_file(tmp_path: Path) -> None:
    """Non-symlink fastpath keeps regular files while symlinks escaping root are rejected."""
    outside = tmp_path / "outside.py"
    outside.write_text("def secret():\n    return 1\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    inside = repo / "main.py"
    inside.write_text("def main():\n    return 0\n", encoding="utf-8")

    escape_link = repo / "escape.py"
    escape_link.symlink_to(outside)

    result = detect(repo)
    code_files = result["files"][FileType.CODE]
    assert any(p.endswith("main.py") for p in code_files)
    assert not any(p.endswith("escape.py") for p in code_files)
    assert any("escape.py" in entry for entry in result["skipped_sensitive"])
