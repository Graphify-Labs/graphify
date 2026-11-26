"""Restamp variant: watch._rebuild_code advances ``built_at_commit`` on a
topology-preserving commit, so a consumer's ``built_at_commit == HEAD`` check
clears without a memo. Skipped when the restamp patch is not applied.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from graphify import watch
from tests._freshness_repo import build_graph, clean_env, commit, graph_json, init_repo

pytestmark = pytest.mark.skipif(
    not hasattr(watch, "_restamp_built_commit"),
    reason="restamp variant not applied",
)


def test_noop_commit_restamps_built_at_commit(tmp_path):
    repo = tmp_path / "proj"
    init_repo(repo)
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    commit(repo, "initial")
    build_graph(repo)

    (repo / "data.nope").write_text("unclassified\n", encoding="utf-8")  # not indexed
    head = commit(repo, "chore: noop (topology-preserving)")

    before = json.loads(graph_json(repo).read_text(encoding="utf-8"))["built_at_commit"]
    assert before != head  # the stamp is behind until an update runs

    subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(repo)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=clean_env(),
    )
    after = json.loads(graph_json(repo).read_text(encoding="utf-8"))["built_at_commit"]
    assert after == head  # restamped without a topology rebuild


def test_restamp_does_not_touch_payload(tmp_path):
    repo = tmp_path / "proj"
    init_repo(repo)
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    commit(repo, "initial")
    build_graph(repo)

    before = json.loads(graph_json(repo).read_text(encoding="utf-8"))
    (repo / "data.nope").write_text("unclassified\n", encoding="utf-8")
    commit(repo, "chore: noop")

    subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(repo)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=clean_env(),
    )
    after = json.loads(graph_json(repo).read_text(encoding="utf-8"))
    # Same nodes/edges; only the stamp advanced.
    assert before["nodes"] == after["nodes"]
    assert before.get("links", before.get("edges")) == after.get("links", after.get("edges"))
    assert before["built_at_commit"] != after["built_at_commit"]
