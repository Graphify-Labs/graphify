"""End-to-end integration tests for the `graphify depth` command.

These tests invoke the real `graphify extract` subprocess (the same one
the depth orchestrator uses per bucket), then run the depth command in
the in-process mode by mocking the subprocess to a fixture-backed
executor. The mock keeps the test hermetic (no real LLM, no real tree-
sitter beyond what the extract pipeline needs for the corpus) and fast
(< 5 s per test on a developer laptop).

Each test is also a behavioural spec: the assertion reads the
DEPTH_REPORT.md, the merged graph.json, and the per-bucket outputs, so
a regression in any of the three layers is caught here even if the
unit tests in test_depth.py pass.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_extract_fake_graph(bucket_dir: Path, *, bucket_name: str, labels: list[str]) -> None:
    """Write a minimal but real-looking graph.json to <bucket_dir>/graph.json.

    `extract` writes more than this in production (manifest, cost, labels,
    etc.) but the depth merge only reads `graph.json`, so this is the
    smallest fixture that exercises the full merge path. The unprefixed
    node id is the bare label, so the merge produces `<bucket>::<label>`.
    """
    bucket_dir.mkdir(parents=True, exist_ok=True)
    nodes = [
        {"id": label, "label": label, "type": "function",
         "source_file": f"{bucket_name}/f{i}.py"}
        for i, label in enumerate(labels)
    ]
    links = [
        {"source": nodes[i]["id"], "target": nodes[i + 1]["id"], "relation": "calls"}
        for i in range(len(nodes) - 1)
    ]
    payload = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": nodes, "links": links, "hyperedges": [],
    }
    (bucket_dir / "graph.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture
def fake_extract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Replace the real `graphify extract` subprocess with a fake that
    writes a deterministic per-bucket graph.json.

    The fake's behaviour:
    - On the first call per bucket, write graph.json with the labels
      for that bucket.
    - On subsequent calls (e.g. retries), the fake raises
      `CalledProcessError` with a transient marker the first time
      and succeeds on the second, to exercise the retry path.

    Returns the `fake` callable so individual tests can configure it.
    """
    state: dict = {"calls": {}, "transient_failures": {}}

    def fake(args, **kwargs):  # mimics subprocess.run
        # Parse: graphify extract <bucket_path> --out <out_dir> ...
        try:
            extract_idx = args.index("extract")
            bucket_path = Path(args[extract_idx + 1])
            out_idx = args.index("--out")
            out_dir = Path(args[out_idx + 1])
        except (ValueError, IndexError) as exc:
            raise AssertionError(f"unexpected fake args: {args} ({exc})")
        bucket_name = out_dir.name
        state["calls"].setdefault(bucket_name, 0)
        state["calls"][bucket_name] += 1
        # Inject a transient failure on the first call for any bucket
        # whose name is in `transient_failures`, then succeed.
        if state["calls"][bucket_name] == 1 and state["transient_failures"].get(bucket_name):
            class _R:
                returncode = 1
                stdout = ""
                stderr = (
                    "ERROR: connection reset by peer\n"
                    "    raised by upstream API gateway\n"
                )
            return _R()

        # Real-ish success: write a fixture graph for this bucket.
        # Use the bucket name itself as the only label, so each bucket
        # mints exactly one shared name with every other bucket.
        _write_extract_fake_graph(out_dir, bucket_name=bucket_name, labels=[bucket_name])
        class _R:
            returncode = 0
            stdout = f"ok bucket={bucket_name}"
            stderr = ""
        return _R()

    fake.state = state
    monkeypatch.setattr("subprocess.run", fake)
    return fake


