"""Compiler-backed batch extraction for .tetra and .t4 sources."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any

from graphify.ids import make_id


SCHEMA = "tetra.symbol-graph.v1"
TETRA_EXTENSIONS = frozenset({".tetra", ".t4"})
TETRA_IGNORED_DIRECTORIES = frozenset({
    ".git", ".workflow", ".tetra_cache", "graphify-out", "reports",
    "dumps", "node_modules", "vendor",
})


def _command(root: Path) -> tuple[list[str] | None, str]:
    configured = os.environ.get("GRAPHIFY_TETRA_BIN", "").strip()
    if configured:
        command = shlex.split(configured)
        return (command or None), "GRAPHIFY_TETRA_BIN"
    executable = shutil.which("tetra")
    if executable:
        return [executable], "PATH"
    go = shutil.which("go")
    if go and (root / "go.work").is_file() and (root / "cli" / "cmd" / "tetra").is_dir():
        return [go, "run", "./cli/cmd/tetra"], "self_host"
    return None, "unavailable"


def _run(command: list[str], args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    timeout = int(os.environ.get("GRAPHIFY_TETRA_TIMEOUT", "180"))
    return subprocess.run(
        [*command, *args], cwd=root, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
    )


def _version(command: list[str], root: Path) -> str:
    try:
        result = _run(command, ["version"], root)
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"


def _cache_key(paths: list[Path], root: Path, compiler_version: str) -> str:
    """Hash the complete Tetra corpus plus both producer schema versions."""
    digest = hashlib.sha256()
    digest.update(f"{SCHEMA}\0{compiler_version}\0".encode())
    for path in sorted(paths):
        try:
            relative = path.relative_to(root).as_posix()
            content = path.read_bytes()
        except (OSError, ValueError):
            continue
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _corpus_paths(root: Path) -> list[Path]:
    """Mirror the compiler exporter's corpus boundary for dependency invalidation."""
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TETRA_EXTENSIONS
        and not TETRA_IGNORED_DIRECTORIES.intersection(path.relative_to(root).parts[:-1])
    )


def _cache_file(cache_root: Path, key: str) -> Path:
    return cache_root.resolve() / "graphify-out" / "cache" / "tetra" / SCHEMA / f"{key}.json"


