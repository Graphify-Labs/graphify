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


# --- #1259: frontmatter delimiters must be whole `---` lines -----------------

def test_body_content_hr_start_is_not_frontmatter():
    """A document opening with a ``----`` thematic break has no frontmatter;
    a later ``---`` hr must not be mistaken for a close delimiter."""
    content = b"----\nIntro paragraph that must be hashed.\n\n---\nbody"
    assert _body_content(content) == content


def test_body_content_dash_title_start_is_not_frontmatter():
    """``--- title`` on the first line is prose, not an open delimiter."""
    content = b"--- title\nIntro that must be hashed.\n\n---\nbody"
    assert _body_content(content) == content


def test_body_content_dash_text_line_is_not_close_delimiter():
    """``--- text`` and ``----`` lines inside opened frontmatter are not the
    close; without a proper close the content passes through unchanged."""
    content = b"---\ntitle: Test\nbody starts here\n--- not a delimiter\n----\nreal content"
    assert _body_content(content) == content


def test_body_content_later_proper_close_skips_dash_text_lines():
    """A ``--- text`` line is skipped; the next whole ``---`` line closes."""
    content = b"---\ntitle: Test\nnote: --- inline\n---\nreal body"
    assert _body_content(content) == b"\nreal body"


def test_body_content_well_formed_output_byte_identical():
    """For well-formed frontmatter the stripped body must stay byte-identical
    to the historical substring implementation, so existing semantic-cache
    hashes do not churn (re-extraction is billed LLM work)."""
    cases = [
        # (input, output of the historical text.find("\n---")+4 algorithm)
        (b"---\ntitle: Test\n---\n\nActual body.", b"\n\nActual body."),
        (b"---\nreviewed: 2026-01-01\n---\n\n# Title\n\nBody text.", b"\n\n# Title\n\nBody text."),
        # close delimiter with trailing whitespace keeps it in the body
        (b"---\ntitle: Test\n---  \nbody", b"  \nbody"),
        # CRLF line endings
        (b"---\r\ntitle: Test\r\n---\r\nbody", b"\r\nbody"),
        # empty frontmatter block
        (b"---\n---\nbody", b"\nbody"),
        # close as the very last line, no trailing newline
        (b"---\ntitle: Test\n---", b""),
    ]
    for content, expected in cases:
        assert _body_content(content) == expected, content


def test_md_edit_above_hr_changes_hash(tmp_path):
    """Editing content above a mid-document ``----`` break must change the
    hash -- previously that region was silently excluded from hashing."""
    f = tmp_path / "doc.md"
    f.write_text("----\nIntro paragraph.\n\n---\nbody")
    h1 = file_hash(f)
    f.write_text("----\nEdited intro paragraph.\n\n---\nbody")
    h2 = file_hash(f)
    assert h1 != h2


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


# --- AST cache versioning ----------------------------------------------------
# AST cache entries are the output of graphify's own extractor code, so they
# are only valid for the graphify version that wrote them. Keying purely on
# file content meant extractor fixes shipped in a new release kept serving
# stale pre-fix results. The AST cache is therefore namespaced by package
# version; the semantic cache is NOT (invalidating it would re-bill LLM
# extraction for unchanged files).

def test_ast_cache_invalidated_on_version_bump(tmp_path, monkeypatch):
    """An AST entry written by version X must not be served after upgrading
    to version Y — the file is unchanged but the extractor is not."""
    import graphify.cache as cache_mod

    f = tmp_path / "mod.py"
    f.write_text("def f(): pass\n")

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.0", raising=False)
    save_cached(f, {"nodes": [{"id": "n1"}], "edges": []}, root=tmp_path, kind="ast")
    assert load_cached(f, root=tmp_path, kind="ast") is not None

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.1", raising=False)
    assert load_cached(f, root=tmp_path, kind="ast") is None, (
        "AST cache entry from a previous graphify version must not be served"
    )


def test_ast_cache_version_bump_cleans_stale_entries(tmp_path, monkeypatch):
    """Upgrading removes AST entries left behind by previous versions so the
    cache directory does not grow one full copy per release."""
    import graphify.cache as cache_mod

    f = tmp_path / "mod.py"
    f.write_text("def f(): pass\n")

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.0", raising=False)
    save_cached(f, {"nodes": [{"id": "n1"}], "edges": []}, root=tmp_path, kind="ast")
    old_dir = cache_dir(tmp_path, "ast")
    assert any(old_dir.glob("*.json"))

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.1", raising=False)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set(), raising=False)
    cache_dir(tmp_path, "ast")
    assert not old_dir.exists(), (
        "stale AST version directory must be removed on upgrade"
    )


