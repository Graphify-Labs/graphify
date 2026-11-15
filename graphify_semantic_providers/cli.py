"""Command line interface for optional semantic provider runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from graphify.paths import write_json_atomic

from .contracts import ProviderKind, ProviderRun, ProviderStatus
from .lsp import discover_files, resolve_command, run_provider
from .merge import merge_runs
from .registry import ProviderRegistry, builtin_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graphify-semantic")
    parser.add_argument(
        "--manifest",
        action="append",
        type=Path,
        default=[],
        help="operator-trusted custom provider JSON manifest",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list built-in and custom providers")
    list_parser.add_argument("--json", action="store_true")

    run_parser = sub.add_parser("run", help="collect bounded local semantic evidence")
    run_parser.add_argument("path", type=Path)
    run_parser.add_argument("--provider", action="append", default=[])
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--max-files", type=int, default=200)
    run_parser.add_argument("--max-symbols", type=int, default=5_000)
    run_parser.add_argument("--max-relationship-requests", type=int, default=500)
    run_parser.add_argument("--request-timeout", type=float, default=20.0)

    merge_parser = sub.add_parser("merge", help="add provider results to a separate graph file")
    merge_parser.add_argument("graph", type=Path)
    merge_parser.add_argument("runs", type=Path)
    merge_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        registry = _registry(args.manifest)
        if args.command == "list":
            return _list(registry, args.json)
        if args.command == "run":
            return _run(args, registry)
        if args.command == "merge":
            return _merge(args)
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"graphify-semantic: {exc}", file=sys.stderr)
        return 2
    return 2


def _registry(manifests: list[Path]) -> ProviderRegistry:
    registry = builtin_registry()
    for path in manifests:
        registry.load_manifest(path.resolve())
    return registry


def _list(registry: ProviderRegistry, as_json: bool) -> int:
    rows = [
        {
            "name": spec.name,
            "languages": list(spec.languages),
            "extensions": list(spec.extensions),
            "available": resolve_command(spec) is not None,
            "description": spec.description,
        }
        for spec in registry.all()
    ]
    if as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            availability = "available" if row["available"] else "not installed"
            print(f"{row['name']}: {', '.join(row['languages'])} ({availability})")
    return 0


def _run(args: argparse.Namespace, registry: ProviderRegistry) -> int:
    root = args.path.resolve()
    if not root.is_dir():
        raise ValueError(f"workspace does not exist: {root}")
    requested = args.provider or ["auto"]
    if "auto" in requested:
        specs = [spec for spec in registry.for_workspace(root) if discover_files(root, spec, 1)]
    else:
        specs = [registry.get(name) for name in requested]
    runs = [
        run_provider(
            spec,
            root,
            max_files=_positive_int(args.max_files, "max-files"),
            max_symbols=_positive_int(args.max_symbols, "max-symbols"),
            max_relationship_requests=_positive_int(
                args.max_relationship_requests, "max-relationship-requests"
            ),
            request_timeout=_positive_float(args.request_timeout, "request-timeout"),
        )
        for spec in specs
    ]
    payload = {
        "contract": "graphify-semantic-providers/v1",
        "workspace": root.name,
        "runs": [run.to_dict() for run in runs],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out.resolve(), payload, indent=2)
    completed = sum(
        run.status in {ProviderStatus.COMPLETED, ProviderStatus.BUDGET_EXHAUSTED} for run in runs
    )
    print(f"wrote {args.out}: {completed}/{len(runs)} provider runs produced bounded evidence")
    return 0 if completed or not runs else 1


def _merge(args: argparse.Namespace) -> int:
    graph = _read_json(args.graph, 512 * 1024 * 1024)
    payload = _read_json(args.runs, 256 * 1024 * 1024)
    raw_runs = payload.get("runs", []) if isinstance(payload, dict) else []
    runs: list[ProviderRun] = []
    for raw in raw_runs:
        if not isinstance(raw, dict):
            continue
        try:
            status = ProviderStatus(raw.get("status"))
        except ValueError:
            continue
        try:
            provider_kind = ProviderKind(raw.get("provider_kind", "semantic"))
        except ValueError:
            continue
        runs.append(
            ProviderRun(
                provider=str(raw.get("provider", "unknown")),
                status=status,
                provider_kind=provider_kind,
                version=str(raw.get("version", "unknown")),
                run_id=str(raw.get("run_id", "")) or "legacy-unknown",
                timestamp=str(raw.get("timestamp", "")) or "unknown",
                nodes=raw.get("nodes", []) if isinstance(raw.get("nodes"), list) else [],
                edges=raw.get("edges", []) if isinstance(raw.get("edges"), list) else [],
            )
        )
    merged = merge_runs(graph, runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out.resolve(), merged, indent=2)
    print(f"wrote additive semantic graph: {args.out}")
    return 0


def _read_json(path: Path, max_bytes: int) -> Any:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"file does not exist: {resolved}")
    if resolved.stat().st_size > max_bytes:
        raise ValueError(f"file exceeds size limit: {resolved}")
    return json.loads(resolved.read_bytes())


def _positive_int(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(value: float, name: str) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
