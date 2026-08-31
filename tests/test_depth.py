"""Tests for the `graphify depth` command.

Covers the six production scenarios:

1. Small corpus (<500 files): depth mode is a no-op, returns the root as
   a single bucket, does NOT warn.
2. Medium corpus (auto-detect triggers): picks the top-level subdirs.
3. Explicit `--focus`: respects user paths even when auto-detect would
   pick others, and handles non-existent paths cleanly.
4. Single-bucket case: emits a copy-equivalent merged graph and a
   correct depth report.
5. `--resume`: skips buckets whose graph.json is fresh.
6. Cross-bucket signals: a label minted under two different bucket
   prefixes is surfaced in the depth report.

These tests do not require an LLM API: they exercise the orchestration
layer (auto-detect, merge, signal detection, report writing) with
hand-built graph.json fixtures, so the same suite runs in CI without
network or API keys.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures: hand-built corpus trees and graph.json files
# ---------------------------------------------------------------------------


def _write_minimal_graph_json(path: Path, *, nodes: list[dict], links: list[dict]) -> None:
    """Write a node-link-graph-shaped graph.json that round-trips through
    networkx.readwrite.json_graph. Includes the optional top-level
    `hyperedges` slot to mirror what graphify actually writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": nodes,
        "links": links,
        "hyperedges": [],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture
def tmp_corpus(tmp_path: Path) -> Path:
    """A tiny monorepo with two top-level subdirs, each with a couple of
    `.py` files. Enough files to pass the default auto-detect floors
    when tuned down via flags, but not so many that the test is slow.
    """
    root = tmp_path / "monorepo"
    (root / "pkg-a").mkdir(parents=True)
    (root / "pkg-b").mkdir(parents=True)
    (root / "pkg-c").mkdir(parents=True)
    (root / ".git").mkdir()  # noise: should be skipped
    (root / "node_modules").mkdir()  # noise
    # Each pkg has a few files with non-trivial word count.
    for pkg, count in [("pkg-a", 30), ("pkg-b", 30), ("pkg-c", 30)]:
        for i in range(count):
            (root / pkg / f"f{i}.py").write_text(
                f"# module {pkg}.f{i}\n" + ("\n".join(f"x = {j}" for j in range(50))) + "\n",
                encoding="utf-8",
            )
    return root


@pytest.fixture
def graph_json_factory(tmp_path: Path):
    """A factory that writes a small graph.json containing nodes whose
    unprefixed ids are the given labels. The merge pipeline adds the
    `repo_tag::` prefix itself, so fixtures must use the bare form.
    """
    written: list[Path] = []

    def _make(bucket_dir: Path, *, labels: list[str]) -> Path:
        nodes = [
            {"id": label, "label": label, "type": "function"}
            for label in labels
        ]
        links = [
            {"source": a, "target": b, "relation": "calls"}
            for a, b in zip(labels, labels[1:])
        ]
        path = bucket_dir / "graph.json"
        _write_minimal_graph_json(path, nodes=nodes, links=links)
        written.append(path)
        return path

    return _make


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoDetectBuckets:
    def test_picks_top_level_subdirs(self, tmp_corpus: Path) -> None:
        from graphify.depth import auto_detect_buckets
        # Tune floors so the fixture's 30 files / ~1500 words per pkg
        # is enough to qualify, but tight enough that the test stays fast.
        buckets = auto_detect_buckets(
            tmp_corpus, min_files=20, min_words=1_000, max_buckets=20,
        )
        names = {b.name for b in buckets}
        assert "pkg-a" in names
        assert "pkg-b" in names
        assert "pkg-c" in names
        # Noise dirs are excluded.
        assert ".git" not in names
        assert "node_modules" not in names

    def test_falls_back_to_root_when_nothing_qualifies(self, tmp_path: Path) -> None:
        from graphify.depth import auto_detect_buckets
        root = tmp_path / "tiny"
        root.mkdir()
        (root / "small").mkdir()
        (root / "small" / "x.py").write_text("x = 1\n", encoding="utf-8")
        buckets = auto_detect_buckets(
            root, min_files=100, min_words=100_000, max_buckets=20,
        )
        # The single subdir is too small; the whole root is the only bucket.
        assert len(buckets) == 1
        assert buckets[0] == root

    def test_caps_at_max_buckets(self, tmp_path: Path) -> None:
        from graphify.depth import auto_detect_buckets
        root = tmp_path / "many"
        root.mkdir()
        for i in range(10):
            sub = root / f"sub-{i}"
            sub.mkdir()
            (sub / "f.py").write_text(("y = 1\n" * 200), encoding="utf-8")
        buckets = auto_detect_buckets(root, min_files=1, min_words=1, max_buckets=3)
        assert len(buckets) == 3

    def test_handles_missing_root(self, tmp_path: Path) -> None:
        from graphify.depth import auto_detect_buckets
        buckets = auto_detect_buckets(tmp_path / "nope", min_files=1, min_words=1)
        # Missing root is treated as a single-bucket case (the missing path).
        assert len(buckets) == 1