def test_legacy_unversioned_ast_entries_not_served(tmp_path):
    """Entries written by pre-versioning graphify (flat cache/ or unversioned
    cache/ast/) are by definition from an older extractor and must not be
    served — that staleness is exactly what version namespacing fixes."""
    import json
    from graphify.cache import file_hash, _GRAPHIFY_OUT

    f = tmp_path / "mod.py"
    f.write_text("def f(): pass\n")
    h = file_hash(f, tmp_path)
    payload = json.dumps({"nodes": [{"id": "stale"}], "edges": []})

    # Unversioned cache/ast/{hash}.json (pre-versioning layout)
    unversioned = tmp_path / _GRAPHIFY_OUT / "cache" / "ast"
    unversioned.mkdir(parents=True)
    (unversioned / f"{h}.json").write_text(payload)
    # Legacy flat cache/{hash}.json (pre-0.5.3 layout)
    (unversioned.parent / f"{h}.json").write_text(payload)

    assert load_cached(f, root=tmp_path, kind="ast") is None


def test_semantic_cache_survives_version_bump(tmp_path, monkeypatch):
    """The semantic cache is deliberately not versioned: entries are produced
    by the LLM from file contents, and re-extraction costs real money."""
    import graphify.cache as cache_mod

    f = tmp_path / "doc.md"
    f.write_text("# Title\n\nBody.\n")

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.0", raising=False)
    save_cached(f, {"nodes": [{"id": "n1"}], "edges": []}, root=tmp_path, kind="semantic")
    semantic_dir = cache_dir(tmp_path, "semantic")

    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "0.8.1", raising=False)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set(), raising=False)
    cache_dir(tmp_path, "ast")  # triggers stale-AST cleanup
    assert load_cached(f, root=tmp_path, kind="semantic") is not None
    assert any(semantic_dir.glob("*.json")), (
        "semantic entries must survive both the version bump and AST cleanup"
    )


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


def test_semantic_prune_removes_orphan_entries(tmp_path):
    """Changing a file's content leaves the old content-hash entry orphaned;
    pruning against the new live hash removes the stale entry and keeps the
    current one."""
    from graphify.cache import prune_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# A\n\nContent A.\n")
    h_a = file_hash(f, tmp_path)
    save_cached(f, {"nodes": [{"id": "a"}], "edges": []}, root=tmp_path, kind="semantic")

    f.write_text("# B\n\nContent B.\n")
    h_b = file_hash(f, tmp_path)
    save_cached(f, {"nodes": [{"id": "b"}], "edges": []}, root=tmp_path, kind="semantic")

    semantic_dir = cache_dir(tmp_path, "semantic")
    assert (semantic_dir / f"{h_a}.json").exists()
    assert (semantic_dir / f"{h_b}.json").exists()

    pruned = prune_semantic_cache(tmp_path, {h_b})
    assert pruned == 1
    assert not (semantic_dir / f"{h_a}.json").exists()
    assert (semantic_dir / f"{h_b}.json").exists()


def test_semantic_prune_keeps_live_unchanged_entries(tmp_path):
    """Pruning against the FULL live set must keep every live entry — guards
    the trap of pruning against an incremental changed-subset, which would
    delete all unchanged docs' valid entries."""
    from graphify.cache import prune_semantic_cache

    live_hashes = set()
    for i in range(5):
        f = tmp_path / f"doc{i}.md"
        f.write_text(f"# Doc {i}\n\nBody {i}.\n")
        save_cached(f, {"nodes": [{"id": str(i)}], "edges": []}, root=tmp_path, kind="semantic")
        live_hashes.add(file_hash(f, tmp_path))

    semantic_dir = cache_dir(tmp_path, "semantic")
    assert len(list(semantic_dir.glob("*.json"))) == 5

    pruned = prune_semantic_cache(tmp_path, live_hashes)
    assert pruned == 0
    assert len(list(semantic_dir.glob("*.json"))) == 5


def test_semantic_prune_handles_deleted_file(tmp_path):
    """An entry for a file that no longer exists (dropped from the live set) is
    pruned."""
    from graphify.cache import prune_semantic_cache

    f = tmp_path / "gone.md"
    f.write_text("# Gone\n\nWill be deleted.\n")
    h = file_hash(f, tmp_path)
    save_cached(f, {"nodes": [{"id": "g"}], "edges": []}, root=tmp_path, kind="semantic")
    semantic_dir = cache_dir(tmp_path, "semantic")
    assert (semantic_dir / f"{h}.json").exists()

    f.unlink()
    # Live set is empty: the file is gone, so its entry must be pruned.
    pruned = prune_semantic_cache(tmp_path, set())
    assert pruned == 1
    assert not (semantic_dir / f"{h}.json").exists()


