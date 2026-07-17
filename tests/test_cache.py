"""Native generation-state extraction cache tests."""

from pathlib import Path

from graphify.cache import (
    _body_content,
    cached_files,
    check_semantic_cache,
    clear_cache,
    file_hash,
    load_cached,
    prune_semantic_cache,
    save_cached,
    save_semantic_cache,
)


def test_ast_cache_roundtrip_and_content_invalidation(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("x = 1\n", encoding="utf-8")
    cache: dict = {}
    result = {"nodes": [{"id": "n", "source_file": str(source)}], "edges": []}

    save_cached(source, result, root=tmp_path, cache=cache)

    loaded = load_cached(source, root=tmp_path, cache=cache)
    assert loaded == {"nodes": [{"id": "n", "source_file": str(source.resolve())}], "edges": []}
    source.write_text("x = 2\n", encoding="utf-8")
    assert load_cached(source, root=tmp_path, cache=cache) is None


def test_cache_state_contains_portable_paths_and_no_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    cache: dict = {}

    save_cached(
        source,
        {"nodes": [{"id": "n", "source_file": str(source.resolve())}], "edges": []},
        root=tmp_path,
        cache=cache,
    )

    entry = next(iter(cache.values()))
    assert entry["result"]["nodes"][0]["source_file"] == "src/sample.py"
    assert not (tmp_path / "graphify-out" / "cache").exists()


def test_semantic_cache_is_scoped_by_mode_and_prompt(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Doc\nBody\n", encoding="utf-8")
    result = [{"id": "doc", "source_file": "doc.md"}]
    cache: dict = {}

    assert save_semantic_cache(
        result, [], root=tmp_path, allowed_source_files=[source],
        mode="deep", prompt="prompt-a", cache=cache,
    ) == 1
    nodes, _, _, misses = check_semantic_cache(
        [str(source)], cache, root=tmp_path, mode="deep", prompt="prompt-a"
    )
    assert [node["id"] for node in nodes] == ["doc"]
    assert nodes[0]["source_file"] == str(source.resolve())
    assert misses == []
    assert check_semantic_cache(
        [str(source)], cache, root=tmp_path, mode=None, prompt="prompt-a"
    )[3] == [str(source)]
    assert check_semantic_cache(
        [str(source)], cache, root=tmp_path, mode="deep", prompt="prompt-b"
    )[3] == [str(source)]


def test_partial_semantic_entry_is_a_miss(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("body\n", encoding="utf-8")
    cache: dict = {}
    save_semantic_cache(
        [{"id": "doc", "source_file": "doc.md"}], [], root=tmp_path,
        allowed_source_files=[source], partial_source_files=["doc.md"], cache=cache,
    )
    assert check_semantic_cache([str(source)], cache, root=tmp_path)[3] == [str(source)]


def test_cached_files_clear_and_prune(tmp_path: Path) -> None:
    ast = tmp_path / "a.py"
    semantic = tmp_path / "b.md"
    ast.write_text("pass\n", encoding="utf-8")
    semantic.write_text("body\n", encoding="utf-8")
    cache: dict = {}
    save_cached(ast, {"nodes": [], "edges": []}, root=tmp_path, cache=cache)
    save_semantic_cache(
        [{"id": "b", "source_file": "b.md"}], [], root=tmp_path,
        allowed_source_files=[semantic], cache=cache,
    )
    hashes = cached_files(cache)
    assert file_hash(ast) in hashes
    assert file_hash(semantic) in hashes
    assert prune_semantic_cache(cache, {"not-live"}) == 1
    assert len(cache) == 1
    clear_cache(cache)
    assert cache == {}


def test_markdown_frontmatter_only_change_keeps_hash(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("---\nreviewed: one\n---\n\nBody", encoding="utf-8")
    first = file_hash(source)
    source.write_text("---\nreviewed: two\n---\n\nBody", encoding="utf-8")
    assert file_hash(source) == first
    source.write_text("---\nreviewed: two\n---\n\nChanged", encoding="utf-8")
    assert file_hash(source) != first


def test_frontmatter_delimiters_must_be_whole_lines() -> None:
    content = b"----\nIntro\n---\nbody"
    assert _body_content(content) == content
    assert _body_content(b"---\ntitle: Test\n---\nbody") == b"\nbody"
    assert _body_content(b"---\ntitle: Test\n--- not close\nbody") == b"---\ntitle: Test\n--- not close\nbody"
