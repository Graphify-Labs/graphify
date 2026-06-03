"""Tests for graphify/cache.py."""
import pytest
from pathlib import Path
from graphify.cache import file_hash, cache_dir, load_cached, save_cached, cached_files, clear_cache, _body_content


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world")
    return f


@pytest.fixture
def cache_root(tmp_path):
    return tmp_path


def test_file_hash_consistent(tmp_file):
    """Same file gives same hash on repeated calls."""
    h1 = file_hash(tmp_file)
    h2 = file_hash(tmp_file)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA256 hex digest length


def test_file_hash_changes(tmp_path):
    """Different file contents give different hashes."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content one")
    f2.write_text("content two")
    assert file_hash(f1) != file_hash(f2)


def test_cache_roundtrip(tmp_file, cache_root):
    """Save then load returns the same result dict."""
    result = {"nodes": [{"id": "n1", "label": "Node1"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)
    loaded = load_cached(tmp_file, root=cache_root)
    assert loaded == result


def test_cache_miss_on_change(tmp_file, cache_root):
    """After file content changes, load_cached returns None."""
    result = {"nodes": [], "edges": [{"source": "a", "target": "b"}]}
    save_cached(tmp_file, result, root=cache_root)
    # Modify the file
    tmp_file.write_text("completely different content")
    assert load_cached(tmp_file, root=cache_root) is None


def test_cached_files(tmp_path, cache_root):
    """cached_files returns the set of cached hashes."""
    f1 = tmp_path / "file1.py"
    f2 = tmp_path / "file2.py"
    f1.write_text("alpha")
    f2.write_text("beta")

    save_cached(f1, {"nodes": [], "edges": []}, root=cache_root)
    save_cached(f2, {"nodes": [], "edges": []}, root=cache_root)

    hashes = cached_files(cache_root)
    assert file_hash(f1, cache_root) in hashes
    assert file_hash(f2, cache_root) in hashes


def test_clear_cache(tmp_file, cache_root):
    """clear_cache removes all .json files from graphify-out/cache/ (all subdirs)."""
    save_cached(tmp_file, {"nodes": [], "edges": []}, root=cache_root)
    # Since v0.5.3 entries go into cache/ast/, not the flat cache/ dir
    cache_base = cache_root / "graphify-out" / "cache"
    assert len(list(cache_base.rglob("*.json"))) > 0
    clear_cache(cache_root)
    assert len(list(cache_base.rglob("*.json"))) == 0


def test_md_frontmatter_only_change_same_hash(tmp_path):
    """Changing only frontmatter fields in a .md file does not change the hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nBody text.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-04-09\n---\n\n# Title\n\nBody text.")
    h2 = file_hash(f)
    assert h1 == h2


