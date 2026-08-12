"""Body-free Graphify export for MemoryGuard CodeGraph V2.

The exporter runs normal Graphify extraction, then emits only repository-
relative paths, hashes, structural node/edge metadata, source maps, and
provenance. Source bodies and absolute paths are never included.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata as importlib_metadata
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from graphify.extract import collect_files, extract
from graphify.extractors.embedded import provenance_for_path


EXPORT_FORMAT = "memoryguard-graphify-metadata-v1"
_SOURCE_LOCATION = re.compile(r"^L(?P<start>\d+)(?:[-:](?:L)?(?P<end>\d+))?$")
_BODY_MARKERS = ("{", "}", "<script", "</", "```", "'''", '\"\"\"')


def _distribution_version() -> str:
    for name in ("graphifyy", "graphify"):
        try:
            return importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            continue
    return "unknown"


# Resolve once while this module is imported from the active Graphify package.
# Re-scanning importlib.metadata after a caller changes cwd can accidentally see
# a different globally-installed distribution when running from a source tree.
_GRAPHIFY_VERSION = _distribution_version()


def _version() -> str:
    return _GRAPHIFY_VERSION


def _relative(root: Path, value: Any) -> str:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return ""
    candidate = Path(value)
    try:
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        relative = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        return ""
    if not relative or relative.startswith("../"):
        return ""
    return relative


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _language(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {
        ".py": "python", ".js": "javascript", ".mjs": "javascript",
        ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".jsx": "javascript", ".vue": "vue", ".svelte": "svelte",
        ".html": "html", ".css": "css", ".md": "markdown",
        ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
        ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp", ".c": "c",
        ".h": "c", ".hpp": "cpp", ".rb": "ruby", ".php": "php",
        ".sql": "sql", ".sh": "bash", ".ps1": "powershell",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def _line_map(relative_path: str, source_location: str) -> dict[str, Any]:
    result: dict[str, Any] = {"path": relative_path}
    match = _SOURCE_LOCATION.match(_safe_source_location(source_location))
    if match:
        result["line_start"] = int(match.group("start"))
        result["line_end"] = int(match.group("end") or match.group("start"))
    return result


def _safe_source_location(value: Any) -> str:
    """Keep only the line-range form; never export arbitrary extractor text."""
    text = str(value or "").strip()
    return text if _SOURCE_LOCATION.fullmatch(text) else ""


def _safe_export_text(value: Any, *, limit: int) -> str:
    text = str(value or "")
    if any(marker in text.casefold() for marker in _BODY_MARKERS):
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _semantic_id(semantic_kind: str, name: str, external_id: str) -> str:
    kind = str(semantic_kind or "")
    label = str(name or "")
    if kind == "api_method" and label:
        return "semantic-api-" + hashlib.sha256(label.encode("utf-8")).hexdigest()
    if kind == "surface_spec" and label:
        public = label.split(":", 1)[1] if label.startswith("GuiOperationSpec:") else label
        return "semantic-surface-" + hashlib.sha256(public.encode("utf-8")).hexdigest()
    if kind == "native_handler" and label:
        return "semantic-native-" + hashlib.sha256(label.lstrip("_").encode("utf-8")).hexdigest()
    return external_id


def _semantic_priority(row: Mapping[str, Any]) -> tuple[int, str]:
    kind = str(row.get("semantic_kind") or "")
    path = str((row.get("source_map") or {}).get("path") or "")
    if kind == "api_method":
        return (0 if path.endswith("/surfaces.py") or path.endswith("surfaces.py") else 1, path)
    if kind == "native_handler":
        return (0 if path.endswith("/native_ports.py") or path.endswith("native_ports.py") else 1, path)
    return (0, path)


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = {
        "semantic_kind", "host_symbol", "region_id", "virtual_document_id",
        "confidence", "language", "node_kind", "control_kind", "action",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        item = value.get(key)
        if isinstance(item, str):
            safe = _safe_export_text(item, limit=256)
            if safe:
                result[key] = safe
        elif isinstance(item, (int, float, bool)) or item is None:
            result[key] = item
    return result


def export_repository(
    root: str | Path,
    *,
    paths: Iterable[str | Path] | None = None,
    complete: bool = True,
    parallel: bool = True,
    max_files: int = 50_000,
) -> dict[str, Any]:
    repo = Path(root).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("repository root is not a directory")
    if paths is None:
        files = collect_files(repo, follow_symlinks=False, root=repo)
    else:
        files = []
        for raw in paths:
            candidate = Path(raw)
            candidate = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()
            try:
                candidate.relative_to(repo)
            except ValueError as exc:
                raise ValueError("export path escapes repository root") from exc
            if candidate.is_file():
                files.append(candidate)
    files = sorted(dict.fromkeys(files), key=lambda item: item.as_posix().casefold())
    if not files:
        raise ValueError("graphify export has no source files")
    if len(files) > max(1, int(max_files)):
        raise ValueError("graphify export exceeds file limit")

    file_rows: list[dict[str, Any]] = []
    file_by_path: dict[str, dict[str, Any]] = {}
    for file_path in files:
        relative = file_path.relative_to(repo).as_posix()
        provenance = provenance_for_path(relative)
        item = {
            "id": "file:" + hashlib.sha256(relative.encode("utf-8")).hexdigest(),
            "path": relative,
            "content_hash": _sha256(file_path),
            "language": _language(relative),
            "source_role": provenance,
            "provenance": provenance,
        }
        file_rows.append(item)
        file_by_path[relative] = item

    extracted = extract(files, root=repo, parallel=bool(parallel))
    raw_nodes = list(extracted.get("nodes") or [])
    raw_edges = list(extracted.get("edges") or [])
    node_by_id: dict[str, dict[str, Any]] = {}
    node_file: dict[str, dict[str, Any]] = {}
    external_to_canonical: dict[str, str] = {}

    for node in raw_nodes:
        if not isinstance(node, Mapping):
            continue
        external_id = str(node.get("id") or "").strip()
        if not external_id:
            continue
        file_type = _safe_export_text(node.get("file_type") or node.get("kind") or "symbol", limit=128)
        if file_type.casefold() in {"rationale", "docstring", "source_body", "comment"}:
            # Rationale labels are source text, not graph metadata.
            continue
        relative = _relative(repo, node.get("source_file"))
        file_item = file_by_path.get(relative)
        if file_item is None:
            continue
        provenance = file_item["provenance"]
        source_location = _safe_source_location(node.get("source_location"))
        source_map = _line_map(relative, source_location)
        raw_source_map = node.get("source_map")
        if isinstance(raw_source_map, Mapping):
            for key in ("host_symbol", "region_id", "virtual_document_id", "line_start", "line_end"):
                value = raw_source_map.get(key)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    source_map[key] = value
        raw_metadata = node.get("metadata")
        metadata_kind = raw_metadata.get("semantic_kind") if isinstance(raw_metadata, Mapping) else ""
        semantic_kind = _safe_export_text(node.get("semantic_kind") or metadata_kind or "", limit=128)
        name = _safe_export_text(node.get("label") or node.get("name") or external_id, limit=2048) or "symbol"
        canonical_id = _semantic_id(semantic_kind, name, external_id)
        external_to_canonical[external_id] = canonical_id
        row = {
            "id": canonical_id,
            "file": file_item["id"],
            "name": name,
            "kind": file_type or "symbol",
            "signature": _safe_export_text(node.get("signature"), limit=4096),
            "source_location": source_location,
            "provenance": provenance,
            "semantic_kind": semantic_kind,
            "source_map": source_map,
            "metadata": _safe_metadata(node.get("metadata")),
        }
        row["metadata"].setdefault("semantic_kind", semantic_kind)
        row["symbol_hash"] = hashlib.sha256(
            json.dumps(
                {key: row[key] for key in ("name", "kind", "signature", "source_location", "semantic_kind", "source_map")},
                sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        existing = node_by_id.get(canonical_id)
        if existing is None or _semantic_priority(row) < _semantic_priority(existing):
            node_by_id[canonical_id] = row
            node_file[canonical_id] = file_item

    node_rows = list(node_by_id.values())
    edge_rows: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, ...]] = set()
    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            continue
        source_external = str(edge.get("source") or "").strip()
        target_external = str(edge.get("target") or "").strip()
        source = external_to_canonical.get(source_external, source_external)
        target = external_to_canonical.get(target_external, target_external)
        if source not in node_by_id or target not in node_by_id:
            continue
        source_item = node_file[source]
        provenance = source_item["provenance"]
        relation = _safe_export_text(edge.get("relation") or "related", limit=128) or "related"
        context = _safe_export_text(edge.get("context"), limit=256)
        source_location = _safe_source_location(edge.get("source_location"))
        identity = (source, target, relation, context, provenance, source_location)
        if identity in seen_edges:
            continue
        seen_edges.add(identity)
        raw_edge_metadata = edge.get("metadata")
        edge_metadata_kind = raw_edge_metadata.get("semantic_kind") if isinstance(raw_edge_metadata, Mapping) else ""
        semantic_kind = _safe_export_text(edge.get("semantic_kind") or edge_metadata_kind or context, limit=128)
        metadata = _safe_metadata(edge.get("metadata"))
        metadata.setdefault("semantic_kind", semantic_kind)
        confidence = edge.get("confidence")
        if isinstance(confidence, str):
            safe_confidence = _safe_export_text(confidence, limit=64)
            if safe_confidence:
                metadata["confidence"] = safe_confidence
        try:
            weight = float(edge.get("weight", 1.0) or 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        edge_rows.append({
            "source": source,
            "target": target,
            "relation": relation,
            "context": context,
            "source_file": source_item["path"],
            "source_location": source_location,
            "provenance": provenance,
            "semantic_kind": semantic_kind,
            "metadata": metadata,
            "weight": weight,
        })

    source_digest = hashlib.sha256(
        json.dumps(
            [(item["path"], item["content_hash"], item["provenance"]) for item in file_rows],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    diagnostics: list[dict[str, Any]] = []
    for item in extracted.get("diagnostics") or []:
        if isinstance(item, Mapping):
            diagnostics.append({
                key: value
                for key, value in item.items()
                if key in {"code", "error_type", "limit", "bytes", "count"}
                and isinstance(value, (str, int, bool))
            })
    return {
        "format": EXPORT_FORMAT,
        "complete": bool(complete),
        "graphify_version": _version(),
        "source_digest": source_digest,
        "files": file_rows,
        "nodes": node_rows,
        "edges": edge_rows,
        "diagnostics": diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export body-free Graphify metadata for MemoryGuard")
    parser.add_argument("root")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--no-parallel", action="store_true")
    args = parser.parse_args(argv)
    payload = export_repository(
        args.root,
        paths=args.paths or None,
        complete=not args.incremental,
        parallel=not args.no_parallel,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EXPORT_FORMAT", "export_repository", "main"]