def test_semantic_prune_ignores_ast_and_tmp(tmp_path):
    """Prune touches only cache/semantic/*.json: AST entries and atomic-write
    *.tmp temporaries are left untouched."""
    from graphify.cache import prune_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\nBody.\n")
    # AST entry (different subtree) must survive.
    save_cached(f, {"nodes": [{"id": "ast"}], "edges": []}, root=tmp_path, kind="ast")
    ast_dir = cache_dir(tmp_path, "ast")
    assert len(list(ast_dir.glob("*.json"))) == 1

    # A semantic orphan .json (to be pruned) plus a .tmp temporary (to survive).
    semantic_dir = cache_dir(tmp_path, "semantic")
    (semantic_dir / "deadbeef.json").write_text('{"nodes": [], "edges": []}')
    tmp_entry = semantic_dir / "deadbeef.tmp"
    tmp_entry.write_text("partial")

    pruned = prune_semantic_cache(tmp_path, set())
    assert pruned == 1
    assert not (semantic_dir / "deadbeef.json").exists()
    assert tmp_entry.exists(), "*.tmp temporaries must not be swept"
    assert len(list(ast_dir.glob("*.json"))) == 1, "AST entries must not be touched"


def test_save_semantic_cache_overwrites_by_default(tmp_path):
    """Default save_semantic_cache replaces a file's cached entry (the final,
    authoritative write in the extract pipeline)."""
    from graphify.cache import save_semantic_cache
    f = tmp_path / "doc.md"; f.write_text("# Doc\n")
    save_semantic_cache([{"id": "a", "source_file": "doc.md"}], [], root=tmp_path)
    save_semantic_cache([{"id": "b", "source_file": "doc.md"}], [], root=tmp_path)
    cached = load_cached(f, root=tmp_path, kind="semantic")
    ids = {n["id"] for n in cached["nodes"]}
    assert ids == {"b"}, "default must overwrite, not accumulate"


def test_save_semantic_cache_rejects_out_of_scope_source_file(tmp_path):
    """#1757: an undispatched file must keep its complete cache entry when a
    semantic result misattributes a node to it."""
    from graphify.cache import save_semantic_cache

    intended = tmp_path / "intended.md"
    intended.write_text("# Intended\n")
    protected = tmp_path / "protected.md"
    protected.write_text("# Protected\n")

    save_semantic_cache(
        [{"id": "original", "source_file": "protected.md"}],
        [],
        root=tmp_path,
    )

    nodes = [
        {"id": "expected", "source_file": str(intended.resolve())},
        {"id": "stray", "source_file": "protected.md"},
    ]
    edges = [
        {"source": "stray", "target": "expected", "source_file": "protected.md"},
    ]
    hyperedges = [
        {"id": "stray_hyperedge", "nodes": ["stray"], "source_file": "protected.md"},
    ]

    with pytest.warns(RuntimeWarning, match="out-of-scope source_file 'protected.md'"):
        saved = save_semantic_cache(
            nodes,
            edges,
            hyperedges,
            root=tmp_path,
            allowed_source_files=["intended.md"],
        )

    assert saved == 1
    intended_cache = load_cached(intended, root=tmp_path, kind="semantic")
    assert {node["id"] for node in intended_cache["nodes"]} == {"expected"}

    protected_cache = load_cached(protected, root=tmp_path, kind="semantic")
    assert {node["id"] for node in protected_cache["nodes"]} == {"original"}
    assert protected_cache["edges"] == []
    assert protected_cache["hyperedges"] == []


# --- #1894: mode-namespaced semantic cache -----------------------------------
# `extract --mode deep` produces richer results than standard extraction, so
# deep entries live in their own namespace (cache/semantic-deep/). mode=None
# must stay byte-identical to the historical behavior: older installed skill
# flows call check/save without the parameter and must be unaffected.