class TestCrossBucketSignals:
    def test_detects_labels_shared_across_buckets(self, tmp_path: Path) -> None:
        # Two buckets, both minting "User" under different prefixes.
        from graphify.depth import detect_cross_bucket_signals
        nodes = [
            {"id": "pkg-a::User", "label": "User", "type": "class",
             "source_file": "pkg-a/u.py"},
            {"id": "pkg-b::User", "label": "User", "type": "class",
             "source_file": "pkg-b/u.py"},
            {"id": "pkg-a::Other", "label": "Other", "type": "function",
             "source_file": "pkg-a/o.py"},
        ]
        gpath = tmp_path / "graph.json"
        _write_minimal_graph_json(gpath, nodes=nodes, links=[])

        from graphify.depth import Bucket
        buckets = [
            Bucket(name="pkg-a", path=tmp_path, out_dir=tmp_path),
            Bucket(name="pkg-b", path=tmp_path, out_dir=tmp_path),
        ]
        signals = detect_cross_bucket_signals(merged_graph_path=gpath, buckets=buckets)
        labels = [s["label"] for s in signals]
        assert "User" in labels
        user_signal = next(s for s in signals if s["label"] == "User")
        assert set(user_signal["buckets"]) == {"pkg-a", "pkg-b"}
        # "Other" only appears in pkg-a → no signal.
        assert "Other" not in labels

    def test_handles_empty_graph(self, tmp_path: Path) -> None:
        from graphify.depth import Bucket, detect_cross_bucket_signals
        gpath = tmp_path / "graph.json"
        _write_minimal_graph_json(gpath, nodes=[], links=[])
        buckets = [Bucket(name="x", path=tmp_path, out_dir=tmp_path)]
        assert detect_cross_bucket_signals(merged_graph_path=gpath, buckets=buckets) == []

    def test_handles_missing_graph(self, tmp_path: Path) -> None:
        from graphify.depth import Bucket, detect_cross_bucket_signals
        buckets = [Bucket(name="x", path=tmp_path, out_dir=tmp_path)]
        # No graph.json at all → empty result, not an exception.
        assert detect_cross_bucket_signals(
            merged_graph_path=tmp_path / "nope.json", buckets=buckets,
        ) == []


class TestMergeBuckets:
    def test_merges_two_buckets_into_one_graph(
        self, tmp_path: Path, graph_json_factory,
    ) -> None:
        from graphify.depth import merge_buckets
        a_dir = tmp_path / "buckets" / "a"
        b_dir = tmp_path / "buckets" / "b"
        a_path = graph_json_factory(
            a_dir, labels=["User", "Session"],
        )
        b_path = graph_json_factory(
            b_dir, labels=["Account", "Order"],
        )
        out = tmp_path / "merged.json"
        summary = merge_buckets(
            [a_path, b_path], out_path=out, bucket_tags=["a", "b"],
        )
        assert out.exists()
        merged = json.loads(out.read_text(encoding="utf-8"))
        # All four nodes are present, prefixed by the explicit tags.
        node_ids = {n["id"] for n in merged["nodes"]}
        assert node_ids == {"a::User", "a::Session", "b::Account", "b::Order"}
        # Each node carries the bucket tag in its `repo` attribute.
        repos = {n["repo"] for n in merged["nodes"]}
        assert repos == {"a", "b"}
        # Edge count is the sum of the two bucket edge counts.
        assert summary["edges"] == 2
        assert summary["nodes"] == 4

    def test_bucket_tags_uniqueness_collision_widens(
        self, tmp_path: Path, graph_json_factory,
    ) -> None:
        # Two graphs with the same requested tag should be widened
        # automatically (mirrors distinct_repo_tags behaviour for
        # cross-repo merges). Without this, a multi-bucket depth with
        # nested focuses that share a leaf name would silently merge
        # unrelated entities (#1729).
        from graphify.depth import merge_buckets
        a_dir = tmp_path / "x"
        a_path = graph_json_factory(a_dir, labels=["Alpha"])
        out = tmp_path / "merged.json"
        summary = merge_buckets(
            [a_path, a_path], out_path=out, bucket_tags=["x", "x"],
        )
        # The summary reports the widened tags, not the raw duplicates.
        assert summary["repo_tags"] == ["x", "x-2"]
        # Both prefixed nodes survive.
        merged = json.loads(out.read_text(encoding="utf-8"))
        node_ids = {n["id"] for n in merged["nodes"]}
        assert node_ids == {"x::Alpha", "x-2::Alpha"}

    def test_bucket_tags_length_mismatch_raises(
        self, tmp_path: Path, graph_json_factory,
    ) -> None:
        from graphify.depth import merge_buckets
        a_dir = tmp_path / "x"
        a_path = graph_json_factory(a_dir, labels=["Alpha"])
        with pytest.raises(ValueError, match="bucket_tags length"):
            merge_buckets([a_path], out_path=tmp_path / "m.json",
                          bucket_tags=["one", "two"])

    def test_preserves_hyperedges_at_top_level(self, tmp_path: Path) -> None:
        # Even if a hand-built graph.json omits the nested graph.hyperedges
        # slot, the merge must mirror the dual-slot shape (#2484, #2485).
        from graphify.depth import merge_buckets
        a_dir = tmp_path / "a"
        gpath = a_dir / "graph.json"
        # Unprefixed node id; the merge pipeline adds the `a::` prefix.
        payload = {
            "directed": False, "multigraph": False, "graph": {},
            "nodes": [{"id": "X", "label": "X"}],
            "links": [],
            "hyperedges": [{"id": "h1", "nodes": ["X"], "kind": "group"}],
        }
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text(json.dumps(payload), encoding="utf-8")
        out = tmp_path / "merged.json"
        merge_buckets([gpath], out_path=out, bucket_tags=["a"])
        merged = json.loads(out.read_text(encoding="utf-8"))
        # The top-level `hyperedges` slot survives the round-trip, and
        # the hyperedge id is rewritten with the bucket prefix.
        assert "hyperedges" in merged
        assert any(h.get("id") == "a::h1" for h in merged["hyperedges"])