def _load_batch_cache(cache_root: Path | None, key: str) -> dict[str, Any] | None:
    if cache_root is None:
        return None
    try:
        payload = json.loads(_cache_file(cache_root, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_batch_cache(cache_root: Path | None, key: str, payload: dict[str, Any]) -> None:
    if cache_root is None:
        return
    target = _cache_file(cache_root, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(target)


def _fallback_file_nodes(paths: list[Path], root: Path, status: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for path in sorted(paths):
        try:
            source_file = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        nodes.append({
            "id": make_id("tetra", "file", source_file),
            "label": path.name,
            "file_type": "code",
            "source_file": source_file,
            "source_location": "L1:C1",
            "type": "file",
            "language": "tetra",
            "tetra_status": status,
        })
    return nodes


def _location(item: dict[str, Any]) -> str | None:
    line = item.get("line")
    column = item.get("column")
    if not isinstance(line, int) or line < 1:
        return None
    return f"L{line}:C{column}" if isinstance(column, int) and column > 0 else f"L{line}"


def convert_symbol_graph(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"unsupported Tetra symbol graph schema {payload.get('schema')!r}")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    diagnostics = payload.get("diagnostics", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list) or not isinstance(diagnostics, list):
        raise ValueError("Tetra symbol graph nodes, edges, and diagnostics must be arrays")

    id_map: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    diagnostic_sources = {
        str(item.get("source_file"))
        for item in diagnostics
        if isinstance(item, dict) and item.get("source_file")
    }
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError("Tetra symbol graph node must be an object")
        source_file = str(raw.get("source_file") or "")
        if source_file and Path(source_file).is_absolute():
            raise ValueError(f"absolute source_file is not portable: {source_file}")
        old_id = str(raw.get("id") or "")
        if not old_id:
            raise ValueError("Tetra symbol graph node id is required")
        new_id = make_id("tetra", old_id)
        if new_id in id_map.values():
            raise ValueError(f"Tetra node id collision after normalization: {old_id}")
        id_map[old_id] = new_id
        kind = str(raw.get("kind") or "symbol")
        label = str(raw.get("qualified_name") or raw.get("name") or old_id)
        if kind == "function" and not label.endswith("()"):
            label += "()"
        node: dict[str, Any] = {
            "id": new_id,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": _location(raw),
            "type": kind,
            "language": "tetra",
            "module": raw.get("module") or "",
            "tetra_status": "diagnostic" if source_file in diagnostic_sources else "indexed",
        }
        if kind in {"function", "test"}:
            node["_callable"] = True
        if raw.get("effects"):
            node["effects"] = list(raw["effects"])
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    for raw in raw_edges:
        if not isinstance(raw, dict):
            raise ValueError("Tetra symbol graph edge must be an object")
        source_file = str(raw.get("source_file") or "")
        if source_file and Path(source_file).is_absolute():
            raise ValueError(f"absolute source_file is not portable: {source_file}")
        source = id_map.get(str(raw.get("source") or ""))
        target = id_map.get(str(raw.get("target") or ""))
        if not source or not target:
            raise ValueError("Tetra symbol graph edge has a dangling endpoint")
        edges.append({
            "source": source,
            "target": target,
            "relation": str(raw.get("relation") or "references"),
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "weight": 1.0,
            "source_file": source_file,
            "source_location": _location(raw),
        })

    source_files = {str(node.get("source_file")) for node in nodes if node.get("source_file")}
    return {"nodes": nodes, "edges": edges, "diagnostics": diagnostics, "indexed_sources": source_files}


def _failure(paths: list[Path], root: Path, status: str, compiler_version: str,
             command_source: str, error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "nodes": _fallback_file_nodes(paths, root, status),
        "edges": [],
        "tetra": {
            "schema": SCHEMA, "compiler_version": compiler_version,
            "command_source": command_source, "detected": len(paths),
            "indexed": 0, "diagnostics": 0, "failed": len(paths),
        },
    }
    if error:
        result["error"] = error
    return result


def extract_tetra_batch(
    paths: list[Path], root: Path, *, cache_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    paths = [Path(path).resolve() for path in paths if Path(path).suffix.lower() in TETRA_EXTENSIONS]
    command, command_source = _command(root)
    if command is None:
        print(
            "  warning: Tetra sources detected but no compiler was found; set "
            "GRAPHIFY_TETRA_BIN or put tetra on PATH.",
            file=sys.stderr, flush=True,
        )
        return _failure(paths, root, "compiler_unavailable", "unavailable", command_source)

    compiler_version = _version(command, root)
    # The compiler resolves cross-file imports and calls, so any source change,
    # deletion, or rename invalidates the one batch result even when Graphify's
    # incremental caller hands us only the directly changed path.
    key = _cache_key(_corpus_paths(root), root, compiler_version)
    cached = _load_batch_cache(cache_root, key)
    if cached is not None:
        cached.setdefault("tetra", {})["cache"] = "hit"
        return cached
    try:
        result = _run(command, ["inspect", "symbols", "--root", str(root), str(root), "--format=json"], root)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return _failure(paths, root, "compiler_failed", compiler_version, command_source,
                        f"Tetra compiler invocation failed: {exc}")
    if result.returncode != 0:
        message = result.stderr.strip() or f"exit {result.returncode}"
        return _failure(paths, root, "compiler_failed", compiler_version, command_source,
                        f"Tetra compiler failed: {message}")
    try:
        payload = json.loads(result.stdout)
        converted = convert_symbol_graph(payload, root)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return _failure(paths, root, "invalid_output", compiler_version, command_source,
                        f"invalid Tetra symbol graph: {exc}")

    indexed_sources = converted.pop("indexed_sources")
    diagnostics = converted.pop("diagnostics")
    detected_sources = {
        path.relative_to(root).as_posix() for path in paths if path.is_relative_to(root)
    }
    converted["tetra"] = {
        "schema": SCHEMA,
        "compiler_version": compiler_version,
        "command_source": command_source,
        "detected": len(detected_sources),
        "indexed": len(indexed_sources & detected_sources),
        "diagnostics": len(diagnostics),
        "failed": len(detected_sources - indexed_sources),
        "cache_key": key,
        "cache": "miss",
    }
    _save_batch_cache(cache_root, key, converted)
    return converted


def extract_tetra(path: Path) -> dict[str, Any]:
    """Single-file compatibility entrypoint; extract() uses the batch path."""
    return extract_tetra_batch([path], path.resolve().parent)