def test_md_body_change_different_hash(tmp_path):
    """Changing the body of a .md file produces a different hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nOriginal body.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nChanged body.")
    h2 = file_hash(f)
    assert h1 != h2


def test_md_no_frontmatter_hashed_normally(tmp_path):
    """A .md file with no frontmatter is hashed by its full content."""
    f = tmp_path / "doc.md"
    f.write_text("# Just a heading\n\nNo frontmatter here.")
    h1 = file_hash(f)
    f.write_text("# Just a heading\n\nDifferent content.")
    h2 = file_hash(f)
    assert h1 != h2


def test_non_md_file_hashed_fully(tmp_path):
    """Non-.md files are still hashed by their full content."""
    f = tmp_path / "script.py"
    f.write_text("# comment\nx = 1")
    h1 = file_hash(f)
    f.write_text("# changed comment\nx = 1")
    h2 = file_hash(f)
    assert h1 != h2


def test_body_content_strips_frontmatter():
    """_body_content correctly strips YAML frontmatter."""
    content = b"---\ntitle: Test\n---\n\nActual body."
    assert _body_content(content) == b"\n\nActual body."


def test_body_content_no_frontmatter():
    """_body_content returns content unchanged when no frontmatter present."""
    content = b"No frontmatter here."
    assert _body_content(content) == content


# --- #777: portable cache source_file fields --------------------------------
# ``save_cached`` relativizes ``source_file`` entries inside the cache file
# so a committed ``graphify-out/cache/`` is portable across machines and
# CI runners. ``load_cached`` re-absolutizes them so consumers (extract,
# merge into graph.json) see the same shape that fresh extraction emits.

def test_save_cached_relativizes_source_file(tmp_path):
    """The on-disk cache JSON contains forward-slash relative source_file
    entries — no absolute prefix from the saving machine leaks in."""
    import json
    from graphify.cache import save_cached, file_hash, cache_dir

    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "foo.py"
    src.write_text("def x(): pass\n")
    abs_src = str(src.resolve())
    result = {
        "nodes": [{"id": "n1", "label": "foo", "source_file": abs_src}],
        "edges": [{"source": "n1", "target": "n1", "source_file": abs_src}],
    }
    save_cached(src, result, root=tmp_path, kind="ast")

    h = file_hash(src, tmp_path)
    entry = cache_dir(tmp_path, "ast") / f"{h}.json"
    on_disk = json.loads(entry.read_text(encoding="utf-8"))
    node_sources = {n["source_file"] for n in on_disk["nodes"]}
    edge_sources = {e["source_file"] for e in on_disk["edges"]}
    assert node_sources == {"src/foo.py"}, (
        f"cache nodes must store relative source_file; got {node_sources}"
    )
    assert edge_sources == {"src/foo.py"}


def test_load_cached_absolutizes_source_file(tmp_path):
    """``load_cached`` returns the same absolute-path shape that a fresh
    extraction produces, so consumers don't need to special-case cache
    hits vs. fresh extraction."""
    from graphify.cache import save_cached, load_cached

    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "foo.py"
    src.write_text("def x(): pass\n")
    abs_src = str(src.resolve())
    save_cached(src, {
        "nodes": [{"id": "n1", "source_file": abs_src}],
        "edges": [{"source": "n1", "target": "n1", "source_file": abs_src}],
    }, root=tmp_path, kind="ast")

    loaded = load_cached(src, root=tmp_path, kind="ast")
    assert loaded is not None
    assert loaded["nodes"][0]["source_file"] == abs_src
    assert loaded["edges"][0]["source_file"] == abs_src


def test_load_cached_passes_through_legacy_absolute_source_file(tmp_path):
    """Cache entries written by an older graphify (with absolute source_file
    inside) must still load correctly: the absolutize step is a no-op for
    already-absolute values."""
    import json
    from graphify.cache import load_cached, file_hash, cache_dir

    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "foo.py"
    src.write_text("pass\n")
    abs_src = str(src.resolve())

    # Hand-write a legacy-format cache entry (absolute source_file).
    h = file_hash(src, tmp_path)
    entry = cache_dir(tmp_path, "ast") / f"{h}.json"
    entry.write_text(json.dumps({
        "nodes": [{"id": "n1", "source_file": abs_src}],
        "edges": [],
    }))

    loaded = load_cached(src, root=tmp_path, kind="ast")
    assert loaded is not None
    assert loaded["nodes"][0]["source_file"] == abs_src


def test_cache_portable_across_roots(tmp_path):
    """End-to-end portability: a cache entry written at one root can be
    consumed at a different absolute root because the file is content-hashed
    AND its embedded source_file is stored relative."""
    import json
    import shutil
    from graphify.cache import save_cached, load_cached, file_hash, cache_dir

    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    (repo_a / "src").mkdir()
    src_a = repo_a / "src" / "foo.py"
    src_a.write_text("def x(): pass\n")
    save_cached(src_a, {
        "nodes": [{"id": "n1", "source_file": str(src_a.resolve())}],
        "edges": [],
    }, root=repo_a, kind="ast")

    # Copy corpus + cache to a second location with a different absolute prefix.
    repo_b = tmp_path / "repo_b"
    shutil.copytree(repo_a, repo_b)

    src_b = repo_b / "src" / "foo.py"
    loaded = load_cached(src_b, root=repo_b, kind="ast")
    assert loaded is not None, (
        "cache must port across absolute prefixes (content hash + relative source_file)"
    )
    # Source path re-anchored to the new root, not the old one.
    assert loaded["nodes"][0]["source_file"] == str(src_b.resolve())
    assert not str(repo_a) in loaded["nodes"][0]["source_file"]


def test_save_cached_in_root_symlink_keeps_symlink_name(tmp_path):
    """``source_file`` for an in-root symlink must be stored under the
    symlink's own name, not the resolved target. Lower-impact than the
    manifest case (cache lookup is content-hashed, not key-matched), but
    keeps the on-disk shape consistent with what callers passed in."""
    import json
    from graphify.cache import save_cached, file_hash, cache_dir

    (tmp_path / "sub").mkdir()
    target = tmp_path / "sub" / "target.py"
    target.write_text("pass\n")
    alias = tmp_path / "alias.py"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        import pytest
        pytest.skip("filesystem does not support symlinks")

    abs_alias = str(alias)  # caller's view — the symlink path, unresolved
    save_cached(alias, {
        "nodes": [{"id": "n1", "source_file": abs_alias}],
        "edges": [],
    }, root=tmp_path, kind="ast")

    h = file_hash(alias, tmp_path)
    entry = cache_dir(tmp_path, "ast") / f"{h}.json"
    on_disk = json.loads(entry.read_text(encoding="utf-8"))
    assert on_disk["nodes"][0]["source_file"] == "alias.py", (
        f"cache must store symlink name, not resolved target; got "
        f"{on_disk['nodes'][0]['source_file']!r}"
    )
