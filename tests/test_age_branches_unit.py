"""Tier-1 (pure, DB-free) unit tests for graphify.age_branches
(docs/AGE_PLAN.md Phase 4): branch-graph naming, diff row (de)serialization,
replay/validation, and git-only helpers exercised against a throwaway git
repo in tmp_path (no live Postgres/AGE needed for any of this -- matches
the plan's "tier 1, throwaway git repo in tmpdir" instruction).
"""
from __future__ import annotations

import subprocess

import pytest

from graphify import age_branches as ab


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path):
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _commit(path, filename, content):
    (path / filename).write_text(content)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", f"commit {filename}")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# sanitize_branch_graph_name
# ---------------------------------------------------------------------------

def test_sanitize_branch_graph_name_simple():
    assert ab.sanitize_branch_graph_name("graphify", "feature-x") == "graphify__feature_x"


def test_sanitize_branch_graph_name_within_limit_unchanged():
    name = ab.sanitize_branch_graph_name("graphify", "main")
    assert name == "graphify__main"
    assert len(name.encode("utf-8")) <= 63


def test_sanitize_branch_graph_name_falls_back_to_hash_when_too_long():
    long_branch = "a" * 100
    name = ab.sanitize_branch_graph_name("graphify", long_branch)
    assert len(name.encode("utf-8")) <= 63
    assert "__" in name


def test_sanitize_branch_graph_name_hash_fallback_is_deterministic():
    long_branch = "b" * 100
    n1 = ab.sanitize_branch_graph_name("graphify", long_branch)
    n2 = ab.sanitize_branch_graph_name("graphify", long_branch)
    assert n1 == n2


def test_sanitize_branch_graph_name_different_branches_differ():
    n1 = ab.sanitize_branch_graph_name("graphify", "c" * 100)
    n2 = ab.sanitize_branch_graph_name("graphify", "d" * 100)
    assert n1 != n2


# ---------------------------------------------------------------------------
# diff_to_rows / rows_to_diff round trip
# ---------------------------------------------------------------------------

def _sample_diff():
    return {
        "new_nodes": [{"id": "c", "label": "C", "properties": {"label": "C"}}],
        "removed_nodes": [{"id": "b", "label": "B", "properties": {"label": "B"}}],
        "changed_nodes": [{"id": "a", "old": {"community": 1}, "new": {"community": 2}}],
        "new_edges": [{"source": "a", "target": "c", "relation": "uses", "properties": {}}],
        "removed_edges": [{"source": "a", "target": "b", "relation": "calls", "properties": {}}],
        "changed_edges": [{"source": "x", "target": "y", "relation": "uses",
                            "old": {"confidence": "INFERRED"}, "new": {"confidence": "EXTRACTED"}}],
    }


def test_diff_to_rows_produces_one_row_per_entry():
    diff = _sample_diff()
    rows = ab.diff_to_rows(diff)
    assert len(rows) == 6
    kinds = [k for k, _ in rows]
    assert set(kinds) == {"node_add", "node_del", "node_change", "edge_add", "edge_del", "edge_change"}


def test_diff_to_rows_rows_to_diff_round_trip():
    diff = _sample_diff()
    rows = ab.diff_to_rows(diff)
    reconstructed = ab.rows_to_diff(rows)
    for bucket in diff:
        assert reconstructed[bucket] == diff[bucket]


def test_diff_to_rows_empty_diff_produces_no_rows():
    empty = {b: [] for b in ("new_nodes", "removed_nodes", "changed_nodes",
                              "new_edges", "removed_edges", "changed_edges")}
    assert ab.diff_to_rows(empty) == []


# ---------------------------------------------------------------------------
# replay_branch_diffs: ordering, transition validation, cross-generation
# rejection.
# ---------------------------------------------------------------------------

def test_replay_branch_diffs_no_rows_requires_base_equals_head():
    payload = {"nodes": [], "edges": []}
    result = ab.replay_branch_diffs(payload, [], base_commit_sha="c1", head_commit_sha="c1")
    assert result == payload


