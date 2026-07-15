"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS, _rebuild_lock, _check_shrink


# --- _notify_only ---

def test_notify_only_creates_flag(tmp_path):
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.exists()
    assert flag.read_text() == "1"

def test_notify_only_creates_flag_dir(tmp_path):
    # graphify-out dir does not exist yet
    assert not (tmp_path / "graphify-out").exists()
    _notify_only(tmp_path)
    assert (tmp_path / "graphify-out").is_dir()

def test_notify_only_idempotent(tmp_path):
    _notify_only(tmp_path)
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.read_text() == "1"


# --- _WATCHED_EXTENSIONS ---

def test_watched_extensions_includes_code():
    assert ".py" in _WATCHED_EXTENSIONS
    assert ".ts" in _WATCHED_EXTENSIONS
    assert ".go" in _WATCHED_EXTENSIONS
    assert ".rs" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_docs():
    assert ".md" in _WATCHED_EXTENSIONS
    assert ".txt" in _WATCHED_EXTENSIONS
    assert ".pdf" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_images():
    assert ".png" in _WATCHED_EXTENSIONS
    assert ".jpg" in _WATCHED_EXTENSIONS

def test_watched_extensions_excludes_noise():
    # .json is now indexed (bash/JSON extractors added in #866)
    assert ".json" in _WATCHED_EXTENSIONS
    assert ".sh" in _WATCHED_EXTENSIONS
    assert ".pyc" not in _WATCHED_EXTENSIONS
    assert ".log" not in _WATCHED_EXTENSIONS


# --- watch() import error without watchdog ---

def test_check_update_no_flag_returns_true(tmp_path):
    """check_update returns True and is silent when needs_update flag is absent."""
    from graphify.watch import check_update
    assert check_update(tmp_path) is True


def test_check_update_with_flag_returns_true_and_prints(tmp_path, capsys):
    """check_update returns True and prints notification when flag exists."""
    from graphify.watch import check_update
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    result = check_update(tmp_path)
    assert result is True
    out = capsys.readouterr().out
    assert "graphify --update" in out


def test_check_update_does_not_clear_flag(tmp_path):
    """check_update never removes the needs_update flag (clearing is LLM's job)."""
    from graphify.watch import check_update
    flag = tmp_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    check_update(tmp_path)
    assert flag.exists()


def test_watch_raises_without_watchdog(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "watchdog.observers" or name == "watchdog.events":
            raise ImportError("mocked missing watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from graphify.watch import watch
    with pytest.raises(ImportError, match="watchdog not installed"):
        watch(tmp_path)


# --- _rebuild_lock (GH-858) ---


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_writes_pid_with_newline(tmp_path):
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as got:
        assert got is True
        assert lock_path.exists()
        contents = lock_path.read_text(encoding="utf-8")
        assert contents == f"{os.getpid()}\n", contents


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_removed_after_release(tmp_path):
    """GH-858: lock file must be unlinked once the rebuild completes so
    downstream waiters that poll for its absence unblock promptly."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as got:
        assert got is True
    assert not lock_path.exists(), "lock file should be unlinked after release"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_does_not_accumulate_pids_across_runs(tmp_path):
    """GH-858: each acquisition truncates and rewrites the PID line rather
    than appending, so the file never grows into a digit-concatenation."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    expected = f"{os.getpid()}\n"
    for _ in range(5):
        with _rebuild_lock(out) as got:
            assert got is True
            assert lock_path.read_text(encoding="utf-8") == expected
        assert not lock_path.exists()


def test_graphify_root_preserves_relative_when_invoked_with_relative_path(tmp_path, monkeypatch):
    """#777: ``.graphify_root`` stores the user-supplied path (``.``), not the
    resolved absolute, so a committed ``graphify-out/.graphify_root`` is
    portable across clones and CI runners."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "lib.py").write_text("def f(): pass\n", encoding="utf-8")

    monkeypatch.chdir(corpus)
    assert _rebuild_code(Path("."), acquire_lock=False) is True

    saved = (corpus / "graphify-out" / ".graphify_root").read_text(encoding="utf-8")
    assert saved == ".", (
        f".graphify_root must preserve the user-supplied path; got {saved!r}"
    )


def test_rebuild_code_writes_community_name(tmp_path):
    """#1808: `graphify update` / _rebuild_code must forward community_labels to
    to_json, so graph.json nodes carry a human-readable community_name (hub-derived
    for a code-only rebuild) — not just a numeric community id. Before the fix,
    _rebuild_code called to_json without community_labels, so the labels a
    cluster-only pass writes were stripped again on every incremental rebuild."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text(
        "def alpha():\n    return beta()\n\ndef beta():\n    return 1\n", encoding="utf-8"
    )
    (corpus / "b.py").write_text(
        "import a\n\ndef gamma():\n    return a.alpha()\n", encoding="utf-8"
    )
    assert _rebuild_code(corpus, acquire_lock=False) is True

    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    clustered = [n for n in graph["nodes"] if n.get("community") is not None]
    assert clustered, "expected clustered nodes in the rebuilt graph"
    assert all(n.get("community_name") for n in clustered), (
        "clustered nodes missing community_name — the update rebuild stripped the "
        "labels that cluster-only writes (#1808)"
    )


def test_update_rebuilds_with_nested_star_gitignore(tmp_path):
    """#1880: `graphify update` must not emit 0 nodes (and then refuse to
    overwrite) just because the source tree has a nested `.gitignore` with a
    broad pattern. This was the 0.9.15 symptom of the #1847/#1873 subtree-scoping
    bug: a nested bare `*` zeroed the re-scan, update built 0 nodes, and the
    shrink-guard refused. With scoping fixed the rebuild sees the real files."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    (corpus / "src").mkdir(parents=True)
    (corpus / "src" / "a.py").write_text(
        "from src.b import Base\nclass App(Base):\n    def run(self): return 1\n", encoding="utf-8"
    )
    (corpus / "src" / "b.py").write_text("class Base: pass\n", encoding="utf-8")
    (corpus / "main.py").write_text("def top(): return 2\n", encoding="utf-8")
    # a common scratch-dir idiom deeper in the tree: ignore everything HERE only
    (corpus / "scratch").mkdir()
    (corpus / "scratch" / ".gitignore").write_text("*\n", encoding="utf-8")
    (corpus / "scratch" / "junk.py").write_text("x = 1\n", encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False) is True

    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    sources = {n.get("source_file", "") for n in graph["nodes"]}
    assert graph["nodes"], "update produced 0 nodes on a tree with a nested '*' gitignore (#1880)"
    assert any("src/a.py" in s for s in sources) and any("main.py" in s for s in sources)
    # the nested-ignored scratch file stays out (scoped correctly, not tree-wide)
    assert not any("scratch/junk.py" in s for s in sources)


def test_update_discovers_newly_added_files_and_dirs(tmp_path):
    """#1837: after an initial build, a plain `graphify update` (full re-scan, no
    change-list) must discover brand-new files AND new directories. The reported
    silent no-op was the #1873 nested-gitignore scoping bug zeroing the re-scan;
    this pins the build -> add -> update -> discovered sequence the earlier test
    (single build) did not cover, with a nested `*` scratch dir as a guard."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    (corpus / "src").mkdir(parents=True)
    (corpus / "src" / "a.py").write_text("def alpha(): return 1\n", encoding="utf-8")
    assert _rebuild_code(corpus, acquire_lock=False) is True

    # Add a brand-new file and a brand-new nested directory after the first build,
    # plus a scratch dir that ignores only itself.
    (corpus / "src" / "new.py").write_text("def added(): return 2\n", encoding="utf-8")
    (corpus / "monitor").mkdir()
    (corpus / "monitor" / "dash.py").write_text("def board(): return 3\n", encoding="utf-8")
    (corpus / "scratch").mkdir()
    (corpus / "scratch" / ".gitignore").write_text("*\n", encoding="utf-8")
    (corpus / "scratch" / "junk.py").write_text("x = 1\n", encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False) is True

    sources = {n.get("source_file", "") for n in
               json.loads((corpus / "graphify-out" / "graph.json").read_text())["nodes"]}
    assert any("src/new.py" in s for s in sources), "new file not discovered by update (#1837)"
    assert any("monitor/dash.py" in s for s in sources), "new directory not discovered (#1837)"
    assert not any("scratch/junk.py" in s for s in sources)


