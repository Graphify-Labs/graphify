"""Word counts and hashes do not use a process-global or filesystem cache."""

from pathlib import Path

from graphify import cache


def test_word_count_is_computed_without_application_cache(tmp_path: Path):
    path = tmp_path / "doc.txt"
    path.write_text("one two three")
    calls = 0

    def compute(value: Path) -> int:
        nonlocal calls
        calls += 1
        return len(value.read_text().split())

    assert cache.cached_word_count(path, tmp_path, compute) == 3
    assert cache.cached_word_count(path, tmp_path, compute) == 3
    assert calls == 2


def test_file_hash_is_content_deterministic_across_roots(tmp_path: Path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    path = root_a / "doc.txt"
    path.write_text("hello world\n")

    assert cache.file_hash(path, root_a) == cache.file_hash(path, root_b)
    original = cache.file_hash(path, root_a)
    path.write_text("different\n")
    assert cache.file_hash(path, root_a) != original


def test_markdown_frontmatter_does_not_invalidate_body_hash(tmp_path: Path):
    path = tmp_path / "doc.md"
    path.write_text("---\ntitle: One\n---\nBody\n")
    original = cache.file_hash(path, tmp_path)
    path.write_text("---\ntitle: Two\n---\nBody\n")

    assert cache.file_hash(path, tmp_path) == original