def test_replay_branch_diffs_no_rows_but_base_ne_head_raises():
    payload = {"nodes": [], "edges": []}
    with pytest.raises(ValueError, match="no diff rows"):
        ab.replay_branch_diffs(payload, [], base_commit_sha="c1", head_commit_sha="c2")


def test_replay_branch_diffs_single_transition():
    payload = {"nodes": [{"id": "a"}], "edges": []}
    rows = [
        (1, 1, "c1", "c2", "node_add", {"id": "b", "properties": {"label": "B"}}),
    ]
    result = ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="c2")
    assert {n["id"] for n in result["nodes"]} == {"a", "b"}


def test_replay_branch_diffs_multiple_transitions_in_order():
    payload = {"nodes": [{"id": "a"}], "edges": []}
    rows = [
        (1, 1, "c1", "c2", "node_add", {"id": "b", "properties": {"label": "B"}}),
        (2, 1, "c2", "c3", "node_add", {"id": "c", "properties": {"label": "C"}}),
        (3, 1, "c2", "c3", "node_del", {"id": "a", "properties": {}}),
    ]
    result = ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="c3")
    assert {n["id"] for n in result["nodes"]} == {"b", "c"}


def test_replay_branch_diffs_rejects_wrong_base():
    payload = {"nodes": [], "edges": []}
    rows = [(1, 1, "OTHER", "c2", "node_add", {"id": "a", "properties": {}})]
    with pytest.raises(ValueError, match="base_commit_sha"):
        ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="c2")


def test_replay_branch_diffs_rejects_wrong_head():
    payload = {"nodes": [], "edges": []}
    rows = [(1, 1, "c1", "c2", "node_add", {"id": "a", "properties": {}})]
    with pytest.raises(ValueError, match="head_commit_sha"):
        ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="OTHER")


def test_replay_branch_diffs_rejects_non_contiguous_chain():
    payload = {"nodes": [], "edges": []}
    rows = [
        (1, 1, "c1", "c2", "node_add", {"id": "a", "properties": {}}),
        (2, 1, "c3", "c4", "node_add", {"id": "b", "properties": {}}),  # gap: c2 != c3
    ]
    with pytest.raises(ValueError, match="non-contiguous"):
        ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="c4")


def test_replay_branch_diffs_rejects_multiple_generations():
    payload = {"nodes": [], "edges": []}
    rows = [
        (1, 1, "c1", "c2", "node_add", {"id": "a", "properties": {}}),
        (2, 2, "c2", "c3", "node_add", {"id": "b", "properties": {}}),
    ]
    with pytest.raises(ValueError, match="multiple generations"):
        ab.replay_branch_diffs(payload, rows, base_commit_sha="c1", head_commit_sha="c3")


# ---------------------------------------------------------------------------
# _advisory_lock_key
# ---------------------------------------------------------------------------

def test_advisory_lock_key_is_deterministic():
    k1 = ab._advisory_lock_key("repo-1", "main")
    k2 = ab._advisory_lock_key("repo-1", "main")
    assert k1 == k2


def test_advisory_lock_key_differs_per_branch():
    k1 = ab._advisory_lock_key("repo-1", "main")
    k2 = ab._advisory_lock_key("repo-1", "feature")
    assert k1 != k2


def test_advisory_lock_key_fits_in_postgres_bigint():
    key = ab._advisory_lock_key("repo-1", "main")
    assert -(2 ** 63) <= key <= 2 ** 63 - 1


# ---------------------------------------------------------------------------
# Git helpers: throwaway repo in tmp_path, no DB/AGE involved.
# ---------------------------------------------------------------------------

