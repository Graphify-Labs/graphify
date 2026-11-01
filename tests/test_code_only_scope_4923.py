"""#4923: a graph built with `extract --code-only` must stay code-only across
hook-style rebuilds. Assertions are on the final graph only, so the same file
can judge any candidate fix (persisted flag, hook flag, rc key)."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphify.watch import _rebuild_code

DOC_SUFFIXES = (".md", ".mdx", ".qmd")


def _write_corpus(root: Path) -> None:
    (root / "a.py").write_text("def foo():\n    return bar()\n\ndef bar():\n    return 1\n")
    (root / "b.py").write_text("from a import foo\n\ndef baz():\n    return foo()\n")
    (root / "guide.md").write_text("# Guide\n\n## Install\n\ntext\n\n## Usage\n\nmore\n")


def _graphify(root: Path, *args: str) -> subprocess.CompletedProcess:
    # Separate process on purpose: the flag must not survive in memory.
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=root, capture_output=True, text=True,
    )


def _extract_code_only(root: Path) -> None:
    r = _graphify(root, "extract", str(root), "--code-only")
    assert r.returncode == 0, r.stdout + r.stderr


def _graph(root: Path) -> dict:
    return json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _doc_nodes(g: dict) -> list[dict]:
    return [n for n in g["nodes"]
            if str(n.get("source_file", "")).lower().endswith(DOC_SUFFIXES)]


def _labels(g: dict) -> set[str]:
    return {n.get("label", "") for n in g["nodes"]}


@pytest.fixture
def code_only_repo(tmp_path):
    _write_corpus(tmp_path)
    _extract_code_only(tmp_path)
    return tmp_path


# --- precondition: the oracle is meaningful ---------------------------------

def test_code_only_extract_itself_has_no_doc_nodes(code_only_repo):
    g = _graph(code_only_repo)
    assert _doc_nodes(g) == []
    assert any(l.startswith("foo") for l in _labels(g))  # code really indexed


# --- the bug: the two call shapes the hooks use -----------------------------

def test_full_rebuild_keeps_code_only_scope(code_only_repo):
    """post-checkout / post-merge / post-rewrite: _rebuild_code(root)."""
    assert _rebuild_code(code_only_repo, acquire_lock=False) is True
    assert _doc_nodes(_graph(code_only_repo)) == []


def test_incremental_rebuild_keeps_code_only_scope(code_only_repo):
    """post-commit: _rebuild_code(root, changed_paths=[...]) with a doc in the set."""
    (code_only_repo / "guide.md").write_text("# Guide\n\n## Changed\n\nnew\n")
    (code_only_repo / "a.py").write_text("def foo():\n    return 2\n\ndef bar():\n    return 1\n")
    changed = [code_only_repo / "guide.md", code_only_repo / "a.py"]
    assert _rebuild_code(code_only_repo, changed_paths=changed, acquire_lock=False) is True
    assert _doc_nodes(_graph(code_only_repo)) == []


def test_update_cli_keeps_code_only_scope(code_only_repo):
    """`graphify update` is a third rebuild entry point (no hook involved)."""
    r = _graphify(code_only_repo, "update", str(code_only_repo))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _doc_nodes(_graph(code_only_repo)) == []


def test_doc_added_after_extract_stays_out(code_only_repo):
    (code_only_repo / "new.mdx").write_text("# New\n\n## Section\n\ntext\n")
    assert _rebuild_code(code_only_repo, acquire_lock=False) is True
    assert _doc_nodes(_graph(code_only_repo)) == []


# --- controls: a fix must not buy scope by freezing the graph ---------------

def test_code_only_rebuild_still_tracks_new_code(code_only_repo):
    (code_only_repo / "c.py").write_text("def brand_new():\n    return 3\n")
    assert _rebuild_code(code_only_repo, acquire_lock=False) is True
    assert any(l.startswith("brand_new") for l in _labels(_graph(code_only_repo)))


def test_code_only_rebuild_still_tracks_deleted_code(code_only_repo):
    (code_only_repo / "b.py").unlink()
    assert _rebuild_code(code_only_repo, acquire_lock=False) is True
    assert not any(l.startswith("baz") for l in _labels(_graph(code_only_repo)))


def test_default_graph_still_gets_doc_nodes(tmp_path):
    """No code-only scope recorded => behaviour unchanged (#4750 feature)."""
    _write_corpus(tmp_path)
    assert _rebuild_code(tmp_path, acquire_lock=False) is True
    assert _doc_nodes(_graph(tmp_path)) != []


# --- end to end: the issue's literal steps, through a real git hook ---------

def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, check=True)


def _wait_for(pred, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


def test_issue_repro_via_real_post_commit_hook(tmp_path):
    _write_corpus(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "init")
    _extract_code_only(tmp_path)
    assert _graphify(tmp_path, "hook", "install").returncode == 0

    (tmp_path / "a.py").write_text("def foo():\n    return 9\n\ndef bar():\n    return 1\n\ndef added():\n    return 0\n")
    (tmp_path / "guide.md").write_text("# Guide\n\n## Rewritten\n\ntext\n")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-qm", "change")

    # The hook is detached: wait until the new code symbol lands, then judge.
    assert _wait_for(lambda: any(l.startswith("added") for l in _labels(_graph(tmp_path))))
    assert _doc_nodes(_graph(tmp_path)) == []