def test_semantic_cache_deep_mode_roundtrip_under_deep_namespace(tmp_path):
    """mode='deep' saves under cache/semantic-deep/ and reads back from it."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\nBody.\n")
    saved = save_semantic_cache(
        [{"id": "deep_n", "source_file": "doc.md"}], [], root=tmp_path, mode="deep"
    )
    assert saved == 1

    deep_dir = tmp_path / "graphify-out" / "cache" / "semantic-deep"
    h = file_hash(f, tmp_path)
    assert (deep_dir / f"{h}.json").exists(), (
        "deep entry must land under cache/semantic-deep/"
    )
    # And NOT in the plain namespace.
    plain_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    assert not (plain_dir / f"{h}.json").exists()

    nodes, edges, hyper, uncached = check_semantic_cache(
        [str(f)], root=tmp_path, mode="deep"
    )
    assert [n["id"] for n in nodes] == ["deep_n"]
    assert uncached == []


def test_semantic_cache_deep_invisible_to_plain_reads_and_vice_versa(tmp_path):
    """Deep entries must not satisfy mode=None reads (and plain entries must
    not satisfy deep reads) — the namespaces are fully isolated."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    deep_doc = tmp_path / "deep.md"
    deep_doc.write_text("# Deep\n")
    plain_doc = tmp_path / "plain.md"
    plain_doc.write_text("# Plain\n")

    save_semantic_cache([{"id": "d", "source_file": "deep.md"}], [],
                        root=tmp_path, mode="deep")
    save_semantic_cache([{"id": "p", "source_file": "plain.md"}], [],
                        root=tmp_path)  # mode omitted: historical call shape

    # Plain read: deep entry is a miss, plain entry is a hit.
    nodes, _, _, uncached = check_semantic_cache(
        [str(deep_doc), str(plain_doc)], root=tmp_path
    )
    assert [n["id"] for n in nodes] == ["p"]
    assert uncached == [str(deep_doc)]

    # Deep read: mirror image.
    nodes, _, _, uncached = check_semantic_cache(
        [str(deep_doc), str(plain_doc)], root=tmp_path, mode="deep"
    )
    assert [n["id"] for n in nodes] == ["d"]
    assert uncached == [str(plain_doc)]


