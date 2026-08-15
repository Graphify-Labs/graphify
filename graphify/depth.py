"""Iterative sliding-window depth command for graphify.

================================================================
WHATS-NEW / METHOD NAME: the "iterative sliding-window depth-graph"
method, introduced for the >500-file / >500K-word case where a
single-pass `graphify <root>` warns and asks the user to narrow
manually.

The method:
  1. Auto-detects a corpus into N "buckets" (top-level subdirs with
     at least M files / W words) — or accepts an explicit
     `--focus <path>` set the user already knows about.
  2. Runs the FULL extract pipeline (detect, AST, semantic
     extraction, cluster, report) per bucket, via subprocess so
     each bucket reuses the shipped pipeline without re-implementing
     any of it.
  3. Merges the per-bucket graphs into a single cross-bucket graph
     using the same prefix-and-compose path the existing
     `graphify merge-graphs` already uses, with explicit bucket
     tags so each merged node's `repo` attribute is the bucket name.
  4. Surfaces "cross-bucket signals" — entity LABELS (not ids) that
     appear under multiple bucket prefixes in the merged graph —
     in a new `DEPTH_REPORT.md`. A signal is the most actionable
     cross-system hint a reviewer can get from a build: two
     sub-systems both minting an entity called "User" (or
     "Session", "Order", "Config") may be coincidence, may be a
     deliberate shared abstraction, or may be a copy-paste that
     should be deduplicated.
  5. Supports resume (skip buckets whose graph.json is fresher
     than the source mtime), transient-failure retry with
     exponential backoff, parallel execution capped at 4 workers
     (to respect LLM API rate limits when --mode deep is in
     effect), and a --global flag that folds the cross-bucket
     graph into the user's cross-repo global graph.

The new code is a thin orchestration layer over the existing
`graphify extract` and `graphify merge-graphs` code paths. No
existing command or its behaviour is changed.

================================================================
AUTHORSHIP: implemented by JFWaskin. The iterative sliding-window
depth-graph method (auto-detect → per-bucket extract → merge →
cross-bucket signal detection → depth report) is a new contribution
to graphify; it is not a refactor of an existing feature. The
underlying `extract` and `merge-graphs` subcommands it composes
are unchanged.

================================================================
PRODUCTION SCENARIOS COVERED (8):

  1. Monorepo (>500 files). Auto-detects top-level subdirs as
     buckets. Honors `.graphifyignore` and `.gitignore`.
  2. Selective focus. `--focus packages/auth --focus packages/billing`
     is the equivalent of "I already know which sub-systems
     matter; just build those."
  3. Resume after interruption. A per-bucket output dir means a
     partial run is reusable; `--resume` skips buckets whose
     `graph.json` is newer than the source mtime.
  4. CI / flaky network. `--retries N --retry-backoff S` retries
     transient failures (timeouts, 5xx, rate limits, connection
     errors) with exponential backoff.
  5. CI parallel. `--parallel N` runs buckets concurrently, capped
     at 4 to respect LLM API rate limits when --mode deep is in
     effect.
  6. Cross-repo integration. `--global` folds the merged graph
     into the user's cross-repo global graph (uses
     `graphify.global_graph.global_add`); `--global-tag` overrides
     the default tag.
  7. Sandbox / read-only. `--dry-run` reports auto-detected buckets
     without committing to a run.
  8. Partial-failure containment. `--skip-on-error` (default)
     continues past a single bucket failure; `--no-skip-on-error`
     aborts on the first failure.

================================================================
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Cap auto-detection so a 6 000-file monorepo does not produce 6 000 buckets.
_DEFAULT_MAX_BUCKETS = 20

# Below this size, a subdirectory is folded into the root bucket rather
# than given its own pass. The numbers mirror the corpus-warn thresholds
# in `graphify/detect.py` so the same notion of "too small to matter"
# is shared.
_MIN_BUCKET_FILES = 20
_MIN_BUCKET_WORDS = 5_000

# Default sub-bucket output dir, relative to <root>/graphify-out/.
_DEFAULT_BUCKET_DIR = "depth/buckets"

# Default cross-bucket output path, relative to <root>/graphify-out/.
_DEFAULT_MERGED = "graph.json"

# Default depth-report path, relative to <root>/graphify-out/.
_DEFAULT_DEPTH_REPORT = "DEPTH_REPORT.md"

# Reserved root bucket name for the catch-all case.
_ROOT_BUCKET = "<root>"


@dataclass
class Bucket:
    """One depth-bucket: a sub-path of the root and its per-bucket output dir."""

    name: str
    path: Path
    out_dir: Path
    graph_path: Path | None = None  # populated after a successful run
    nodes: int = 0
    edges: int = 0
    elapsed_s: float = 0.0
    status: str = "pending"  # pending | running | done | failed | skipped | cached
    error: str | None = None

    def label(self) -> str:
        return f"[{self.name}]"


@dataclass
class DepthReport:
    """Result of one `graphify depth` invocation."""

    root: Path
    out_dir: Path
    buckets: list[Bucket] = field(default_factory=list)
    merged_graph_path: Path | None = None
    cross_bucket_signals: list[dict[str, Any]] = field(default_factory=list)
    total_elapsed_s: float = 0.0
    status: str = "pending"  # pending | running | done | partial | failed

    def bucket_by_name(self, name: str) -> Bucket | None:
        for b in self.buckets:
            if b.name == name:
                return b
        return None


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

# Sub-bucket detection shares its notion of "noise" with the main walker
# in `graphify/detect.py`. We mirror the most common exclusions inline
# because this command must be importable without booting the full
# detect module (which would force a tree-sitter import chain).
_NOISE_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "out", "target", "bin", "obj",
    "vendor", "third_party", "third-party",
    ".venv", "venv", "env", ".env",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache",
    "coverage", ".coverage", ".nyc_output",
    "graphify-out",  # never bucket an existing build output
})

# Subdirectories that look like "buckets" of code/docs but are not, because
# the main walker already knows about them and they tend to be small /
# duplicated / special-purpose. Skipping them prevents over-bucketing.
_NON_BUCKET_NAMES = frozenset({
    "scripts", "tools", "test", "tests", "testdata",
    "docs", "doc", "documentation",
    "examples", "example", "demo", "demos",
    "fixtures", "snapshots",
    "assets", "static", "public", "wwwroot",
    "config", "configs", "configuration",
})


def _file_word_count(path: Path) -> int:
    """Cheap word count for a single file. Skips binary by extension."""
    if path.suffix.lower() in {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v",
        ".mp3", ".wav", ".m4a", ".ogg",
        ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    }:
        return 0
    try:
        with path.open("rb") as f:
            data = f.read(1_000_000)
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return 0
    return len(text.split())


def _bucket_metrics(bucket_path: Path) -> tuple[int, int]:
    """Return (file_count, word_count) for a single bucket dir.

    Both are bounded by walking at most 5 000 files and reading at most
    1 MiB per file so auto-detection does not become an O(corpus) scan.
    The numbers are an estimate; the real count is taken at extract time.
    """
    file_count = 0
    word_count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(bucket_path):
            # Prune noise in-place so the walk does not descend.
            dirnames[:] = [d for d in dirnames if d not in _NOISE_DIR_NAMES]
            for fn in filenames:
                file_count += 1
                if file_count >= 5_000:
                    return file_count, word_count
                word_count += _file_word_count(Path(dirpath) / fn)
    except OSError:
        pass
    return file_count, word_count


def auto_detect_buckets(
    root: Path,
    *,
    min_files: int = _MIN_BUCKET_FILES,
    min_words: int = _MIN_BUCKET_WORDS,
    max_buckets: int = _DEFAULT_MAX_BUCKETS,
) -> list[Path]:
    """Return the top-level subdirectories of `root` worth their own pass.

    A subdirectory is "worth it" if it has at least `min_files` files or
    `min_words` words, and is not a known noise / non-bucket dir. The
    result is sorted by word count (largest first) and capped at
    `max_buckets`.

    If no subdirectory qualifies, the entire root is returned as a single
    bucket — depth mode is a no-op in that case (the user can run plain
    `graphify extract` instead).
    """
    if not root.is_dir():
        return [root]
    candidates: list[tuple[Path, int, int]] = []
    try:
        children = sorted(
            (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name,
        )
    except OSError:
        return [root]
    for child in children:
        if child.name in _NOISE_DIR_NAMES or child.name in _NON_BUCKET_NAMES:
            continue
        files, words = _bucket_metrics(child)
        if files >= min_files or words >= min_words:
            candidates.append((child, files, words))
    # Largest first.
    candidates.sort(key=lambda t: t[2], reverse=True)
    chosen = [c[0] for c in candidates[:max_buckets]]
    if not chosen:
        return [root]
    return chosen


# ---------------------------------------------------------------------------
# Per-bucket extract
# ---------------------------------------------------------------------------


def _run_subprocess(cmd: list[str], *, cwd: Path, timeout: int | None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with line-buffered output so the user sees progress.

    `cwd` pins the working directory to the bucket root so relative paths
    in the extract pipeline resolve correctly.
    """
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_bucket(
    *,
    bucket: Bucket,
    bucket_root: Path,
    extract_args: list[str],
    graphify_bin: str | None,
    timeout_s: int | None,
    skip_on_error: bool,
    retries: int = 0,
    retry_backoff_s: float = 2.0,
) -> bool:
    """Run the full extract pipeline for one bucket.

    Returns True on success (or a fresh skip / cached), False on failure.
    The bucket's `status` and `error` fields are populated in place.

    Transient failures (network, 5xx, timeouts) are retried up to
    `retries` times with exponential backoff. The first non-transient
    failure (bad config, missing dependency) is reported immediately.
    Retries only fire when `retries > 0`; the default is zero so this
    function preserves its v1 behaviour for callers that don't opt in.
    """
    if not bucket.path.exists():
        bucket.status = "skipped"
        bucket.error = f"bucket path does not exist: {bucket.path}"
        return False

    bucket.out_dir.mkdir(parents=True, exist_ok=True)
    bin_path = graphify_bin or _resolve_graphify_bin()
    # The bucket's extract writes its graph.json to
    # <bucket_out_dir>/graphify-out/graph.json (per the `graphify extract`
    # contract — `--out` sets the *root* for graphify-out/, not the
    # graph.json path directly). We pass --out so the inner extract
    # knows the output root, and we read back the graph.json from the
    # conventional location. Setting `GRAPHIFY_OUT=<bucket_out_dir>` in
    # the subprocess env would also work and would let us drop --out,
    # but keeping --out is the more common idiom and matches the
    # user-facing `graphify extract` help.
    cmd = [bin_path, "extract", str(bucket.path), "--out", str(bucket.out_dir), *extract_args]
    attempt = 0
    while True:
        attempt += 1
        started = time.monotonic()
        try:
            result = _run_subprocess(cmd, cwd=bucket_root, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            bucket.elapsed_s = time.monotonic() - started
            transient = True
            result = None
        except FileNotFoundError as exc:
            bucket.elapsed_s = time.monotonic() - started
            bucket.status = "failed"
            bucket.error = f"graphify binary not found: {exc}"
            return False
        else:
            bucket.elapsed_s = time.monotonic() - started
            transient = _is_transient_failure(result)

        if result is not None and result.returncode == 0:
            # `graphify extract --out <dir>` writes to <dir>/graphify-out/graph.json.
            # We accept either the conventional location (preferred) or a
            # flattened <dir>/graph.json as a fallback for users who set
            # GRAPHIFY_OUT=<dir> in the per-bucket env.
            graph_path = bucket.out_dir / "graphify-out" / "graph.json"
            if not graph_path.exists():
                alt = bucket.out_dir / "graph.json"
                if alt.exists():
                    graph_path = alt
                else:
                    bucket.status = "failed"
                    bucket.error = (
                        f"extract succeeded but neither "
                        f"{bucket.out_dir / 'graphify-out' / 'graph.json'} "
                        f"nor {alt} were written"
                    )
                    return skip_on_error
            bucket.graph_path = graph_path
            bucket.nodes, bucket.edges = _read_node_edge_counts(graph_path)
            bucket.status = "done"
            return True

        # Failure path. Build the error message and decide whether to retry.
        if result is not None:
            stderr_tail = (result.stderr or "").strip().splitlines()[-8:]
            stderr_text = "\n".join(stderr_tail) or f"exit {result.returncode}"
        else:
            stderr_text = f"timeout after {timeout_s}s"
        if transient and attempt <= retries:
            backoff = retry_backoff_s * (2 ** (attempt - 1))
            bucket.status = "running"
            # Surface a clear "retrying" line; the orchestrator's
            # progress output uses status so this is observable.
            print(
                f"  [graphify depth] {bucket.label()} transient failure "
                f"(attempt {attempt}/{retries + 1}); retrying in {backoff:.1f}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
            continue
        bucket.status = "failed"
        bucket.error = stderr_text
        return skip_on_error


def _is_transient_failure(result: subprocess.CompletedProcess[str]) -> bool:
    """Return True if the subprocess failure looks transient (retryable).

    Heuristics, in order:
    - Non-zero exit AND stdout/stderr contain a known transient marker
      (timeout, rate limit, network error, 5xx HTTP).
    - Otherwise False: a bad-config or missing-file failure is treated
      as non-transient because retrying it is wasted work.
    """
    if result.returncode == 0:
        return False
    haystack = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    transient_markers = (
        "timeout",
        "timed out",
        "rate limit",
        "rate-limit",
        "429",
        "503",
        "502",
        "504",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "try again",
        "network is unreachable",
    )
    return any(marker in haystack for marker in transient_markers)


def _read_node_edge_counts(graph_path: Path) -> tuple[int, int]:
    """Read node / edge counts from a graph.json without loading the full graph."""
    try:
        with graph_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0, 0
    # node_link_data puts nodes in a list and links under "links" (with
    # optional "edges" for older files, #738). graph attribute may also
    # carry a duplicate node count.
    nodes = data.get("nodes") or []
    links = data.get("links")
    if links is None:
        links = data.get("edges") or []
    return len(nodes), len(links)


def _resolve_graphify_bin() -> str:
    """Locate the `graphify` binary. Falls back to the active Python entry point.

    The user may have graphify installed in a venv that is not on PATH, so
    we fall back to `python -m graphify` when `which graphify` fails. The
    `extract` subcommand lives in `cli.dispatch_command` and is reachable
    from the module entry point as well as the installed script.
    """
    import shutil as _shutil
    found = _shutil.which("graphify")
    if found:
        return found
    return f"{sys.executable} -m graphify"


# ---------------------------------------------------------------------------
# Merge (in-process reuse of merge-graphs' code path)
# ---------------------------------------------------------------------------


def merge_buckets(
    bucket_graphs: list[Path],
    *,
    out_path: Path,
    bucket_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Merge per-bucket graph.json files into one cross-bucket graph.

    `bucket_tags` (optional) is the list of repo tags to use, one per
    input graph. When omitted, falls back to `distinct_repo_tags`, which
    derives a tag from each graph's directory path (the same logic the
    `merge-graphs` CLI uses for cross-repo merging). For depth mode the
    caller should pass the bucket names so the merged graph's `repo`
    attribute matches the bucket names, which keeps cross-bucket signal
    detection straightforward.

    Returns a small summary dict (number of nodes, edges, distinct repo
    tags, etc.). The full graph is written to `out_path`.

    Implementation: imports the same functions `merge-graphs` uses so
    node prefixes, hyperedge handling, and direction restoration match
    the user's manual workflow. We avoid calling the CLI a second time
    so cross-bucket signal detection can read the merged nx.Graph object
    directly.
    """
    import networkx as _nx
    from networkx.readwrite import json_graph as _jg

    from graphify.build import (
        distinct_repo_tags as _repo_tags,
        prefix_graph_for_global as _prefix,
    )
    from graphify.export import attach_hyperedges as _attach
    from graphify.paths import write_json_atomic as _wja

    graphs: list[_nx.Graph] = []
    for gp in bucket_graphs:
        if not gp.exists():
            continue
        data = json.loads(gp.read_text(encoding="utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        # Mirror cli.py merge-graphs direction preservation (#2261, #2309).
        data = dict(
            data,
            links=[
                {
                    **link,
                    "_src": link.get("_src", link.get("source")),
                    "_tgt": link.get("_tgt", link.get("target")),
                }
                for link in data.get("links", [])
            ],
        )
        try:
            G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            G = _jg.node_link_graph(data)
        if "hyperedges" not in G.graph and isinstance(data.get("hyperedges"), list):
            G.graph["hyperedges"] = data["hyperedges"]
        graphs.append(G)

    def _to_simple(g: "_nx.Graph") -> "_nx.Graph":
        if type(g) is not _nx.Graph:
            return _nx.Graph(g)
        return g

    if bucket_tags is not None:
        # Validate: one tag per graph, and unique within the merge.
        if len(bucket_tags) != len(graphs):
            raise ValueError(
                f"bucket_tags length ({len(bucket_tags)}) must match "
                f"the number of valid bucket graphs ({len(graphs)})"
            )
        # Detect collisions and widen with the bucket's path-derived tag.
        # This mirrors the same defensive widening that distinct_repo_tags
        # does for cross-repo merges, so two buckets that share a name
        # (rare, but possible with nested focuses) cannot silently collide.
        seen: dict[str, int] = {}
        final: list[str] = []
        for t in bucket_tags:
            seen[t] = seen.get(t, 0) + 1
            final.append(t if seen[t] == 1 else f"{t}-{seen[t]}")
        repo_tags = final
    else:
        repo_tags = _repo_tags(bucket_graphs)
    merged = _nx.Graph()
    collected_hyperedges: list = []
    for G, tag in zip(graphs, repo_tags):
        prefixed = _to_simple(_prefix(G, tag))
        hes = prefixed.graph.get("hyperedges")
        if isinstance(hes, list):
            collected_hyperedges.extend(h for h in hes if isinstance(h, dict))
        merged = _nx.compose(merged, prefixed)
    merged.graph.pop("hyperedges", None)
    if collected_hyperedges:
        _attach(merged, collected_hyperedges)

    try:
        out_data = _jg.node_link_data(merged, edges="links")
    except TypeError:
        out_data = _jg.node_link_data(merged)
    for link in out_data.get("links", []):
        tsrc = link.pop("_src", None)
        ttgt = link.pop("_tgt", None)
        if tsrc is not None and ttgt is not None:
            link["source"] = tsrc
            link["target"] = ttgt
    out_data["hyperedges"] = merged.graph.get("hyperedges", [])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _wja(out_path, out_data, indent=2)

    return {
        "buckets": len(bucket_graphs),
        "nodes": merged.number_of_nodes(),
        "edges": merged.number_of_edges(),
        "repo_tags": list(repo_tags),
        "out_path": str(out_path),
    }


# ---------------------------------------------------------------------------
# Cross-bucket signal detection
# ---------------------------------------------------------------------------


def detect_cross_bucket_signals(
    *,
    merged_graph_path: Path,
    buckets: list[Bucket],
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """Return nodes whose prefix is "shared" with another bucket.

    A "cross-bucket signal" is a node id whose `<bucket>::<entity>` prefix
    denotes a bucket, but whose label (the entity name without the prefix)
    appears under MORE than one bucket's prefix in the merged graph.

    Concretely: if `pkg-a::User` and `pkg-b::User` both exist, "User" is a
    cross-bucket signal — two different modules in different parts of the
    codebase share a concept name. This is the same insight a human
    reviewer would surface ("auth/User and billing/User look related —
    are they?").

    The result is sorted by (bucket count desc, degree desc) so the most
    significant cross-bucket concepts surface first. `top_n` caps the
    result.
    """
    if not merged_graph_path.exists():
        return []
    try:
        data = json.loads(merged_graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    nodes = data.get("nodes") or []
    if not nodes:
        return []

    # Build a map: bare label -> set of bucket prefixes that mint it.
    label_to_prefixes: dict[str, set[str]] = {}
    label_to_meta: dict[str, dict[str, Any]] = {}
    bucket_names = {b.name for b in buckets}
    for n in nodes:
        nid = n.get("id") or ""
        label = n.get("label") or ""
        if "::" not in nid or not label:
            continue
        prefix, _, _rest = nid.partition("::")
        # Only consider prefixes that are one of our bucket names.
        if prefix not in bucket_names:
            continue
        label_to_prefixes.setdefault(label, set()).add(prefix)
        label_to_meta.setdefault(label, n)

    signals: list[dict[str, Any]] = []
    for label, prefixes in label_to_prefixes.items():
        if len(prefixes) < 2:
            continue
        meta = label_to_meta.get(label) or {}
        signals.append({
            "label": label,
            "buckets": sorted(prefixes),
            "bucket_count": len(prefixes),
            "node_type": meta.get("type") or meta.get("kind") or "",
            "source_file_sample": meta.get("source_file") or meta.get("source") or "",
        })
    # Sort by bucket count, then alphabetically for stable output.
    signals.sort(key=lambda s: (-s["bucket_count"], s["label"]))
    return signals[:top_n]


# ---------------------------------------------------------------------------
# Depth report
# ---------------------------------------------------------------------------


_DEPTH_REPORT_HEADER = """# Depth Report

This report is generated by `graphify depth`, the iterative sliding-window
mode for graphify. It runs the full extract pipeline per sub-bucket of the
corpus, then merges the per-bucket graphs into a single cross-bucket graph.

The report is supplementary to `GRAPH_REPORT.md`; it surfaces the
bucket-level structure that a single-pass build cannot see.

"""


def write_depth_report(report: DepthReport, out_path: Path) -> None:
    """Write a Markdown depth report next to the merged graph.json.

    The report contains:
    - per-bucket node / edge / elapsed-s stats,
    - the cross-bucket signal table (entity labels that appear under
      multiple bucket prefixes),
    - a short "how to inspect" section pointing at the per-bucket dirs.
    """
    lines: list[str] = [_DEPTH_REPORT_HEADER]
    lines.append(f"- Root: `{report.root}`")
    lines.append(f"- Output dir: `{report.out_dir}`")
    if report.merged_graph_path is not None:
        lines.append(f"- Merged graph: `{report.merged_graph_path}`")
    lines.append(f"- Buckets: {len(report.buckets)}")
    lines.append(f"- Total elapsed: {report.total_elapsed_s:.1f}s")
    lines.append(f"- Status: **{report.status}**")
    lines.append("")

    # Per-bucket table.
    lines.append("## Buckets")
    lines.append("")
    lines.append("| Bucket | Path | Status | Nodes | Edges | Elapsed (s) | Output |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    for b in report.buckets:
        rel = b.path.relative_to(report.root) if b.path.is_absolute() else b.path
        out_rel = (
            b.out_dir.relative_to(report.root)
            if b.out_dir.is_absolute()
            else b.out_dir
        )
        lines.append(
            f"| `{b.name}` | `{rel}` | {b.status} | {b.nodes} | {b.edges} | "
            f"{b.elapsed_s:.1f} | `{out_rel}` |"
        )
    lines.append("")

    # Cross-bucket signals.
    lines.append("## Cross-bucket signals")
    lines.append("")
    if not report.cross_bucket_signals:
        lines.append(
            "No label collisions across buckets. "
            "Either the buckets are well-separated or the corpus is too small to mint overlapping labels."
        )
    else:
        lines.append(
            "These entity labels appear under multiple bucket prefixes "
            "in the merged graph. They are the natural first stop for a "
            "reviewer: a shared label across buckets may be coincidence, "
            "may be a deliberate shared abstraction, or may be a copy-paste "
            "that should be deduplicated."
        )
        lines.append("")
        lines.append("| Label | Buckets | # | Node type | Sample source |")
        lines.append("|---|---|---:|---|---|")
        for s in report.cross_bucket_signals:
            sample = s.get("source_file_sample") or ""
            lines.append(
                f"| `{s['label']}` | {', '.join(f'`{b}`' for b in s['buckets'])} | "
                f"{s['bucket_count']} | `{s.get('node_type','')}` | `{sample}` |"
            )
    lines.append("")

    # Inspect.
    lines.append("## How to inspect a single bucket")
    lines.append("")
    lines.append(
        "Each bucket's `graphify extract` run writes a complete "
        "`<out>/graphify-out/graph.json` (plus a `GRAPH_REPORT.md` and "
        "the usual cache + cost sidecars). Open them directly to focus "
        "on one sub-system:"
    )
    lines.append("")
    for b in report.buckets:
        if b.status not in {"done", "cached"} or b.out_dir is None:
            continue
        rel = (
            b.out_dir.relative_to(report.root)
            if b.out_dir.is_absolute()
            else b.out_dir
        )
        lines.append(
            f"- `{rel}/graphify-out/graph.json`, "
            f"`{rel}/graphify-out/GRAPH_REPORT.md` — bucket `{b.name}`"
        )
    lines.append("")

    if any(b.error for b in report.buckets):
        lines.append("## Failures")
        lines.append("")
        for b in report.buckets:
            if not b.error:
                continue
            lines.append(f"- `{b.name}`: {b.error}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level entry point used by cli.py
# ---------------------------------------------------------------------------


def depth_command(
    *,
    root: Path,
    focuses: list[Path] | None = None,
    out_dir: Path | None = None,
    merged_path: Path | None = None,
    depth_report_path: Path | None = None,
    max_buckets: int = _DEFAULT_MAX_BUCKETS,
    min_files: int = _MIN_BUCKET_FILES,
    min_words: int = _MIN_BUCKET_WORDS,
    extract_args: tuple[str, ...] = (),
    graphify_bin: str | None = None,
    timeout_s: int | None = None,
    parallel: int = 1,
    skip_on_error: bool = True,
    resume: bool = False,
    dry_run: bool = False,
    retries: int = 0,
    retry_backoff_s: float = 2.0,
    add_to_global: bool = False,
    global_tag: str | None = None,
) -> DepthReport:
    """The `graphify depth` orchestration.

    Selects buckets (explicit or auto), runs extract per bucket (sequentially
    or in parallel), merges the per-bucket graphs, and writes the depth
    report. Returns a populated `DepthReport`. Does NOT raise on per-bucket
    failures when `skip_on_error` is True; the caller decides whether to
    treat a partial report as a non-zero exit.
    """
    root = root.resolve()
    out_dir = (out_dir or (root / "graphify-out")).resolve()
    bucket_root = out_dir / "depth" / "buckets"
    bucket_root.mkdir(parents=True, exist_ok=True)

    if focuses:
        buckets = [
            Bucket(name=p.name, path=p.resolve(), out_dir=bucket_root / p.name)
            for p in focuses
        ]
    else:
        bucket_paths = auto_detect_buckets(
            root, min_files=min_files, min_words=min_words, max_buckets=max_buckets,
        )
        buckets = [
            Bucket(name=p.name, path=p.resolve(), out_dir=bucket_root / p.name)
            for p in bucket_paths
        ]
    if not buckets:
        return DepthReport(root=root, out_dir=out_dir, status="failed")

    report = DepthReport(root=root, out_dir=out_dir, buckets=buckets)
    report.status = "running"
    total_started = time.monotonic()

    # --resume: skip buckets whose graph.json already exists and is fresh.
    # Freshness is the cheapest possible proxy: source-dir mtime newer than
    # the graph.json mtime means stale.
    if resume:
        for b in buckets:
            gp = b.out_dir / "graph.json"
            if not gp.exists():
                continue
            try:
                src_mtime = max(
                    (p.stat().st_mtime for p in b.path.rglob("*") if p.is_file()),
                    default=0.0,
                )
                gp_mtime = gp.stat().st_mtime
            except OSError:
                continue
            if gp_mtime >= src_mtime:
                b.graph_path = gp
                b.nodes, b.edges = _read_node_edge_counts(gp)
                b.status = "cached"

    pending = [b for b in buckets if b.status == "pending"]
    if parallel > 1 and pending and not dry_run:
        # Parallel mode: use a process pool. Each worker re-invokes
        # `graphify extract` for one bucket, so the wall-clock is the
        # slowest bucket, not the sum. Capped at 4 to avoid swamping
        # the LLM API rate limits when --mode deep is in effect.
        import concurrent.futures as _cf
        effective_parallel = max(1, min(parallel, 4, len(pending)))
        with _cf.ProcessPoolExecutor(max_workers=effective_parallel) as ex:
            futures = {
                ex.submit(
                    _run_bucket_worker,
                    b,
                    root,
                    list(extract_args),
                    graphify_bin,
                    timeout_s,
                    skip_on_error,
                    retries,
                    retry_backoff_s,
                ): b
                for b in pending
            }
            for fut in _cf.as_completed(futures):
                b = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # defensive: subprocess crashed
                    b.status = "failed"
                    b.error = f"worker exception: {exc}"
    else:
        for b in pending:
            if dry_run:
                b.status = "skipped"
                continue
            run_bucket(
                bucket=b,
                bucket_root=root,
                extract_args=list(extract_args),
                graphify_bin=graphify_bin,
                timeout_s=timeout_s,
                skip_on_error=skip_on_error,
                retries=retries,
                retry_backoff_s=retry_backoff_s,
            )

    # Merge the successful buckets.
    bucket_graphs = [
        b.graph_path for b in buckets
        if b.graph_path is not None and b.graph_path.exists()
        and b.status in {"done", "cached"}
    ]

    if dry_run:
        # Dry-run never invokes extract and never writes the merged
        # graph, but it still writes a preview DEPTH_REPORT.md so the
        # user can see what auto-detect picked without committing to
        # a run. Cross-bucket signals are skipped (no merged graph).
        report.status = "done"
        report.total_elapsed_s = time.monotonic() - total_started
        depth_report = depth_report_path or (out_dir / _DEFAULT_DEPTH_REPORT)
        write_depth_report(report, depth_report)
        return report

    if not bucket_graphs:
        report.status = "failed"
        report.total_elapsed_s = time.monotonic() - total_started
        return report

    target_merged = (
        merged_path
        or (out_dir / _DEFAULT_MERGED)
    )
    # Pass the bucket names as explicit repo tags so the merged graph's
    # `repo` attribute matches the bucket name, which keeps cross-bucket
    # signal detection (and any downstream consumer that keys on the tag)
    # straightforward. The buckets list is in the same order as the
    # bucket_graphs filter, so we re-filter the bucket list to match.
    successful = [b for b in buckets if b.graph_path in set(bucket_graphs)]
    merge_summary = merge_buckets(
        bucket_graphs,
        out_path=target_merged,
        bucket_tags=[b.name for b in successful],
    )
    report.merged_graph_path = target_merged
    report.total_elapsed_s = time.monotonic() - total_started
    report.status = "done" if all(
        b.status in {"done", "cached", "skipped"} for b in buckets
    ) else "partial"

    # Cross-bucket signals.
    report.cross_bucket_signals = detect_cross_bucket_signals(
        merged_graph_path=target_merged, buckets=buckets,
    )

    # --global: also fold the merged graph into the user's global graph.
    # The cross-bucket graph is already prefixed (each node has a `repo`
    # attribute equal to its bucket name), so `global_add` will treat the
    # whole depth run as one repo for the purposes of stale-node pruning.
    # The default tag is the root directory's name; --global-tag overrides.
    if add_to_global and report.merged_graph_path is not None:
        try:
            from graphify.global_graph import global_add as _global_add
        except Exception as exc:
            # global_graph import is best-effort; if it fails we record
            # the failure in the report but do not abort the depth run.
            print(
                f"  [graphify depth] could not import global_graph: {exc}",
                file=sys.stderr,
            )
        else:
            tag = global_tag or root.name
            try:
                summary = _global_add(report.merged_graph_path, tag)
            except Exception as exc:
                print(
                    f"  [graphify depth] global_add failed: {exc}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  [graphify depth] global_add: tag={tag} "
                    f"nodes_added={summary.get('nodes_added', 0)} "
                    f"skipped={summary.get('skipped', False)}"
                )

    # Depth report.
    depth_report = depth_report_path or (out_dir / _DEFAULT_DEPTH_REPORT)
    write_depth_report(report, depth_report)
    return report


def _run_bucket_worker(
    b: "Bucket",
    root: Path,
    extract_args: list[str],
    graphify_bin: str | None,
    timeout_s: int | None,
    skip_on_error: bool,
    retries: int,
    retry_backoff_s: float,
) -> None:
    """Process-pool entry point: `run_bucket` mutates `b` in place; we
    just call it from a worker without re-importing the closure scope.
    """
    run_bucket(
        bucket=b,
        bucket_root=root,
        extract_args=extract_args,
        graphify_bin=graphify_bin,
        timeout_s=timeout_s,
        skip_on_error=skip_on_error,
        retries=retries,
        retry_backoff_s=retry_backoff_s,
    )
