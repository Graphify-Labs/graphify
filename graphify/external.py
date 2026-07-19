"""Generic external extraction ingress for Graphify integrations."""
from __future__ import annotations

import json
import os
from pathlib import Path

from graphify.validate import assert_valid

_MAX_EXTERNAL_BYTES = 32 * 1024 * 1024
_BUCKETS = ("nodes", "edges", "hyperedges")


def load_extractions(paths: list[Path], *, root: Path) -> dict:
    """Load and merge generic extraction envelopes from trusted integrations.

    Each envelope contains ``nodes``, ``edges``, optional ``hyperedges``, and
    ``source_files``. Source paths are normalized to POSIX paths relative to
    the scan root, matching Graphify's ordinary extraction output.
    """
    merged = {"nodes": [], "edges": [], "hyperedges": [], "source_files": []}
    seen_sources: set[str] = set()
    root = root.resolve()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            raise ValueError(f"external extraction does not exist: {path}")
        if path.stat().st_size > _MAX_EXTERNAL_BYTES:
            raise ValueError(f"external extraction exceeds {_MAX_EXTERNAL_BYTES} bytes: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"external extraction must be an object: {path}")
        if "hyperedges" not in payload:
            payload["hyperedges"] = []
        assert_valid(payload)

        payload_sources = payload.get("source_files")
        if payload_sources is None:
            payload_sources = []
            for bucket in _BUCKETS:
                for item in payload.get(bucket, []):
                    source = item.get("source_file")
                    if source:
                        payload_sources.append(source)
        if not isinstance(payload_sources, list) or not all(
            isinstance(source, str) and source for source in payload_sources
        ):
            raise ValueError(f"external extraction source_files must be a list of strings: {path}")

        for bucket in _BUCKETS:
            for item in payload.get(bucket, []):
                source = item.get("source_file")
                if source:
                    item["source_file"] = _relative_source(source, root)
                item.setdefault("_origin", "external")
                merged[bucket].append(item)
        for source in payload_sources:
            normalized = _relative_source(source, root)
            if normalized not in seen_sources:
                seen_sources.add(normalized)
                merged["source_files"].append(normalized)

    return merged


def _relative_source(source: str, root: Path) -> str:
    path = Path(source)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return os.path.relpath(path.resolve(), root).replace(os.sep, "/")