def test_semantic_cache_mode_none_layout_unchanged(tmp_path):
    """Omitting mode writes exactly the historical cache/semantic/ layout —
    forward-compat for older installed callers that never pass mode."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "n", "source_file": "doc.md"}], [], root=tmp_path)
    h = file_hash(f, tmp_path)
    assert (tmp_path / "graphify-out" / "cache" / "semantic" / f"{h}.json").exists()
    assert not (tmp_path / "graphify-out" / "cache" / "semantic-deep").exists(), (
        "mode=None must never create the deep namespace"
    )
    nodes, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path)
    assert [n["id"] for n in nodes] == ["n"] and uncached == []


def test_clear_cache_removes_deep_namespace(tmp_path):
    """clear_cache sweeps cache/semantic-deep/ alongside semantic/ and ast/."""
    from graphify.cache import save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "p", "source_file": "doc.md"}], [], root=tmp_path)
    save_semantic_cache([{"id": "d", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep")
    base = tmp_path / "graphify-out" / "cache"
    assert list((base / "semantic").glob("*.json"))
    assert list((base / "semantic-deep").glob("*.json"))

    clear_cache(tmp_path)
    assert not list(base.rglob("*.json")), (
        "clear_cache must remove entries in BOTH semantic namespaces"
    )


def test_cached_files_includes_deep_namespace(tmp_path):
    """cached_files reports deep-namespace entries too."""
    from graphify.cache import save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "d", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep")
    assert file_hash(f, tmp_path) in cached_files(tmp_path)


def test_semantic_prune_sweeps_both_namespaces_against_same_live_set(tmp_path):
    """#1894 follow-up to #1527: prune must sweep cache/semantic/ AND
    cache/semantic-deep/ against the SAME live-hash set (liveness is
    content-based, mode-independent). Orphans go in both namespaces; live
    entries survive in both."""
    from graphify.cache import prune_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# A\n\nContent A.\n")
    h_old = file_hash(f, tmp_path)
    save_semantic_cache([{"id": "pa", "source_file": "doc.md"}], [], root=tmp_path)
    save_semantic_cache([{"id": "da", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep")

    f.write_text("# B\n\nContent B.\n")
    h_live = file_hash(f, tmp_path)
    save_semantic_cache([{"id": "pb", "source_file": "doc.md"}], [], root=tmp_path)
    save_semantic_cache([{"id": "db", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep")

    plain_dir = tmp_path / "graphify-out" / "cache" / "semantic"
    deep_dir = tmp_path / "graphify-out" / "cache" / "semantic-deep"
    for d in (plain_dir, deep_dir):
        assert (d / f"{h_old}.json").exists()
        assert (d / f"{h_live}.json").exists()

    pruned = prune_semantic_cache(tmp_path, {h_live})
    assert pruned == 2, "one orphan in EACH namespace must be pruned"
    for d in (plain_dir, deep_dir):
        assert not (d / f"{h_old}.json").exists(), f"orphan survived in {d.name}"
        assert (d / f"{h_live}.json").exists(), f"live entry pruned from {d.name}"


def test_save_semantic_cache_merge_existing_unions(tmp_path):
    """#1715: merge_existing=True unions with the prior entry so a file split
    across chunks (checkpointed per chunk) keeps every slice."""
    from graphify.cache import save_semantic_cache
    f = tmp_path / "big.md"; f.write_text("# Big\n")
    # chunk 1 slice
    save_semantic_cache([{"id": "a", "source_file": "big.md"}],
                        [{"source": "a", "target": "x", "source_file": "big.md"}],
                        root=tmp_path, merge_existing=True)
    # chunk 2 slice for the same file
    save_semantic_cache([{"id": "b", "source_file": "big.md"}], [],
                        root=tmp_path, merge_existing=True)
    cached = load_cached(f, root=tmp_path, kind="semantic")
    ids = {n["id"] for n in cached["nodes"]}
    assert ids == {"a", "b"}, "merge_existing must union both chunk slices"
    assert len(cached["edges"]) == 1


def test_save_semantic_cache_drops_edges_to_out_of_scope_nodes(tmp_path):
    """#1916: an edge in an ALLOWED file's group referencing a node grouped
    under an out-of-scope REAL file used to be written verbatim, so on replay
    (check_semantic_cache) it dangled forever — the #1895 merged-result filter
    runs after this checkpoint write and is bypassed entirely on replay. The
    written entry must carry no reference to the skipped id, while a
    duplicate-attribution node (also defined in a written group) must not be
    over-pruned."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    allowed = tmp_path / "allowed.md"
    allowed.write_text("# Allowed\n")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")

    nodes = [
        {"id": "kept", "source_file": "allowed.md"},
        {"id": "stray", "source_file": "outside.md"},
        # duplicate attribution: same id defined in a written AND a skipped group
        {"id": "dup", "source_file": "allowed.md"},
        {"id": "dup", "source_file": "outside.md"},
    ]
    edges = [
        {"source": "kept", "target": "stray", "source_file": "allowed.md"},
        {"source": "stray", "target": "kept", "source_file": "allowed.md"},
        {"source": "kept", "target": "dup", "source_file": "allowed.md"},
    ]
    with pytest.warns(RuntimeWarning, match="out-of-scope source_file"):
        saved = save_semantic_cache(
            nodes, edges, root=tmp_path, allowed_source_files=["allowed.md"]
        )
    assert saved == 1

    cached_nodes, cached_edges, _, uncached = check_semantic_cache(
        [str(allowed)], root=tmp_path
    )
    assert uncached == []
    assert {n["id"] for n in cached_nodes} == {"kept", "dup"}
    pairs = [(e["source"], e["target"]) for e in cached_edges]
    assert pairs == [("kept", "dup")], "edges touching the skipped id must be dropped"