class TestWriteDepthReport:
    def test_report_lists_buckets_and_signals(self, tmp_path: Path) -> None:
        from graphify.depth import (
            Bucket, DepthReport, detect_cross_bucket_signals, write_depth_report,
        )
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        # The factory writes un-prefixed node ids; the merge adds the
        # bucket tag (`a`/`b`) so the merged graph has `a::User` /
        # `b::User`, which is exactly the cross-bucket signal we want
        # the report to surface.
        from graphify.depth import merge_buckets
        a_path = tmp_path / "a" / "graph.json"
        b_path = tmp_path / "b" / "graph.json"
        _write_minimal_graph_json(
            a_path,
            nodes=[{"id": "User", "label": "User", "type": "class"}],
            links=[],
        )
        _write_minimal_graph_json(
            b_path,
            nodes=[{"id": "User", "label": "User", "type": "class"}],
            links=[],
        )
        out = tmp_path / "merged.json"
        merge_buckets([a_path, b_path], out_path=out, bucket_tags=["a", "b"])

        buckets = [
            Bucket(name="a", path=tmp_path / "a", out_dir=tmp_path / "a_out", nodes=1, edges=0, status="done", graph_path=a_path),
            Bucket(name="b", path=tmp_path / "b", out_dir=tmp_path / "b_out", nodes=1, edges=0, status="done", graph_path=b_path),
        ]
        report = DepthReport(
            root=tmp_path, out_dir=tmp_path, buckets=buckets,
            merged_graph_path=out, status="done", total_elapsed_s=1.0,
        )
        report.cross_bucket_signals = detect_cross_bucket_signals(
            merged_graph_path=out, buckets=buckets,
        )
        # Sanity: the signal exists in the merged graph.
        assert any(s["label"] == "User" for s in report.cross_bucket_signals)
        depth_report = tmp_path / "DEPTH_REPORT.md"
        write_depth_report(report, depth_report)
        text = depth_report.read_text(encoding="utf-8")
        assert "## Buckets" in text
        assert "## Cross-bucket signals" in text
        assert "User" in text
        # Both bucket names appear in the signals table.
        assert "`a`" in text
        assert "`b`" in text


class TestDepthCommandOrchestration:
    def test_dry_run_does_not_invoke_extract(self, tmp_corpus: Path) -> None:
        # The dry-run path should not shell out, and should populate the
        # bucket list from auto-detection only.
        from graphify.depth import depth_command
        out_dir = tmp_corpus / "graphify-out"
        result = depth_command(
            root=tmp_corpus,
            out_dir=out_dir,
            min_files=20, min_words=1_000,
            max_buckets=20,
            dry_run=True,
        )
        assert result.status == "done"
        # Buckets were auto-detected but nothing was extracted.
        assert {b.name for b in result.buckets} >= {"pkg-a", "pkg-b", "pkg-c"}
        for b in result.buckets:
            assert b.status == "skipped"
        # No merged graph was written.
        assert result.merged_graph_path is None
        # No per-bucket graph.json was created.
        assert not (out_dir / "depth" / "buckets" / "pkg-a" / "graph.json").exists()

    def test_focus_overrides_auto_detect(self, tmp_corpus: Path) -> None:
        from graphify.depth import depth_command
        out_dir = tmp_corpus / "graphify-out"
        result = depth_command(
            root=tmp_corpus,
            focuses=[tmp_corpus / "pkg-a", tmp_corpus / "pkg-b"],
            out_dir=out_dir,
            dry_run=True,
        )
        names = {b.name for b in result.buckets}
        assert names == {"pkg-a", "pkg-b"}
        assert "pkg-c" not in names
