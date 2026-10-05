"""Controller-owned chunk provenance checks for generated skill runbooks."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from graphify.cache import scope_semantic_result
from graphify.paths import write_json_atomic

_MANIFEST = ".graphify_dispatch.json"
_CHUNK_NAME = re.compile(r"\.graphify_chunk_([0-9a-f]{32})_([0-9]+)\.json\Z")


def prepare_semantic_dispatch(
    chunks: Iterable[Iterable[str | Path]],
    *,
    root: str | Path,
    output_dir: str | Path = "graphify-out",
) -> list[dict]:
    """Record exact FILE_LIST inputs and allocate fresh run-owned chunk paths.

    The UUID identifies output artifacts only; it never enters graph node IDs.
    Inline-return hosts also write each result to its assigned path before B3.
    """
    output = Path(output_dir).resolve()
    run_id = uuid4().hex
    assignments: dict[str, list[str]] = {}
    dispatch: list[dict] = []
    for index, files in enumerate(chunks, 1):
        if isinstance(files, (str, bytes)):
            raise ValueError("Each semantic chunk must contain a list of file paths.")
        paths = []
        for source in files:
            if not isinstance(source, (str, Path)) or not str(source).strip():
                raise ValueError("Semantic FILE_LIST entries must be non-empty file paths.")
            paths.append(str(source))
        if not paths:
            raise ValueError("A semantic chunk cannot have an empty FILE_LIST.")
        name = f".graphify_chunk_{run_id}_{index:02d}.json"
        assignments[name] = paths
        dispatch.append({"path": str(output / name), "files": paths})
    output.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output / _MANIFEST, {
        "version": 1, "run_id": run_id, "root": str(Path(root).resolve()),
        "chunks": assignments,
    }, ensure_ascii=False)
    return dispatch


def assert_semantic_scope(
    result: dict,
    *,
    root: str | Path,
    allowed_source_files: Iterable[str | Path],
) -> None:
    """Refuse a chunk's foreign provenance without modifying its input.

    Use the cache's walked-path identity rules instead of another path normalizer.
    Cross-chunk edge endpoints are allowed; their source_file must belong to the
    referring chunk, and no foreign node definition may be supplied as a stub.
    """
    for bucket in ("nodes", "edges", "hyperedges"):
        items = result.get(bucket, [] if bucket == "hyperedges" else None)
        if not isinstance(items, list):
            raise ValueError(f"Semantic chunk {bucket} must be a list.")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("source_file"), str):
                raise ValueError(f"Every semantic {bucket} item needs an originating source_file.")
            if not item["source_file"].strip():
                raise ValueError(f"Every semantic {bucket} item needs a non-empty source_file.")
    checked = deepcopy(result)
    dropped_files, count = scope_semantic_result(
        checked, root=Path(root), allowed_source_files=allowed_source_files,
    )
    if count:
        raise ValueError(
            f"Refusing semantic chunk: {count} item(s) outside its FILE_LIST: "
            f"{sorted(dropped_files)!r}. Re-extract before caching or merging."
        )


def collect_semantic_dispatch(output_dir: str | Path = "graphify-out") -> dict:
    """Validate every current-run chunk before aggregating or saving any result.

    Only controller-planned basenames are read. Stale glob matches are ignored,
    and a missing current output can never reuse an older run's chunk number.
    """
    output = Path(output_dir)
    if (output / _MANIFEST).is_symlink():
        raise ValueError("Controller dispatch manifest must not be a symlink.")
    manifest = json.loads((output / _MANIFEST).read_text(encoding="utf-8"))
    run_id = manifest.get("run_id")
    assignments = manifest.get("chunks")
    if (manifest.get("version") != 1 or not isinstance(run_id, str)
            or not re.fullmatch(r"[0-9a-f]{32}", run_id)
            or not isinstance(assignments, dict) or not isinstance(manifest.get("root"), str)):
        raise ValueError("Invalid controller dispatch manifest; prepare a new semantic run.")
    chunks: list[dict] = []
    missing: list[str] = []
    for name, files in assignments.items():
        match = _CHUNK_NAME.fullmatch(name) if isinstance(name, str) else None
        if (match is None or match.group(1) != run_id or not isinstance(files, list)
                or not files or not all(isinstance(f, str) and f.strip() for f in files)):
            raise ValueError("Chunk does not belong to the controller's current dispatch run.")
        chunk_path = output / name
        if chunk_path.is_symlink():
            raise ValueError(f"Semantic chunk {name!r} must not be a symlink.")
        if not chunk_path.is_file():
            missing.append(name)
            continue
        result = json.loads(chunk_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError(f"Semantic chunk {name!r} must be a JSON object.")
        assert_semantic_scope(result, root=manifest["root"], allowed_source_files=files)
        chunks.append(result)
    if missing and len(missing) * 2 > len(assignments):
        raise ValueError(f"More than half the current semantic chunks are missing: {missing!r}")
    merged: dict = {
        "nodes": [], "edges": [], "hyperedges": [],
        "input_tokens": 0, "output_tokens": 0, "missing_chunks": missing,
        "dispatched_source_files": [source for files in assignments.values() for source in files],
    }
    for chunk in chunks:
        for bucket in ("nodes", "edges", "hyperedges"):
            merged[bucket].extend(chunk.get(bucket, []))
        for key in ("input_tokens", "output_tokens"):
            merged[key] += int(chunk.get(key, 0))
    return merged


def load_skill_update_extraction(
    semantic_files: Iterable[str | Path],
    *,
    root: str | Path,
    prompt_file: str | Path,
    output_dir: str | Path = "graphify-out",
) -> dict:
    """Bind a destructive update to owned inputs, never a stale aggregate.

    Semantic cache records are read again by walked source identity and prompt
    fingerprint, not from an earlier cached/semantic/extract sidecar. The AST
    sidecar is kept separate: structural cross-file records have different
    ownership semantics and must not be scoped as semantic stubs.
    """
    from graphify.cache import _semantic_source_matcher, check_semantic_cache

    files = [str(f) for f in semantic_files]
    fresh = collect_semantic_dispatch(output_dir)
    assert_semantic_scope(fresh, root=root, allowed_source_files=files)
    planned = fresh["dispatched_source_files"]
    assert_semantic_scope({"nodes": [{"source_file": f} for f in planned], "edges": []},
                          root=root, allowed_source_files=files)
    source_identity, _ = _semantic_source_matcher(Path(root))
    dispatched = {source_identity(f) for f in planned}
    # B3 has already saved fresh results. Do not read them a second time as cache
    # hits, or repeat their edges; failed dispatched chunks must not replay cache.
    cache_files = [f for f in files if source_identity(f) not in dispatched]
    ast = json.loads((Path(output_dir) / ".graphify_ast.json").read_text(encoding="utf-8"))
    nodes, edges, hyperedges, _ = check_semantic_cache(cache_files, root=Path(root),
                                                     prompt_file=prompt_file)
    cached = {"nodes": nodes, "edges": edges, "hyperedges": hyperedges}
    assert_semantic_scope(cached, root=root, allowed_source_files=files)
    seen = set()
    merged_nodes = []
    for node in ast.get("nodes", []) + fresh["nodes"] + nodes:
        if node["id"] not in seen:
            seen.add(node["id"])
            merged_nodes.append(node)
    return {
        "nodes": merged_nodes,
        "edges": ast.get("edges", []) + fresh["edges"] + edges,
        "hyperedges": fresh["hyperedges"] + hyperedges,
        "input_tokens": fresh["input_tokens"],
        "output_tokens": fresh["output_tokens"],
    }