def test_save_semantic_cache_drops_edges_to_ghost_file_nodes(tmp_path):
    """#1916 (ghost variant): a node group whose source_file does not exist is
    silently skipped by the write loop; edges in a written group referencing
    its node ids must not survive into the cache."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    real = tmp_path / "real.md"
    real.write_text("# Real\n")

    nodes = [
        {"id": "kept", "source_file": "real.md"},
        {"id": "phantom", "source_file": "ghost.md"},  # no such file on disk
    ]
    edges = [
        {"source": "kept", "target": "phantom", "source_file": "real.md"},
        {"source": "kept", "target": "kept", "relation": "self", "source_file": "real.md"},
    ]
    saved = save_semantic_cache(
        nodes, edges, root=tmp_path, allowed_source_files=["real.md"]
    )
    assert saved == 1

    cached_nodes, cached_edges, _, uncached = check_semantic_cache(
        [str(real)], root=tmp_path
    )
    assert uncached == []
    assert {n["id"] for n in cached_nodes} == {"kept"}
    pairs = [(e["source"], e["target"]) for e in cached_edges]
    assert pairs == [("kept", "kept")]


def test_save_semantic_cache_drops_hyperedges_touching_skipped_nodes(tmp_path):
    """#1916: a hyperedge whose member list intersects the skipped ids is
    dropped whole (mirroring the #1895 semantics), while hyperedges over
    surviving nodes are kept."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    allowed = tmp_path / "allowed.md"
    allowed.write_text("# Allowed\n")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")

    nodes = [
        {"id": "kept", "source_file": "allowed.md"},
        {"id": "kept2", "source_file": "allowed.md"},
        {"id": "stray", "source_file": "outside.md"},
    ]
    hyperedges = [
        {"id": "he_bad", "nodes": ["kept", "stray"], "source_file": "allowed.md"},
        {"id": "he_ok", "nodes": ["kept", "kept2"], "source_file": "allowed.md"},
    ]
    with pytest.warns(RuntimeWarning, match="out-of-scope source_file"):
        save_semantic_cache(
            nodes, [], hyperedges, root=tmp_path, allowed_source_files=["allowed.md"]
        )

    _, _, cached_hyperedges, uncached = check_semantic_cache(
        [str(allowed)], root=tmp_path
    )
    assert uncached == []
    assert {h["id"] for h in cached_hyperedges} == {"he_ok"}


def test_save_semantic_cache_unscoped_preserves_dangling_refs_verbatim(tmp_path):
    """#1916 guard-rail: unscoped callers (allowed_source_files=None) must stay
    byte-identical — no pruning happens even when an edge or hyperedge
    references a node grouped under a ghost file."""
    from graphify.cache import save_semantic_cache

    doc = tmp_path / "doc.md"
    doc.write_text("# Doc\n")

    nodes = [
        {"id": "a", "source_file": "doc.md"},
        {"id": "ghost_n", "source_file": "ghost.md"},  # skipped group (no file)
    ]
    edges = [{"source": "a", "target": "ghost_n", "source_file": "doc.md"}]
    hyperedges = [{"id": "he", "nodes": ["a", "ghost_n"], "source_file": "doc.md"}]

    saved = save_semantic_cache(nodes, edges, hyperedges, root=tmp_path)
    assert saved == 1

    import json
    raw = json.loads(
        (cache_dir(tmp_path, "semantic") / f"{file_hash(doc, tmp_path)}.json").read_text()
    )
    assert raw["edges"] == edges
    assert raw["hyperedges"] == hyperedges


def test_save_semantic_cache_merge_existing_prunes_only_incoming(tmp_path):
    """#1916 + #1715: with merge_existing=True (the llm.py checkpoint path),
    only the INCOMING slice is pruned before the union — the prior cached
    entry's valid edges must survive untouched."""
    from graphify.cache import save_semantic_cache

    big = tmp_path / "big.md"
    big.write_text("# Big\n")
    other = tmp_path / "other.md"
    other.write_text("# Other\n")

    # checkpoint 1: a clean slice
    save_semantic_cache(
        [{"id": "a", "source_file": "big.md"}],
        [{"source": "a", "target": "a", "relation": "self", "source_file": "big.md"}],
        root=tmp_path,
        merge_existing=True,
        allowed_source_files=["big.md"],
    )
    # checkpoint 2: incoming slice with a dangling edge to an out-of-scope node
    nodes2 = [
        {"id": "b", "source_file": "big.md"},
        {"id": "stray", "source_file": "other.md"},
    ]
    edges2 = [
        {"source": "b", "target": "stray", "source_file": "big.md"},
        {"source": "a", "target": "b", "source_file": "big.md"},
    ]
    with pytest.warns(RuntimeWarning, match="out-of-scope source_file"):
        save_semantic_cache(
            nodes2, edges2, root=tmp_path, merge_existing=True,
            allowed_source_files=["big.md"],
        )

    cached = load_cached(big, root=tmp_path, kind="semantic")
    assert {n["id"] for n in cached["nodes"]} == {"a", "b"}
    pairs = [(e["source"], e["target"]) for e in cached["edges"]]
    assert ("a", "a") in pairs, "prior entry's valid edge must survive the union"
    assert ("a", "b") in pairs, "incoming valid edge must be kept"
    assert not any("stray" in p for p in pairs)


# --- extraction-prompt fingerprinting (#1939) -------------------------------


def test_prompt_fingerprint_stable_and_prompt_sensitive(tmp_path):
    """The fingerprint is stable for identical prompts and differs when the
    prompt text changes — the whole invalidation signal rests on this."""
    from graphify.cache import prompt_fingerprint

    assert prompt_fingerprint("extract a graph") == prompt_fingerprint("extract a graph")
    assert prompt_fingerprint("extract a graph") != prompt_fingerprint("extract a graph v2")

    # A Path is read and hashed as its contents, so the skill path (which loads
    # references/extraction-spec.md) and the Python path agree on the same text.
    spec = tmp_path / "extraction-spec.md"
    spec.write_text("extract a graph", encoding="utf-8")
    assert prompt_fingerprint(spec) == prompt_fingerprint("extract a graph")


def test_prompt_fingerprint_ignores_line_endings(tmp_path):
    """A CRLF checkout of the same spec must not look like a prompt change —
    otherwise every Windows run re-bills the whole corpus."""
    from graphify.cache import prompt_fingerprint

    assert prompt_fingerprint("a\r\nb\r\n") == prompt_fingerprint("a\nb\n")
    assert prompt_fingerprint("a  \nb\n") == prompt_fingerprint("a\nb\n")


def test_semantic_cache_prompt_change_invalidates(tmp_path):
    """The reported bug (#1939): after the extraction prompt changes, an
    unchanged file must MISS instead of replaying the older vintage."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\nBody.\n")
    save_semantic_cache([{"id": "old_vintage", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V1")

    # Same prompt: hit.
    nodes, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, prompt="PROMPT V1")
    assert [n["id"] for n in nodes] == ["old_vintage"]
    assert uncached == []

    # Prompt changed (an upgrade shipped a new extraction-spec): must re-extract.
    nodes, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, prompt="PROMPT V2")
    assert nodes == []
    assert uncached == [str(f)], "a new prompt must not replay the old prompt's entry"

    # V2's results land in their own namespace and do not clobber V1's, so
    # rolling back to V1 still hits rather than re-billing.
    save_semantic_cache([{"id": "new_vintage", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V2")
    nodes, _, _, _ = check_semantic_cache([str(f)], root=tmp_path, prompt="PROMPT V2")
    assert [n["id"] for n in nodes] == ["new_vintage"]
    nodes, _, _, _ = check_semantic_cache([str(f)], root=tmp_path, prompt="PROMPT V1")
    assert [n["id"] for n in nodes] == ["old_vintage"]


def test_semantic_cache_prompt_namespaced_layout(tmp_path):
    """Fingerprinted entries live under cache/semantic/p{fp}/, never flat."""
    from graphify.cache import prompt_fingerprint, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "n", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V1")

    sem = tmp_path / "graphify-out" / "cache" / "semantic"
    h = file_hash(f, tmp_path)
    assert (sem / f"p{prompt_fingerprint('PROMPT V1')}" / f"{h}.json").exists()
    assert not (sem / f"{h}.json").exists(), (
        "a known-vintage entry must never be written into the flat unknown-vintage layout"
    )


def test_semantic_cache_prompt_and_mode_compose(tmp_path):
    """The prompt fingerprint nests inside the deep namespace (#1894), so the
    two dimensions are independent."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "d", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep", prompt="PROMPT V1")

    deep = tmp_path / "graphify-out" / "cache" / "semantic-deep"
    assert list(deep.glob("p*/*.json")), "deep + prompt must nest under semantic-deep/p{fp}/"

    # Right mode, wrong prompt -> miss. Right prompt, wrong mode -> miss.
    _, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, mode="deep",
                                             prompt="PROMPT V2")
    assert uncached == [str(f)]
    _, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, prompt="PROMPT V1")
    assert uncached == [str(f)]
    # Both right -> hit.
    nodes, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, mode="deep",
                                                 prompt="PROMPT V1")
    assert [n["id"] for n in nodes] == ["d"] and uncached == []