def test_merge_base_finds_common_ancestor(tmp_path):
    _init_repo(tmp_path)
    base_sha = _commit(tmp_path, "base.txt", "base")
    _git(tmp_path, "checkout", "-qb", "feature")
    feature_sha = _commit(tmp_path, "feature.txt", "feature")
    _git(tmp_path, "checkout", "-q", "-")
    main_sha = _commit(tmp_path, "main.txt", "main")

    assert ab.merge_base(tmp_path, "feature", "main") == base_sha
    assert feature_sha and main_sha  # sanity, avoid unused-var lint


def test_merge_base_unknown_ref_returns_none(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "base.txt", "base")
    assert ab.merge_base(tmp_path, "does-not-exist", "HEAD") is None


def test_is_ancestor_true_for_direct_history(tmp_path):
    _init_repo(tmp_path)
    first_sha = _commit(tmp_path, "a.txt", "a")
    second_sha = _commit(tmp_path, "b.txt", "b")
    assert ab.is_ancestor(tmp_path, first_sha, second_sha) is True


def test_is_ancestor_false_for_diverged_history(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "base.txt", "base")
    _git(tmp_path, "checkout", "-qb", "feature")
    feature_sha = _commit(tmp_path, "feature.txt", "feature")
    _git(tmp_path, "checkout", "-q", "-")
    main_sha = _commit(tmp_path, "main.txt", "main")
    assert ab.is_ancestor(tmp_path, feature_sha, main_sha) is False


def test_detect_rebase_false_on_fast_forward(tmp_path):
    _init_repo(tmp_path)
    first_sha = _commit(tmp_path, "a.txt", "a")
    second_sha = _commit(tmp_path, "b.txt", "b")
    assert ab.detect_rebase(tmp_path, first_sha, second_sha) is False


def test_detect_rebase_true_when_old_head_not_ancestor(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "base.txt", "base")
    first_sha = _commit(tmp_path, "a.txt", "a")
    # Amend (rewrite history) so the old head is no longer an ancestor.
    (tmp_path / "a.txt").write_text("a-changed")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "--amend", "-m", "amended")
    new_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert ab.detect_rebase(tmp_path, first_sha, new_head) is True


def test_detect_rebase_false_when_no_old_head():
    assert ab.detect_rebase("/tmp", None, "somesha") is False


def test_detect_rebase_false_when_unchanged():
    assert ab.detect_rebase("/tmp", "samesha", "samesha") is False


# ---------------------------------------------------------------------------
# _extract_graph_at_commit: real extraction via a temporary git worktree.
# ---------------------------------------------------------------------------

def test_extract_graph_at_commit_extracts_historical_state(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    return bar()\n\ndef bar():\n    return 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    old_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    (tmp_path / "a.py").write_text("def foo():\n    return 42\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "simplify")

    G = ab._extract_graph_at_commit(tmp_path, old_sha)
    labels = {data.get("label") for _, data in G.nodes(data=True)}
    assert any("bar" in (label or "") for label in labels)


def test_extract_graph_at_commit_unknown_commit_raises(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "a")
    with pytest.raises(RuntimeError, match="worktree"):
        ab._extract_graph_at_commit(tmp_path, "0" * 40)


def test_extract_graph_at_commit_cwd_none_uses_process_cwd(tmp_path, monkeypatch):
    """Regression: the two `git worktree` subprocess calls used to do
    `cwd=str(cwd)` unconditionally, so a caller passing cwd=None (the
    default all the way up through push_branch()/ensure_base_snapshot(),
    since the CLI never passes an explicit cwd) turned into the literal
    string "None" as the subprocess cwd -- `FileNotFoundError` on any real
    invocation, only ever masked in tests that happened to pass an
    explicit tmp_path. `is_ancestor()` already guarded this correctly;
    `_extract_graph_at_commit()` didn't (found via review)."""
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    old_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    monkeypatch.chdir(tmp_path)
    G = ab._extract_graph_at_commit(None, old_sha)
    labels = {data.get("label") for _, data in G.nodes(data=True)}
    assert any("foo" in (label or "") for label in labels)