def test_rebuild_honors_persisted_excludes(tmp_path):
    """#1886: `--exclude` recorded at extract time must survive into update/watch/
    hook rebuilds. Before the fix only the initial scan applied the excludes, so
    the first rebuild silently re-indexed the excluded paths. _rebuild_code now
    reads the persisted build config and re-applies them."""
    import json
    from graphify.watch import _rebuild_code, _write_build_config

    corpus = tmp_path / "corpus"
    (corpus / "src").mkdir(parents=True)
    (corpus / "vendor").mkdir()
    (corpus / "src" / "app.py").write_text("def keep(): return 1\n", encoding="utf-8")
    (corpus / "main.py").write_text("def top(): return 2\n", encoding="utf-8")
    (corpus / "vendor" / "lib.py").write_text("def vendored(): pass\n", encoding="utf-8")
    _write_build_config(corpus / "graphify-out", excludes=["vendor"])

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True

    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    sources = {n.get("source_file", "") for n in graph["nodes"]}
    assert any("src/app.py" in s for s in sources) and any("main.py" in s for s in sources)
    assert not any("vendor/lib.py" in s for s in sources), (
        "rebuild silently re-included an excluded path (#1886)"
    )


def test_graphify_root_preserves_absolute_when_user_supplied(tmp_path):
    """When the caller supplies an absolute path, ``.graphify_root`` stores
    that absolute form verbatim — preserving explicit-absolute intent."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "lib.py").write_text("def f(): pass\n", encoding="utf-8")
    assert _rebuild_code(corpus, acquire_lock=False) is True

    saved = (corpus / "graphify-out" / ".graphify_root").read_text(encoding="utf-8")
    assert saved == str(corpus), (
        f"absolute caller path must be preserved as-is; got {saved!r}"
    )


def test_rebuild_code_deleted_cwd_without_repo_root_returns_false(tmp_path, monkeypatch, capsys):
    """Detached hooks can inherit a CWD that no longer exists.

    Without GRAPHIFY_REPO_ROOT, the rebuild should fail cleanly before creating
    relative graphify-out queue/lock files.
    """
    from graphify.watch import _rebuild_code

    old_cwd = Path.cwd()
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.delenv("GRAPHIFY_REPO_ROOT", raising=False)

    os.chdir(gone)
    gone.rmdir()
    try:
        assert _rebuild_code(Path("."), changed_paths=[Path("lib.py")]) is False
    finally:
        os.chdir(old_cwd)

    out = capsys.readouterr().out
    assert "current working directory no longer exists" in out


def test_rebuild_code_deleted_cwd_uses_graphify_repo_root(tmp_path, monkeypatch):
    """GRAPHIFY_REPO_ROOT lets detached hook rebuilds recover from a deleted CWD."""
    from graphify.watch import _rebuild_code

    old_cwd = Path.cwd()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "lib.py").write_text("def f(): pass\n", encoding="utf-8")
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.setenv("GRAPHIFY_REPO_ROOT", str(corpus))

    os.chdir(gone)
    gone.rmdir()
    try:
        assert _rebuild_code(
            Path("."),
            changed_paths=[Path("lib.py")],
            no_cluster=True,
        ) is True
        assert Path.cwd().resolve() == corpus.resolve()
        assert (corpus / "graphify-out" / "graph.json").exists()
    finally:
        os.chdir(old_cwd)


def test_rebuild_code_evicts_nodes_from_deleted_files(tmp_path):
    """#1007: graphify update (_rebuild_code with no changed_paths) must remove
    nodes and edges from files deleted since the last run."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()

    (corpus / "auth.py").write_text(
        "def login(): pass\ndef logout(): pass\n", encoding="utf-8"
    )
    (corpus / "utils.py").write_text(
        "def format_date(): pass\n", encoding="utf-8"
    )

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_labels_before = {n["label"] for n in data.get("nodes", [])}
    assert "format_date()" in node_labels_before

    (corpus / "utils.py").unlink()

    assert _rebuild_code(corpus, acquire_lock=False) is True
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_labels_after = {n["label"] for n in data.get("nodes", [])}
    assert "format_date()" not in node_labels_after, "stale function node from deleted file must be evicted"
    assert "login()" in node_labels_after, "nodes from surviving file must be kept"