def test_semantic_cache_legacy_entries_served_with_warning(tmp_path):
    """Entries written before fingerprinting have unknowable vintage. They are
    still served — dropping them would re-bill a whole corpus on upgrade — but
    the user is told how many, which is the signal #1939 says is missing today."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    a = tmp_path / "a.md"
    a.write_text("# A\n")
    b = tmp_path / "b.md"
    b.write_text("# B\n")
    # Pre-fingerprint writes: the historical flat layout.
    save_semantic_cache([{"id": "a_old", "source_file": "a.md"},
                         {"id": "b_old", "source_file": "b.md"}], [], root=tmp_path)

    with pytest.warns(RuntimeWarning, match="2 semantic cache entries predate"):
        nodes, _, _, uncached = check_semantic_cache(
            [str(a), str(b)], root=tmp_path, prompt="PROMPT V1"
        )
    assert {n["id"] for n in nodes} == {"a_old", "b_old"}
    assert uncached == []


def test_semantic_cache_fingerprinted_entry_beats_legacy(tmp_path):
    """Once a file is re-extracted under the current prompt, its fingerprinted
    entry wins and the stale flat one is no longer consulted (no warning)."""
    import warnings as _warnings
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "unknown_vintage", "source_file": "doc.md"}], [],
                        root=tmp_path)  # legacy flat
    save_semantic_cache([{"id": "current", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V1")

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")  # any legacy warning would raise here
        nodes, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path,
                                                     prompt="PROMPT V1")
    assert [n["id"] for n in nodes] == ["current"]
    assert uncached == []


def test_semantic_cache_merge_existing_never_fuses_legacy_vintage(tmp_path):
    """merge_existing must not union a pre-fingerprint entry into a write it is
    about to stamp as current-vintage — that would mix two prompts inside one
    entry and then attest the result to a prompt that produced half of it."""
    from graphify.cache import load_cached, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "unknown_vintage", "source_file": "doc.md"}], [],
                        root=tmp_path)  # legacy flat
    save_semantic_cache([{"id": "current", "source_file": "doc.md"}], [],
                        root=tmp_path, merge_existing=True, prompt="PROMPT V1")

    entry = load_cached(f, root=tmp_path, kind="semantic", prompt="PROMPT V1")
    assert [n["id"] for n in entry["nodes"]] == ["current"]

    # Within one prompt, merge_existing still unions across checkpoints.
    save_semantic_cache([{"id": "second_chunk", "source_file": "doc.md"}], [],
                        root=tmp_path, merge_existing=True, prompt="PROMPT V1")
    entry = load_cached(f, root=tmp_path, kind="semantic", prompt="PROMPT V1")
    assert {n["id"] for n in entry["nodes"]} == {"current", "second_chunk"}


def test_semantic_prune_and_clear_reach_fingerprint_subdirs(tmp_path):
    """A glob that stopped at the top level would leave every fingerprinted
    entry unprunable, re-growing the unbounded-orphan problem of #1527."""
    from graphify.cache import (
        cached_files, clear_cache, prune_semantic_cache, save_semantic_cache,
    )

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "n", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V1")
    h = file_hash(f, tmp_path)
    assert h in cached_files(tmp_path), "cached_files must see fingerprinted entries"

    # Live: kept.
    assert prune_semantic_cache(tmp_path, {h}) == 0
    # Orphaned (content changed / file deleted): pruned.
    assert prune_semantic_cache(tmp_path, set()) == 1

    save_semantic_cache([{"id": "n", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt="PROMPT V1")
    clear_cache(tmp_path)
    assert not list((tmp_path / "graphify-out" / "cache" / "semantic").glob("**/*.json"))


def test_semantic_cache_unreadable_prompt_file_warns_and_falls_back(tmp_path):
    """A skill snippet substitutes SPEC_PATH by hand. If it lands on a path that
    isn't there, the fallback to the unattributed layout must be loud: silently
    reverting to unversioned keying is exactly the #1939 behavior being fixed."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")
    save_semantic_cache([{"id": "n", "source_file": "doc.md"}], [], root=tmp_path)

    with pytest.warns(RuntimeWarning, match="could not read extraction prompt"):
        nodes, _, _, uncached = check_semantic_cache(
            [str(f)], root=tmp_path, prompt_file=str(tmp_path / "nope.md")
        )
    # Fell back rather than aborting the run.
    assert [n["id"] for n in nodes] == ["n"] and uncached == []


def test_prompt_file_reflects_edited_spec(tmp_path):
    """The prompt-file fingerprint is memoized per (path, size, mtime); an edited
    spec must still register as a new prompt rather than reusing a stale memo."""
    from graphify.cache import check_semantic_cache, save_semantic_cache

    spec = tmp_path / "extraction-spec.md"
    spec.write_text("prompt one", encoding="utf-8")
    f = tmp_path / "doc.md"
    f.write_text("# Doc\n")

    save_semantic_cache([{"id": "v1", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt_file=str(spec))
    nodes, _, _, _ = check_semantic_cache([str(f)], root=tmp_path, prompt_file=str(spec))
    assert [n["id"] for n in nodes] == ["v1"]

    # An upgrade rewrites the spec: the same file path is now a different prompt.
    import os as _os
    spec.write_text("prompt two — rewritten by an upgrade", encoding="utf-8")
    _os.utime(spec, ns=(0, 0))  # force a distinct stat signature
    _, _, _, uncached = check_semantic_cache([str(f)], root=tmp_path, prompt_file=str(spec))
    assert uncached == [str(f)], "an edited spec must invalidate, not reuse the memo"