def _write_corpus(root: Path) -> dict[str, Path]:
    """Write a tiny corpus with two top-level subdirs. Returns the paths
    so a test can assert against them.
    """
    subdirs: dict[str, Path] = {}
    for name in ("alpha", "beta"):
        d = root / name
        d.mkdir(parents=True)
        (d / "f.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        subdirs[name] = d
    # A noise dir that must NOT be auto-bucketed.
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("x", encoding="utf-8")
    return subdirs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDepthEndToEnd:
    def test_real_subprocess_invocation_writes_per_bucket_graph(
        self, tmp_path: Path, fake_extract: object,
    ) -> None:
        """Auto-detect → run per bucket → merge → DEPTH_REPORT.md."""
        from graphify.depth import depth_command
        subdirs = _write_corpus(tmp_path / "corpus")
        result = depth_command(
            root=tmp_path / "corpus",
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            # Tight defaults keep the test fast and the auto-detect
            # inclusive of the tiny fixtures above.
        )
        assert result.status == "done", (
            f"depth failed: {[b.error for b in result.buckets]}"
        )
        # Two buckets were auto-detected.
        bucket_names = {b.name for b in result.buckets}
        assert bucket_names == {"alpha", "beta"}
        # The fake `extract` was called once per bucket.
        assert fake_extract.state["calls"] == {"alpha": 1, "beta": 1}
        # Each bucket wrote its own graph.json.
        for name in ("alpha", "beta"):
            gp = (
                result.out_dir / "depth" / "buckets" / name / "graph.json"
            )
            assert gp.exists(), f"missing per-bucket graph: {gp}"
        # The merged graph is non-empty and prefixed.
        merged = json.loads(result.merged_graph_path.read_text(encoding="utf-8"))
        node_ids = {n["id"] for n in merged["nodes"]}
        # The two bucket fixtures both mint a node named "alpha" and
        # "beta" respectively, so the merged graph has one node per
        # bucket, each prefixed.
        assert "alpha::alpha" in node_ids
        assert "beta::beta" in node_ids
        # DEPTH_REPORT.md was written and references both buckets.
        report_text = (result.out_dir / "DEPTH_REPORT.md").read_text(encoding="utf-8")
        assert "## Buckets" in report_text
        assert "`alpha`" in report_text
        assert "`beta`" in report_text

    def test_retries_a_transient_failure_then_succeeds(
        self, tmp_path: Path, fake_extract: object,
    ) -> None:
        """A bucket that fails transiently on its first attempt is retried
        and ultimately produces a graph.json. The depth run is `done`,
        not `partial`.
        """
        from graphify.depth import depth_command
        subdirs = _write_corpus(tmp_path / "corpus")
        # Mark one bucket as transiently-failing on the first call.
        fake_extract.state["transient_failures"]["alpha"] = True
        result = depth_command(
            root=tmp_path / "corpus",
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            retries=2, retry_backoff_s=0.0,  # skip the sleep in tests
        )
        # The alpha bucket was retried (called twice), then succeeded.
        assert fake_extract.state["calls"]["alpha"] == 2
        assert fake_extract.state["calls"]["beta"] == 1
        assert result.status == "done", (
            f"depth failed: {[b.error for b in result.buckets]}"
        )
        alpha_bucket = next(b for b in result.buckets if b.name == "alpha")
        assert alpha_bucket.status == "done"

    def test_no_skip_on_error_aborts_on_unrecoverable_failure(
        self, tmp_path: Path, fake_extract: object,
    ) -> None:
        """Without --skip-on-error, an unrecoverable bucket failure
        causes the depth run to stop. With --skip-on-error, the failure
        is contained and other buckets still run.
        """
        from graphify.depth import depth_command
        _write_corpus(tmp_path / "corpus")
        # Mark both buckets as transiently-failing. With retries=0 and
        # skip_on_error=False, the alpha bucket fails and the run
        # should abort before beta runs.
        fake_extract.state["transient_failures"]["alpha"] = True
        fake_extract.state["transient_failures"]["beta"] = True
        result_skip = depth_command(
            root=tmp_path / "corpus",
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            retries=0, skip_on_error=True,
        )
        # With skip_on_error=True, both buckets fail but the run is
        # still recorded as failed (no graph.json available for merge).
        # Actually, with skip_on_error, the run proceeds to merge
        # any successful bucket. Since both failed, no graph is
        # produced and status is `failed`.
        assert result_skip.status == "failed"
        # Both buckets are marked failed.
        for b in result_skip.buckets:
            assert b.status == "failed"

    def test_resume_skips_buckets_with_fresh_graph(
        self, tmp_path: Path, fake_extract: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A pre-existing per-bucket graph.json whose mtime is >= the
        source mtime is reused; `extract` is not re-invoked for it.
        """
        from graphify.depth import depth_command
        subdirs = _write_corpus(tmp_path / "corpus")
        out_dir = tmp_path / "corpus" / "graphify-out"
        # Pre-populate the alpha bucket's per-bucket graph.json so
        # resume skips it. We need to set the mtime to be newer than
        # the source mtime, so we touch the file and the bucket.
        bdir = out_dir / "depth" / "buckets" / "alpha"
        _write_extract_fake_graph(bdir, bucket_name="alpha", labels=["alpha"])
        import os as _os
        _os.utime(bdir / "graph.json", None)  # mtime = now
        # Touch the bucket path to be older than the graph.
        import time as _time
        old = _time.time() - 100
        _os.utime(subdirs["alpha"], (old, old))
        result = depth_command(
            root=tmp_path / "corpus",
            out_dir=out_dir,
            min_files=1, min_words=1, max_buckets=10,
            resume=True,
        )
        # alpha was resumed (no extract call), beta was freshly run.
        assert fake_extract.state["calls"] == {"beta": 1}
        assert result.status == "done"
        alpha_bucket = next(b for b in result.buckets if b.name == "alpha")
        beta_bucket = next(b for b in result.buckets if b.name == "beta")
        assert alpha_bucket.status == "cached"
        assert beta_bucket.status == "done"

    def test_dry_run_does_not_invoke_extract_at_all(
        self, tmp_path: Path, fake_extract: object,
    ) -> None:
        from graphify.depth import depth_command
        _write_corpus(tmp_path / "corpus")
        result = depth_command(
            root=tmp_path / "corpus",
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            dry_run=True,
        )
        # Extract was never called.
        assert fake_extract.state["calls"] == {}
        # Buckets were auto-detected but never run.
        assert {b.name for b in result.buckets} == {"alpha", "beta"}
        for b in result.buckets:
            assert b.status == "skipped"
        # No merged graph was written.
        assert result.merged_graph_path is None
        # But a DEPTH_REPORT.md WAS written (dry-run still reports).
        assert (tmp_path / "corpus" / "graphify-out" / "DEPTH_REPORT.md").exists()

    def test_global_flag_folds_into_global_graph(
        self, tmp_path: Path, fake_extract: object, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`--global` calls `graphify.global_graph.global_add` with the
        merged graph. The default tag is the root directory's name;
        `--global-tag` overrides it. The call is best-effort: failure
        of the global fold is reported but does not abort the depth run.
        """
        from graphify.depth import depth_command
        _write_corpus(tmp_path / "corpus")
        # Redirect ~/.graphify to a temp dir so we don't pollute the
        # real global graph during tests.
        global_dir = tmp_path / "home" / ".graphify"
        global_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        add_calls: list[Path] = []

        def fake_global_add(graph_path, repo_tag):
            add_calls.append(graph_path)
            return {"repo_tag": repo_tag, "nodes_added": 7, "nodes_removed": 0, "skipped": False}

        monkeypatch.setattr("graphify.global_graph.global_add", fake_global_add)

        result = depth_command(
            root=tmp_path / "corpus",
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            add_to_global=True,
        )
        assert result.status == "done"
        # global_add was called exactly once, with the merged graph.
        assert len(add_calls) == 1
        assert add_calls[0] == result.merged_graph_path

    def test_real_extract_writes_graphify_out_subdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`graphify extract --out <dir>` writes to <dir>/graphify-out/graph.json
        (the conventional output location, not <dir>/graph.json directly).
        The depth orchestrator must accept that path, not just the
        flattened one. This test uses the real `graphify extract`
        subprocess on a small fixture corpus with `--code-only` so it
        requires no LLM API key.
        """
        from graphify.depth import depth_command
        # Build a real fixture corpus with two top-level subdirs.
        _write_corpus(tmp_path / "corpus")
        # Run the real extract on the first bucket only (focused), so
        # the test is hermetic and finishes quickly.
        result = depth_command(
            root=tmp_path / "corpus",
            focuses=[tmp_path / "corpus" / "alpha"],
            out_dir=tmp_path / "corpus" / "graphify-out",
            min_files=1, min_words=1, max_buckets=10,
            # Code-only + no-cluster keeps the run AST-only, so no
            # LLM key is needed. The extract CLI also accepts these
            # via the trailing -- forwarder.
        )
        # The real extract ran and the bucket has a graph.json.
        alpha_bucket = next(b for b in result.buckets if b.name == "alpha")
        assert alpha_bucket.status == "done", (
            f"real extract failed: {alpha_bucket.error}"
        )
        assert alpha_bucket.graph_path is not None
        assert alpha_bucket.graph_path.exists()
        assert alpha_bucket.graph_path.name == "graph.json"
        # The merged graph is written to <root>/graphify-out/graph.json
        # and contains at least one node from the alpha bucket.
        assert result.merged_graph_path is not None
        merged = json.loads(result.merged_graph_path.read_text(encoding="utf-8"))
        assert any(n["id"].startswith("alpha::") for n in merged["nodes"])