def _add_unrelated_semantic_pair(graph_path):
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    data["nodes"].extend([
        {"id": "docs_topic", "label": "DocsTopic", "file_type": "concept"},
        {"id": "shared_concept", "label": "SharedConcept", "file_type": "concept"},
    ])
    data["links"].append({
        "source": "docs_topic",
        "target": "shared_concept",
        "relation": "related_to",
    })
    data["hyperedges"] = [{
        "id": "semantic_context",
        "label": "Semantic context",
        "nodes": ["docs_topic", "shared_concept"],
    }]
    graph_path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    "changed_paths",
    [None, [Path("doc.md")]],
    ids=["full-update", "incremental-doc-update"],
)
def test_rebuild_code_preserves_hyperedges_for_rebuilt_surviving_source(
    tmp_path, changed_paths
):
    """#1755: AST-only updates must not drop semantic hyperedges whose members survive."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.md").write_text(
        "# Design\n\n## Flow\n\nDetails.\n", encoding="utf-8"
    )

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert {"doc", "doc_design"} <= {node["id"] for node in data["nodes"]}
    data["hyperedges"] = [{
        "id": "doc_flow_group",
        "label": "Doc flow group",
        "nodes": ["doc", "doc_design"],
        "relation": "implements",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": "doc.md",
    }]
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    assert _rebuild_code(
        corpus,
        changed_paths=changed_paths,
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    assert after["hyperedges"] == [{
        "id": "doc_flow_group",
        "label": "Doc flow group",
        "nodes": ["doc", "doc_design"],
        "relation": "implements",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": "doc.md",
    }]


@pytest.mark.parametrize(
    "changed_paths",
    [None, [Path("auth.md")]],
    ids=["full-update", "incremental-doc-update"],
)
def test_rebuild_code_preserves_semantic_edges_from_reextracted_doc(
    tmp_path, changed_paths
):
    """#1865: AST-only updates must not evict semantic edges whose source_file
    is a re-extracted document; only that source's AST-tier edges are replaced."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "auth.md").write_text(
        "# Token Validation\n\nVerifies bearer tokens.\n", encoding="utf-8"
    )
    (corpus / "login.md").write_text(
        "# Session Verification\n\nVerifies login sessions.\n", encoding="utf-8"
    )

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in data["nodes"]}
    assert {"auth_token_validation", "login_session_verification"} <= node_ids

    data["links"].extend([
        {
            "source": "auth_token_validation",
            "target": "login_session_verification",
            "relation": "semantically_similar_to",
            "confidence": "INFERRED",
            "source_file": "auth.md",
        },
        # A stale AST-tier edge of the same source must still be evicted.
        {
            "source": "auth_token_validation",
            "target": "login_session_verification",
            "relation": "references",
            "_origin": "ast",
            "source_file": "auth.md",
        },
    ])
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    assert _rebuild_code(
        corpus,
        changed_paths=changed_paths,
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    relations = {
        (e.get("source"), e.get("target"), e.get("relation"))
        for e in after["links"]
    }
    assert (
        "auth_token_validation", "login_session_verification", "semantically_similar_to"
    ) in relations, "semantic edge from a re-extracted doc must survive an AST-only update"
    assert (
        "auth_token_validation", "login_session_verification", "references"
    ) not in relations, "stale AST-tier edge of a re-extracted source must be evicted"


@pytest.mark.parametrize(
    "changed_paths",
    [None, [Path("only.py")]],
    ids=["full-update", "incremental-update"],
)
def test_rebuild_code_prunes_final_deleted_file(tmp_path, changed_paths):
    """Deleting the final code file must reconcile the existing graph."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    only = corpus / "only.py"
    only.write_text("def only_fn():\n    return 1\n", encoding="utf-8")

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    _add_unrelated_semantic_pair(graph_path)
    before = json.loads(graph_path.read_text(encoding="utf-8"))
    code_node_id = next(n["id"] for n in before["nodes"] if n.get("source_file") == "only.py")
    before["hyperedges"].append({
        "id": "code_context",
        "label": "Code context",
        "nodes": [code_node_id],
        "source_file": "only.py",
    })
    before["nodes"].append({
        "id": "sourceless_ast_stub",
        "label": "ExternalType",
        "file_type": "class",
        "_origin": "ast",
    })
    graph_path.write_text(json.dumps(before), encoding="utf-8")

    only.unlink()
    assert _rebuild_code(
        corpus,
        changed_paths=changed_paths,
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    assert not any(n.get("source_file") == "only.py" for n in after["nodes"])
    assert {"docs_topic", "shared_concept"} <= {n["id"] for n in after["nodes"]}
    assert any(
        e.get("source") == "docs_topic" and e.get("target") == "shared_concept"
        for e in after["links"]
    )
    assert {he["id"] for he in after["hyperedges"]} == {"semantic_context"}
    assert "sourceless_ast_stub" not in {n["id"] for n in after["nodes"]}


def test_rebuild_code_prunes_renamed_source_not_listed_by_hook(tmp_path):
    """A hook-style rename list may contain only the destination path."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    old = corpus / "old.py"
    old.write_text("def old_fn():\n    return 1\n", encoding="utf-8")

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    _add_unrelated_semantic_pair(graph_path)

    renamed = corpus / "renamed.py"
    old.rename(renamed)
    assert _rebuild_code(
        corpus,
        changed_paths=[Path("renamed.py")],
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    sources = {n.get("source_file") for n in after["nodes"]}
    assert "old.py" not in sources
    assert "renamed.py" in sources
    assert {"docs_topic", "shared_concept"} <= {n["id"] for n in after["nodes"]}
    assert any(
        e.get("source") == "docs_topic" and e.get("target") == "shared_concept"
        for e in after["links"]
    )


def test_rebuild_code_normalizes_preserved_source_paths(tmp_path):
    """An incremental rebuild must not treat ./foo.py as a deleted live source."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    foo = corpus / "foo.py"
    bar = corpus / "bar.py"
    foo.write_text("def foo_fn():\n    return 1\n", encoding="utf-8")
    bar.write_text("def bar_fn():\n    return 1\n", encoding="utf-8")

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    for item in data["nodes"] + data["links"]:
        if item.get("source_file") == "foo.py":
            item["source_file"] = "./foo.py"
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    bar.write_text("def updated_bar_fn():\n    return 2\n", encoding="utf-8")
    assert _rebuild_code(
        corpus,
        changed_paths=[Path("bar.py")],
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "foo_fn()" in {n.get("label") for n in after["nodes"]}


def test_rebuild_code_prunes_renamed_ast_backed_document(tmp_path):
    """Destination-only rename reconciliation also covers AST-backed docs."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    old = corpus / "old.md"
    old.write_text("# Old heading\n", encoding="utf-8")

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    renamed = corpus / "renamed.md"
    old.rename(renamed)
    assert _rebuild_code(
        corpus,
        changed_paths=[Path("renamed.md")],
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    sources = {n.get("source_file") for n in after["nodes"]}
    assert "old.md" not in sources
    assert "renamed.md" in sources


def test_rebuild_code_evicts_removed_symbol_from_surviving_file(tmp_path):
    """#1116: graphify update (_rebuild_code with no changed_paths) must prune a
    symbol removed from a file that still exists — and its inbound call edge —
    without dropping genuine semantic nodes that share the surviving file."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()

    (corpus / "a.py").write_text(
        "def foo(): pass\ndef bar(): pass\n", encoding="utf-8"
    )
    (corpus / "b.py").write_text(
        "from a import foo\n\ndef caller():\n    foo()\n", encoding="utf-8"
    )

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))

    def labels(d):
        return {n["label"] for n in d.get("nodes", [])}

    def id_for(d, label):
        return next(n["id"] for n in d.get("nodes", []) if n["label"] == label)

    def edges(d):
        return d.get("links", d.get("edges", []))

    before = labels(data)
    assert {"foo()", "bar()", "caller()"} <= before
    foo_id = id_for(data, "foo()")
    caller_id = id_for(data, "caller()")
    assert any(
        {e.get("source"), e.get("target")} == {caller_id, foo_id}
        for e in edges(data)
    ), "cross-file caller->foo call edge must exist before removal"

    # Pre-seed a semantic node on the surviving a.py (no AST id, no _origin
    # marker). A naive "evict every re-extracted file's nodes by source_file"
    # fix would wrongly delete this; the identity-based fix must keep it.
    data["nodes"].append({
        "id": "a_authconcept",
        "label": "AuthConcept",
        "file_type": "concept",
        "source_file": "a.py",
    })
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    # Remove foo() from a.py (keep bar); leave b.py untouched.
    (corpus / "a.py").write_text("def bar(): pass\n", encoding="utf-8")

    # No force=True: a symbol removed from a re-extracted file is a legitimate
    # shrink, so the shrink-guard must let `graphify update` refresh the graph
    # without --force (the lost node belongs to a rebuilt source).
    assert _rebuild_code(corpus, acquire_lock=False) is True
    after_data = json.loads(graph_path.read_text(encoding="utf-8"))
    after = labels(after_data)

    assert "foo()" not in after, "removed symbol must be pruned from surviving file"
    assert not any(
        e.get("source") == foo_id or e.get("target") == foo_id
        for e in edges(after_data)
    ), "dangling edge to the removed symbol must be dropped"
    assert "bar()" in after, "surviving symbol in the same file must be kept"
    assert "caller()" in after, "unchanged file's nodes must be kept"
    assert "AuthConcept" in after, "semantic node on a surviving file must not be evicted"


def test_rebuild_code_preupgrade_marker_less_node_one_cycle_lag(tmp_path):
    """#1118 backward-compat: a graph.json built before #1116 has no `_origin`
    markers. On the first `graphify update` after upgrading, a symbol removed
    from a surviving file is NOT pruned that cycle — its old node carries no
    marker, so the new drop-rule skips it. This is a deliberate one-cycle lag
    (no data loss); it self-heals once the node has been stamped `_origin="ast"`
    (which a full re-extraction does for every surviving symbol)."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("def bar(): pass\n", encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text(encoding="utf-8"))

    def labels(d):
        return {n["label"] for n in d.get("nodes", [])}

    # Simulate a pre-#1116 graph: strip every `_origin` marker, then inject a
    # stale AST node for a symbol no longer present in a.py's source — also
    # marker-less, exactly as a pre-upgrade graph would carry it.
    for n in data["nodes"]:
        n.pop("_origin", None)
    data["nodes"].append({
        "id": "a_foo",
        "label": "foo()",
        "file_type": "function",
        "source_file": "a.py",
    })
    graph_path.write_text(json.dumps(data), encoding="utf-8")

    # First update after "upgrade" (full rebuild, no changed_paths): the stale
    # node has no marker, so the drop-rule skips it and it survives this cycle.
    assert _rebuild_code(corpus, acquire_lock=False, force=True) is True
    after = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "foo()" in labels(after), (
        "pre-upgrade marker-less stale node must survive the first update — "
        "documented one-cycle backward-compat lag (#1118)"
    )

    # Once stamped (a full re-extraction stamps every surviving symbol), the
    # drop-rule applies on the next update and the stale node self-heals away.
    for n in after["nodes"]:
        if n["label"] == "foo()":
            n["_origin"] = "ast"
    graph_path.write_text(json.dumps(after), encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False, force=True) is True
    healed = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "foo()" not in labels(healed), (
        "once carrying _origin=ast, the stale node is pruned on the next "
        "update (self-heal)"
    )
    assert "bar()" in labels(healed), "surviving symbol must be kept throughout"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_lock_non_blocking_does_not_clobber_holder(tmp_path):
    """GH-858: a non-blocking caller that fails to acquire the lock must not
    truncate the holder's PID payload."""
    out = tmp_path / "graphify-out"
    lock_path = out / ".rebuild.lock"
    with _rebuild_lock(out) as outer:
        assert outer is True
        held_contents = lock_path.read_text(encoding="utf-8")
        with _rebuild_lock(out, blocking=False) as inner:
            assert inner is False
            # Holder's PID line must still be intact.
            assert lock_path.read_text(encoding="utf-8") == held_contents


def test_rebuild_code_is_idempotent_when_cluster_ids_flap(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

    calls = {"n": 0}

    def flaky_cluster(G):
        calls["n"] += 1
        nodes = sorted(G.nodes())
        if calls["n"] % 2 == 1:
            return {100: nodes}
        return {7: nodes}

    monkeypatch.setattr(cluster_mod, "cluster", flaky_cluster)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    graph_path = tmp_path / "graphify-out" / "graph.json"
    report_path = tmp_path / "graphify-out" / "GRAPH_REPORT.md"
    first_graph = graph_path.read_text(encoding="utf-8")
    first_report = report_path.read_text(encoding="utf-8")

    assert _rebuild_code(tmp_path)
    second_graph = graph_path.read_text(encoding="utf-8")
    second_report = report_path.read_text(encoding="utf-8")

    assert first_graph == second_graph
    assert first_report == second_report


def test_rebuild_code_skips_cluster_when_topology_unchanged(tmp_path, monkeypatch):
    from graphify import cluster as cluster_mod
    from graphify.watch import _rebuild_code

    src = tmp_path / "app.py"
    src.write_text("def alpha():\n    return 1\n\ndef beta():\n    return alpha()\n", encoding="utf-8")

    calls = {"n": 0}

    def cluster_once(G):
        calls["n"] += 1
        if calls["n"] > 1:
            raise AssertionError("cluster() should be skipped when topology is unchanged")
        return {0: sorted(G.nodes())}

    monkeypatch.setattr(cluster_mod, "cluster", cluster_once)
    monkeypatch.setattr(cluster_mod, "score_all", lambda _G, comm: {cid: 1.0 for cid in comm})

    assert _rebuild_code(tmp_path)
    assert _rebuild_code(tmp_path)
    assert calls["n"] == 1


# --- .graphifyignore honored in watch handler (gh-928) ---


def _watchdog_available() -> bool:
    try:
        import watchdog  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _watchdog_available(), reason="watchdog not installed")
def test_watch_handler_honors_graphifyignore(tmp_path, monkeypatch):
    """gh-928: the watch Handler must short-circuit paths matching
    .graphifyignore so busy volumes (node_modules churn, build artefacts,
    Time Machine writes, …) don't wake the rebuild pipeline.
    """
    import threading
    from graphify import watch as watch_mod

    watch_root = tmp_path / ".hidden-parent" / "corpus"
    watch_root.mkdir(parents=True)
    (watch_root / ".graphifyignore").write_text("node_modules/\nbuild/\n", encoding="utf-8")
    (watch_root / "node_modules").mkdir()
    (watch_root / "build").mkdir()

    rebuild_calls: list[Path] = []
    notify_calls: list[Path] = []
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: rebuild_calls.append(p) or True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: notify_calls.append(p))

    # Run watch() in a thread with a short debounce so we can verify the
    # post-debounce dispatch path actually runs on real events.
    t = threading.Thread(
        target=watch_mod.watch,
        args=(watch_root,),
        kwargs={"debounce": 0.2},
        daemon=True,
    )
    t.start()
    time.sleep(0.5)  # let observer.start() settle

    # Ignored writes — handler must drop these.
    (watch_root / "node_modules" / "junk.js").write_text("// noise\n", encoding="utf-8")
    (watch_root / "build" / "out.py").write_text("x = 1\n", encoding="utf-8")
    time.sleep(1.0)
    assert rebuild_calls == [], "ignored writes triggered a rebuild"
    assert notify_calls == [], "ignored writes triggered a notify"

    # Non-ignored write — handler must accept and (after debounce) dispatch.
    (watch_root / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not rebuild_calls:
        time.sleep(0.1)
    assert rebuild_calls, "non-ignored .py write should have triggered _rebuild_code"


@pytest.mark.skipif(not _watchdog_available(), reason="watchdog not installed")
def test_watch_loads_graphifyignore_once(tmp_path, monkeypatch):
    """gh-928: .graphifyignore must be parsed exactly once at watch() startup,
    not per filesystem event. Otherwise busy volumes re-read the file
    thousands of times per second.
    """
    import threading
    from graphify import watch as watch_mod
    from graphify import detect as detect_mod

    (tmp_path / ".graphifyignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()

    calls = {"n": 0}
    real_loader = detect_mod._load_graphifyignore

    def counting_loader(root):
        calls["n"] += 1
        return real_loader(root)

    # Patch the symbol the watch module imported at module-load time.
    monkeypatch.setattr(watch_mod, "_load_graphifyignore", counting_loader)
    monkeypatch.setattr(watch_mod, "_rebuild_code", lambda p, **kw: True)
    monkeypatch.setattr(watch_mod, "_notify_only", lambda p: None)

    t = threading.Thread(target=watch_mod.watch, args=(tmp_path,), kwargs={"debounce": 0.2}, daemon=True)
    t.start()
    time.sleep(0.5)

    # Generate many events; loader must not be called again.
    for i in range(50):
        (tmp_path / "ignored" / f"f{i}.py").write_text("x\n", encoding="utf-8")
    time.sleep(0.7)
    assert calls["n"] == 1, f"_load_graphifyignore called {calls['n']} times; expected 1"


# --- _check_shrink: silent-corruption guard with explicit-deletion bypass ---

def _shrink_payload(n: int) -> dict:
    """Build a minimal graph-data dict with *n* placeholder nodes."""
    return {"nodes": [{"id": f"n{i}"} for i in range(n)], "links": []}


def test_check_shrink_blocks_silent_shrink(capsys):
    """Default case: smaller new graph + no force + no declared deletions = refuse."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
    )
    assert ok is False
    captured = capsys.readouterr()
    assert "Refusing to overwrite" in captured.err
    assert "80 nodes" in captured.err and "100" in captured.err


def test_check_shrink_allows_force_override():
    """force=True bypasses the guard regardless of node delta."""
    ok = _check_shrink(
        force=True,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(1),
    )
    assert ok is True


def test_check_shrink_allows_explicit_deletions(capsys):
    """Caller declared deletions → shrink is expected → guard skipped silently."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        had_explicit_deletions=True,
    )
    assert ok is True
    # And critically, no scary warning is printed when the shrink is intentional.
    assert "Refusing to overwrite" not in capsys.readouterr().err


def test_check_shrink_allows_no_existing_data():
    """First-run case: no existing graph → guard inert."""
    ok = _check_shrink(
        force=False,
        existing_data={},
        new_data=_shrink_payload(50),
    )
    assert ok is True


def test_check_shrink_allows_shrink_within_rebuilt_sources(capsys):
    """#1116: a symbol removed from a re-extracted file is a legitimate shrink —
    every lost node belongs to a rebuilt source, so the write proceeds (no --force)."""
    existing = {"nodes": [
        {"id": "a", "source_file": "m.py"},
        {"id": "b", "source_file": "m.py"},
        {"id": "c", "source_file": "other.py"},
    ], "links": []}
    new = {"nodes": [
        {"id": "a", "source_file": "m.py"},
        {"id": "c", "source_file": "other.py"},
    ], "links": []}
    ok = _check_shrink(False, existing, new, rebuilt_sources={"m.py"})
    assert ok is True
    assert "Refusing to overwrite" not in capsys.readouterr().err


def test_check_shrink_blocks_shrink_outside_rebuilt_sources(capsys):
    """The guard's real job is intact: a node lost from a file we did NOT re-extract
    (the failed-chunk signal) is still refused even with rebuilt_sources set."""
    existing = {"nodes": [
        {"id": "a", "source_file": "m.py"},
        {"id": "z", "source_file": "untouched.py"},
    ], "links": []}
    new = {"nodes": [{"id": "a", "source_file": "m.py"}], "links": []}
    ok = _check_shrink(False, existing, new, rebuilt_sources={"m.py"})
    assert ok is False
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_check_shrink_allows_growth():
    """new > existing is always fine."""
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(50),
        new_data=_shrink_payload(60),
    )
    assert ok is True


def test_check_shrink_unlinks_tmp_on_refuse(tmp_path):
    """When refusing, the temp graph file gets cleaned up so it can't leak across runs."""
    tmp = tmp_path / "graph.tmp.json"
    tmp.write_text("{}", encoding="utf-8")
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        tmp=tmp,
    )
    assert ok is False
    assert not tmp.exists()


def test_check_shrink_keeps_tmp_when_deletions_declared(tmp_path):
    """Mirror of the above: if the caller declared deletions, the tmp file is NOT unlinked
    because the caller is going to swap it into place. Regression guard against a future
    bug where the tmp cleanup leaks out of the refuse branch.
    """
    tmp = tmp_path / "graph.tmp.json"
    tmp.write_text("{}", encoding="utf-8")
    ok = _check_shrink(
        force=False,
        existing_data=_shrink_payload(100),
        new_data=_shrink_payload(80),
        tmp=tmp,
        had_explicit_deletions=True,
    )
    assert ok is True
    assert tmp.exists()


# --- _rebuild_code integration: post-commit delete scenario ---

@pytest.mark.skipif(sys.platform == "win32", reason="git CLI behaviour varies on Windows runners")
def test_rebuild_code_prunes_deleted_file_nodes(tmp_path):
    """End-to-end probe of the post-commit-delete bug fix.

    Build a tiny graph, delete one of its source files, then call _rebuild_code
    with the deleted path in changed_paths. Without the fix this raises the
    shrink guard and refuses to write; with the fix the deleted file's nodes
    are pruned and graph.json is rewritten.
    """
    from graphify.watch import _rebuild_code

    # Set up a minimal "project" with two Python files in a git repo so detect
    # treats it as a real corpus.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True,
    )

    keep = tmp_path / "keep.py"
    drop = tmp_path / "drop.py"
    keep.write_text("def keep_fn():\n    return 1\n", encoding="utf-8")
    drop.write_text("def drop_fn():\n    return 2\n", encoding="utf-8")

    # Initial build covers both files.
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ok = _rebuild_code(tmp_path, no_cluster=True)
        assert ok is True
        graph_path = tmp_path / "graphify-out" / "graph.json"
        assert graph_path.exists()
        before = json.loads(graph_path.read_text(encoding="utf-8"))
        before_sources = {n.get("source_file") for n in before.get("nodes", [])}
        assert "drop.py" in before_sources

        # Now delete drop.py and re-run with it in the change list. This is what
        # the post-commit hook does when git diff --name-only HEAD~1 HEAD includes
        # a deletion: the path is passed to _rebuild_code even though it no
        # longer exists on disk.
        drop.unlink()
        ok = _rebuild_code(
            tmp_path,
            changed_paths=[Path("drop.py")],
            no_cluster=True,
        )
        assert ok is True, "rebuild should succeed even though the graph shrinks"

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        after_sources = {n.get("source_file") for n in after.get("nodes", [])}
        assert "drop.py" not in after_sources, "deleted file's nodes should be pruned"
        assert "keep.py" in after_sources, "untouched file's nodes should survive"
    finally:
        os.chdir(cwd)


