"""Compare JS fact collection or extraction in two existing git checkouts.

Example (run with the same Python environment for both checkouts)::

    python scripts/benchmark_js_fact_collection.py \
        --baseline ../graphify-base --candidate . --source ../openclaw \
        --files 2000 --runs 5 --output /tmp/js-facts.json

Use --mode graph to also verify ordered serialized extraction output. Each
measurement runs in a fresh process, alternates baseline/candidate order, and
uses the same seeded sample. No filesystem-cache flush is attempted. RSS is
process high-water memory before result serialization, not total system memory
or the sum of graph extraction workers. Results are measurements, not CI gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile


def git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(checkout), *args], text=True,
    ).strip()


def worker(source: Path, manifest: Path, mode: str) -> None:
    import contextlib
    from dataclasses import asdict, fields
    from importlib.metadata import version
    import resource
    import time

    from graphify.extract import _raise_recursion_limit, extract
    from graphify.extractors import resolution
    from graphify.extractors.models import _SymbolResolutionFacts
    from graphify.extractors.resolution import _collect_js_symbol_resolution_facts

    _raise_recursion_limit()
    paths = [Path(name) for name in json.loads(manifest.read_text())]
    os.chdir(source)
    # A new empty cache directory for every graph run prevents one arm from
    # benefiting from the other's serialized extraction cache.
    with tempfile.TemporaryDirectory() as cache, contextlib.redirect_stdout(sys.stderr):
        start = time.perf_counter()
        if mode == "facts":
            result = _SymbolResolutionFacts()
            _collect_js_symbol_resolution_facts(paths, result)
        else:
            result = extract([source / path for path in paths], root=source,
                             cache_root=Path(cache), max_workers=2)
        elapsed = time.perf_counter() - start
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    if mode == "facts":
        counts = {field.name: len(getattr(result, field.name)) for field in fields(result)}
        result = asdict(result)
        failed_sources = []
    else:
        counts = {name: len(result[name]) for name in ("nodes", "edges")}
        failed_sources = result["failed_sources"]

    def encode_path(value):
        if isinstance(value, Path):
            return str(value.relative_to(source) if value.is_absolute() else value)
        raise TypeError(f"Unexpected output type: {type(value).__name__}")

    # Sort object keys only. List order is part of the compatibility contract.
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"), default=encode_path)
    print(json.dumps({
        "elapsed_seconds": elapsed,
        "peak_rss_mib": peak_rss / (1024 ** 2 if sys.platform == "darwin" else 1024),
        "output_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "output_bytes": len(serialized.encode()),
        "counts": counts,
        "failed_sources": failed_sources,
        "loaded_resolution_sha256": hashlib.sha256(
            Path(resolution.__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        "dependencies": {name: version(name) for name in (
            "tree-sitter", "tree-sitter-javascript", "tree-sitter-typescript",
        )},
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--files", type=int, default=2000, help="0 selects all eligible files")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mode", choices=("facts", "graph"), default="facts")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-manifest", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    source = args.source.resolve()
    if args.worker_manifest:
        worker(source, args.worker_manifest, args.mode)
        return
    if not args.baseline or not args.candidate or not args.output:
        parser.error("--baseline, --candidate and --output are required")
    if args.files < 0 or args.runs < 1:
        parser.error("--files must be nonnegative and --runs must be positive")

    checkouts = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    # Read tracked paths, so untracked outputs and dependency installations
    # never silently change the corpus. Suffixes mirror the collector contract.
    suffixes = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts",
                ".vue", ".svelte"}
    tracked = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"])
    eligible = sorted(name.decode() for name in tracked.split(b"\0")
                      if name and Path(name.decode()).suffix in suffixes)
    if not eligible:
        parser.error("source has no tracked JS/TS files")
    selected = eligible if not args.files else sorted(
        random.Random(args.seed).sample(eligible, min(args.files, len(eligible)))
    )
    corpus_hash = hashlib.sha256()
    for name in selected:
        corpus_hash.update(name.encode() + b"\0")
        corpus_hash.update(hashlib.sha256((source / name).read_bytes()).digest())
    receipt = {
        "mode": args.mode, "seed": args.seed, "files": selected,
        "corpus_sha256": corpus_hash.hexdigest(),
        "source_commit": git(source, "rev-parse", "HEAD"),
        "source_status": git(source, "status", "--porcelain", "--untracked-files=no"),
        "platform": platform.platform(), "machine": platform.machine(),
        "checkouts": {arm: {
            "commit": git(path, "rev-parse", "HEAD"),
            "status": git(path, "status", "--porcelain"),
            "resolution_sha256": hashlib.sha256(
                (path / "graphify/extractors/resolution.py").read_bytes()).hexdigest(),
        } for arm, path in checkouts.items()},
        "measurements": [],
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        manifest = Path(scratch) / "files.json"
        manifest.write_text(json.dumps(selected))
        for repeat in range(args.runs):
            order = ("baseline", "candidate") if repeat % 2 == 0 else ("candidate", "baseline")
            for arm in order:
                env = dict(os.environ, PYTHONPATH=str(checkouts[arm]), PYTHONHASHSEED="0")
                run = subprocess.run([
                    sys.executable, str(Path(__file__).resolve()), "--source", str(source),
                    "--mode", args.mode, "--worker-manifest", str(manifest),
                ], cwd=checkouts[arm], env=env, capture_output=True, text=True)
                if run.returncode:
                    print(run.stderr, file=sys.stderr)
                    raise SystemExit(f"{arm} worker exited {run.returncode}")
                measurement = dict(json.loads(run.stdout), arm=arm, repeat=repeat + 1)
                if measurement["loaded_resolution_sha256"] != receipt["checkouts"][arm]["resolution_sha256"]:
                    raise SystemExit(f"Wrong collector loaded for {arm}")
                receipt["measurements"].append(measurement)
                output.write_text(json.dumps(receipt, indent=2) + "\n")
                print(f"{arm} {repeat + 1}: {measurement['elapsed_seconds']:.3f}s, "
                      f"{measurement['peak_rss_mib']:.1f} MiB", flush=True)

    hashes = {item["output_sha256"] for item in receipt["measurements"]}
    receipt["ordered_output_equal"] = len(hashes) == 1
    receipt["extraction_complete"] = all(
        not item["failed_sources"] for item in receipt["measurements"]
    )
    summary = {}
    for arm in checkouts:
        summary[arm] = {}
        for metric in ("elapsed_seconds", "peak_rss_mib"):
            values = [item[metric] for item in receipt["measurements"] if item["arm"] == arm]
            summary[arm][metric] = {
                "median": statistics.median(values), "min": min(values), "max": max(values),
            }
    receipt["summary"] = summary
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["summary"], indent=2))
    if not receipt["ordered_output_equal"]:
        raise SystemExit("FAIL: ordered outputs differ; see measurement hashes")
    if not receipt["extraction_complete"]:
        raise SystemExit("FAIL: extraction has failed sources; see measurement receipts")


if __name__ == "__main__":
    main()