def test_rebuild_code_accepts_repo_relative_changed_path_for_subdir_root(tmp_path):
    """#1348: git-hook paths are repo-root-relative even when the graph root is a subdir."""
    from graphify.watch import _rebuild_code

    src = tmp_path / "src"
    src.mkdir()
    app = src / "app.py"
    app.write_text("def old_name():\n    return 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(Path("src"), no_cluster=True, acquire_lock=False) is True
        graph_path = src / "graphify-out" / "graph.json"
        before = json.loads(graph_path.read_text(encoding="utf-8"))
        assert "old_name()" in {n.get("label") for n in before.get("nodes", [])}

        app.write_text("def new_name():\n    return 2\n", encoding="utf-8")
        assert _rebuild_code(
            Path("src"),
            changed_paths=[Path("src/app.py")],
            no_cluster=True,
            acquire_lock=False,
            force=True,
        ) is True

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        labels = {n.get("label") for n in after.get("nodes", [])}
        assert "old_name()" not in labels
        assert "new_name()" in labels
    finally:
        os.chdir(cwd)


@pytest.mark.parametrize(
    "changed_paths",
    [None, [Path("src/app.py")]],
    ids=["full-update", "incremental-update"],
)
def test_rebuild_code_subdir_preserves_outside_ast_nodes(tmp_path, changed_paths):
    """A full rebuild of a subdirectory must not prune graph data outside it."""
    from graphify.watch import _rebuild_code

    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "app.py").write_text("def outside_fn():\n    return 2\n", encoding="utf-8")
    (src / "app.py").write_text("def inside_fn():\n    return 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(Path("src"), no_cluster=True, acquire_lock=False) is True
        graph_path = src / "graphify-out" / "graph.json"
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        inside_id = next(n["id"] for n in data["nodes"] if n.get("label") == "inside_fn()")
        outside_source = "app.py"
        data["nodes"].extend([
            {
                "id": "outside_ast",
                "label": "outside_fn()",
                "file_type": "function",
                "source_file": outside_source,
                "_origin": "ast",
            },
            {
                "id": "stale_inside_ast",
                "label": "stale_inside_fn()",
                "file_type": "function",
                "source_file": "src/deleted.py",
                "_origin": "ast",
            },
        ])
        data["links"].append({
            "source": "outside_ast",
            "target": inside_id,
            "relation": "calls",
            "source_file": outside_source,
        })
        graph_path.write_text(json.dumps(data), encoding="utf-8")

        assert _rebuild_code(
            Path("src"),
            changed_paths=changed_paths,
            no_cluster=True,
            acquire_lock=False,
        ) is True
        after = json.loads(graph_path.read_text(encoding="utf-8"))
        node_ids = {n["id"] for n in after["nodes"]}
        assert "outside_ast" in node_ids
        assert "stale_inside_ast" not in node_ids
        outside_node = next(n for n in after["nodes"] if n["id"] == "outside_ast")
        assert outside_node["source_file"] == outside_source
        outside_edge = next(
            e
            for e in after["links"]
            if e.get("source") == "outside_ast" and e.get("target") == inside_id
        )
        assert outside_edge["source_file"] == outside_source
    finally:
        os.chdir(cwd)


def test_rebuild_code_subdir_survives_absolute_to_relative_invocation(tmp_path):
    """Persisted source paths keep their meaning when invocation style changes."""
    from graphify.watch import _rebuild_code

    src = tmp_path / "src"
    src.mkdir()
    old = src / "old.py"
    old.write_text("def old_fn():\n    return 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(src, no_cluster=True, acquire_lock=False) is True
        graph_path = src / "graphify-out" / "graph.json"
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        data["nodes"].append({
            "id": "local_semantic",
            "label": "LocalSemantic",
            "file_type": "concept",
            "source_file": "old.py",
        })
        graph_path.write_text(json.dumps(data), encoding="utf-8")

        assert _rebuild_code(Path("src"), no_cluster=True, acquire_lock=False) is True
        rebased = json.loads(graph_path.read_text(encoding="utf-8"))
        semantic = next(n for n in rebased["nodes"] if n["id"] == "local_semantic")
        assert semantic["source_file"] == "src/old.py"

        old.rename(src / "renamed.py")

        assert _rebuild_code(Path("src"), no_cluster=True, acquire_lock=False) is True
        after = json.loads(graph_path.read_text(encoding="utf-8"))
        sources = {n.get("source_file") for n in after["nodes"]}
        assert "old.py" not in sources
        assert "src/renamed.py" in sources
    finally:
        os.chdir(cwd)


def test_rebuild_code_prunes_legacy_watch_relative_subdir_source(tmp_path):
    """Pre-rebase subdirectory graphs stored source_file relative to watch_root."""
    from graphify.watch import _rebuild_code

    src = tmp_path / "src"
    src.mkdir()
    old = src / "old.py"
    old.write_text("def old_fn():\n    return 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert _rebuild_code(Path("src"), no_cluster=True, acquire_lock=False) is True
        graph_path = src / "graphify-out" / "graph.json"
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        for item in data["nodes"] + data["links"]:
            source = item.get("source_file")
            if source and source.startswith("src/"):
                item["source_file"] = source.removeprefix("src/")
        graph_path.write_text(json.dumps(data), encoding="utf-8")

        old.rename(src / "renamed.py")
        assert _rebuild_code(
            Path("src"),
            changed_paths=[Path("src/renamed.py")],
            no_cluster=True,
            acquire_lock=False,
        ) is True

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        sources = {n.get("source_file") for n in after["nodes"]}
        assert "old.py" not in sources
        assert "src/renamed.py" in sources
    finally:
        os.chdir(cwd)


def test_rebuild_code_does_not_update_root_marker_when_write_is_refused(tmp_path, monkeypatch):
    """A rejected candidate keeps the marker paired with the existing graph."""
    from graphify import watch as watch_mod

    src = tmp_path / "src"
    src.mkdir()
    app = src / "app.py"
    app.write_text("def before():\n    return 1\n", encoding="utf-8")

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert watch_mod._rebuild_code(src, no_cluster=True, acquire_lock=False) is True
        marker = src / "graphify-out" / ".graphify_root"
        assert marker.read_text(encoding="utf-8") == str(src)

        app.write_text("def after():\n    return 2\n", encoding="utf-8")
        monkeypatch.setattr(watch_mod, "_check_shrink", lambda *args, **kwargs: False)
        assert watch_mod._rebuild_code(
            Path("src"), no_cluster=True, acquire_lock=False
        ) is False
        assert marker.read_text(encoding="utf-8") == str(src)
    finally:
        os.chdir(cwd)


@pytest.mark.skipif(sys.platform == "win32", reason="symlink setup differs on Windows")
def test_rebuild_code_incremental_rename_preserves_symlink_source_path(tmp_path):
    """Changed files under followed symlinks retain their watched lexical path."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    real = corpus / "real"
    real.mkdir()
    (corpus / ".graphifyignore").write_text("real/\n", encoding="utf-8")
    old = real / "old.py"
    old.write_text("def linked_fn():\n    return 1\n", encoding="utf-8")
    (corpus / "linked").symlink_to(real, target_is_directory=True)

    assert _rebuild_code(
        corpus,
        follow_symlinks=True,
        no_cluster=True,
        acquire_lock=False,
    ) is True
    graph_path = corpus / "graphify-out" / "graph.json"

    first = real / "first.py"
    old.rename(first)
    assert _rebuild_code(
        corpus,
        changed_paths=[Path("linked/first.py")],
        follow_symlinks=True,
        no_cluster=True,
        acquire_lock=False,
    ) is True

    second = real / "second.py"
    first.rename(second)
    assert _rebuild_code(
        corpus,
        changed_paths=[Path("linked/second.py")],
        follow_symlinks=True,
        no_cluster=True,
        acquire_lock=False,
    ) is True

    after = json.loads(graph_path.read_text(encoding="utf-8"))
    sources = {n.get("source_file") for n in after["nodes"]}
    assert "linked/old.py" not in sources
    assert "linked/first.py" not in sources
    assert "linked/second.py" in sources


# --- #1059: pending-changes queue prevents commit drops under lock contention ---


def test_queue_and_drain_pending_round_trip(tmp_path):
    """_queue_pending writes one path per line; _drain_pending reads + unlinks
    and returns the same set of paths."""
    from graphify.watch import _queue_pending, _drain_pending, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    paths = [Path("a.py"), Path("sub/b.py"), Path("c.md")]
    _queue_pending(out, paths)

    pending_file = out / _PENDING_FILENAME
    assert pending_file.exists()
    # Each path written on its own line.
    assert pending_file.read_text(encoding="utf-8").splitlines() == [
        "a.py", "sub/b.py", "c.md",
    ]

    drained = _drain_pending(out)
    assert drained == paths
    # Drain unlinks so subsequent callers see an empty queue.
    assert not pending_file.exists()
    assert _drain_pending(out) == []


def test_drain_pending_dedupes_and_skips_blank_lines(tmp_path):
    """Repeated appends across concurrent contenders must dedupe; partial
    writes leaving blank lines must not poison the merge."""
    from graphify.watch import _queue_pending, _drain_pending

    out = tmp_path / "graphify-out"
    _queue_pending(out, [Path("a.py"), Path("b.py")])
    _queue_pending(out, [Path("b.py"), Path("c.py")])
    # Simulate a torn write leaving an empty line.
    with open(out / ".pending_changes", "a", encoding="utf-8") as fh:
        fh.write("\n   \n")

    drained = _drain_pending(out)
    assert drained == [Path("a.py"), Path("b.py"), Path("c.py")]


def test_queue_pending_noop_on_empty_list(tmp_path):
    """Empty change set must not create an empty .pending_changes file."""
    from graphify.watch import _queue_pending, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    _queue_pending(out, [])
    assert not (out / _PENDING_FILENAME).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_queues_on_lock_contention(tmp_path, monkeypatch, capsys):
    """#1059: when the rebuild lock is held, an incremental hook must queue
    its changed_paths to .pending_changes and print 'queued' instead of
    silently dropping the change set."""
    from graphify.watch import _rebuild_code, _rebuild_lock, _PENDING_FILENAME

    out = tmp_path / "graphify-out"
    out.mkdir()

    # Hold the lock so the next non-blocking attempt fails. Use a real
    # _rebuild_lock context manager in this same process — flock on the same
    # file descriptor would otherwise be re-entrant on Linux, so we open
    # the file ourselves via the lock helper.
    with _rebuild_lock(out, blocking=False) as outer_got:
        assert outer_got is True

        ok = _rebuild_code(
            tmp_path,
            changed_paths=[Path("a.py"), Path("b.py")],
        )
        assert ok is False

        # Output should say "queued", not "skipping".
        captured = capsys.readouterr().out
        assert "queued" in captured.lower()
        assert "skipping" not in captured.lower()

        # And the paths must have been written to the pending file so the
        # eventual lock-holder can drain them.
        pending = out / _PENDING_FILENAME
        assert pending.exists()
        assert pending.read_text(encoding="utf-8").splitlines() == ["a.py", "b.py"]


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_merges_pending_on_acquire(tmp_path, monkeypatch):
    """#1059: the process that acquires the lock must drain .pending_changes
    and pass the merged change set to the inner rebuild call."""
    from graphify import watch as watch_mod

    out = tmp_path / "graphify-out"
    out.mkdir()
    # Pre-populate the queue as if an earlier contender had dropped its paths.
    watch_mod._queue_pending(out, [Path("queued1.py"), Path("queued2.py")])

    # Snapshot the original BEFORE monkeypatching so we can drive the outer
    # dispatch path while the inner recursive call resolves to our spy.
    orig_rebuild = watch_mod._rebuild_code
    inner_calls: list[list[str]] = []

    def recording_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            paths = kwargs.get("changed_paths") or []
            inner_calls.append([p.as_posix() for p in paths])
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", recording_inner)

    ok = orig_rebuild(
        tmp_path,
        changed_paths=[Path("own.py"), Path("queued1.py")],
    )
    assert ok is True

    # The first inner call must have received the merged + deduped set:
    # own.py first (caller's order preserved), then drained queued1/queued2,
    # with queued1.py deduped against own's prior occurrence.
    assert inner_calls, "inner _rebuild_code should have been called"
    assert inner_calls[0] == ["own.py", "queued1.py", "queued2.py"]

    # And .pending_changes was drained.
    assert not (out / watch_mod._PENDING_FILENAME).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl-only (POSIX)")
def test_rebuild_code_drains_late_arrivals(tmp_path, monkeypatch):
    """#1059: after the primary rebuild, the lock-holder must loop and drain
    any paths queued by hooks that arrived mid-rebuild."""
    from graphify import watch as watch_mod
    from graphify.watch import _rebuild_code as orig_rebuild

    out = tmp_path / "graphify-out"
    out.mkdir()

    inner_calls: list[list[str]] = []
    call_state = {"i": 0}

    def fake_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            paths = [p.as_posix() for p in (kwargs.get("changed_paths") or [])]
            inner_calls.append(paths)
            # Simulate a late-arriving hook that queues during the FIRST
            # inner rebuild only. The outer drain loop must see it.
            call_state["i"] += 1
            if call_state["i"] == 1:
                watch_mod._queue_pending(out, [Path("late.py")])
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", fake_inner)

    ok = orig_rebuild(tmp_path, changed_paths=[Path("own.py")])
    assert ok is True

    # First inner call covers our own change set; second is the late-drain
    # pass that picks up "late.py".
    assert len(inner_calls) >= 2
    assert inner_calls[0] == ["own.py"]
    assert inner_calls[1] == ["late.py"]
    # And the queue is now empty (no further late drains).
    assert not (out / watch_mod._PENDING_FILENAME).exists()


def test_rebuild_code_full_corpus_skips_pending_queue(tmp_path, monkeypatch):
    """#1059: changed_paths=None means a full-corpus rebuild — the queue
    must not be touched on the failure path because there is nothing
    incremental to preserve."""
    from graphify import watch as watch_mod
    from graphify.watch import _rebuild_code as orig_rebuild

    out = tmp_path / "graphify-out"
    out.mkdir()

    # Pre-existing queued paths from an earlier incremental hook.
    watch_mod._queue_pending(out, [Path("earlier.py")])

    # Force the inner call to record what it saw.
    seen: list = []

    def fake_inner(watch_path, **kwargs):
        if kwargs.get("acquire_lock") is False:
            seen.append(kwargs.get("changed_paths"))
        return True

    monkeypatch.setattr(watch_mod, "_rebuild_code", fake_inner)

    ok = orig_rebuild(tmp_path, changed_paths=None)
    assert ok is True
    # Full-corpus rebuild passes None to the inner call (does not merge in
    # the queued paths — a full rebuild already covers them).
    assert seen == [None]
    # The queue still gets drained on entry so stale entries don't leak,
    # but no late-arrival loop runs for the full-corpus path.
    assert not (out / watch_mod._PENDING_FILENAME).exists()


def test_merge_changed_paths_dedupes_in_order():
    """_merge_changed_paths preserves first-seen order and drops dupes."""
    from graphify.watch import _merge_changed_paths

    merged = _merge_changed_paths(
        [Path("a.py"), Path("b.py")],
        None,
        [Path("b.py"), Path("c.py")],
        [Path("a.py")],
    )
    assert [p.as_posix() for p in merged] == ["a.py", "b.py", "c.py"]


def test_rebuild_code_preserves_nodes_from_excluded_but_alive_file(tmp_path, capsys):
    """Fail-closed eviction: a file that leaves the scan corpus (newly ignored)
    but still exists on disk was EXCLUDED, not deleted — its nodes must survive
    an incremental rebuild, with a loud message, instead of being silently
    mass-evicted as stale sources (the docs/brainstorms incident: an upgrade
    started honoring .gitignore and evicted 655 nodes whose files were present).
    """
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    (corpus / "notes").mkdir(parents=True)
    (corpus / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    (corpus / "notes" / "brainstorm.md").write_text(
        "# Brainstorm\n\nA local-only design note.\n", encoding="utf-8"
    )

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    labels = {n["label"] for n in json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]}
    assert "brainstorm.md" in labels

    # The file becomes ignored (leaves the corpus) but stays on disk.
    (corpus / ".graphifyignore").write_text("notes/\n", encoding="utf-8")
    capsys.readouterr()

    assert _rebuild_code(corpus, changed_paths=[Path("auth.py")], acquire_lock=False) is True
    labels = {n["label"] for n in json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]}
    assert "brainstorm.md" in labels, (
        "nodes from an excluded-but-alive file must be preserved, not evicted"
    )
    assert "fail-closed: kept" in capsys.readouterr().out


def test_rebuild_code_still_evicts_when_excluded_file_is_also_deleted(tmp_path):
    """The fail-closed preserve must not weaken true-deletion eviction: once the
    excluded file is actually gone from disk, its nodes are evicted as before."""
    import json
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    (corpus / "notes").mkdir(parents=True)
    (corpus / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    (corpus / "notes" / "brainstorm.md").write_text("# Brainstorm\n", encoding="utf-8")

    assert _rebuild_code(corpus, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"

    (corpus / "notes" / "brainstorm.md").unlink()

    assert _rebuild_code(corpus, changed_paths=[Path("auth.py")], acquire_lock=False) is True
    labels = {n["label"] for n in json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]}
    assert "brainstorm.md" not in labels, "deleted file's nodes must still be evicted"
    assert "login()" in labels
