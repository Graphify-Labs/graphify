"""YAML structural extractor.

Deterministic, PyYAML-based extraction for ``.yaml``/``.yml`` files so that
config-heavy repositories (Helm charts, Kubernetes manifests, CI pipelines)
contribute nodes to code-only / AST-only runs (``graphify update``) instead of
being skipped entirely (#2214).

Mirrors ``extract_json`` in shape: a file node plus ``contains`` edges to
top-level (and nested) keys, with a pair/depth cap to keep data-heavy YAML from
exploding into orphan nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id
from graphify.ids import normalize_id


def extract_yaml(path: Path) -> dict:
    """Extract structural nodes/edges from a ``.yaml``/``.yml`` file.

    Uses PyYAML (``yaml.safe_load``) when available; returns an error payload
    otherwise so callers degrade gracefully instead of crashing.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        return {"nodes": [], "edges": [], "error": "pyyaml not installed"}

    _YAML_MAX_BYTES = 1_048_576  # 1 MiB

    try:
        with path.open("rb") as _f:
            raw = _f.read(_YAML_MAX_BYTES + 1)
        if len(raw) > _YAML_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "yaml file too large to index"}
        text = raw.decode("utf-8", errors="ignore")
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001 - surface any parse failure to caller
        return {"nodes": [], "edges": [], "error": str(exc)}

    if not isinstance(data, (dict, list)):
        # A scalar document carries no structure worth graphing.
        return {"nodes": [], "edges": [], "skipped": "scalar yaml"}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int = 1, file_type: str = "code") -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {"id": nid, "label": str(label), "file_type": file_type,
                 "source_file": str_path, "source_location": f"L{line}"}
            )

    def add_edge(src: str, tgt: str, relation: str, line: int = 1,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    pair_count = [0]

    def walk(obj: Any, parent_nid: str, parent_key: str | None, depth: int) -> None:
        if depth > 6:
            return
        if isinstance(obj, dict):
            for key, val in obj.items():
                if pair_count[0] >= 500:
                    return
                pair_count[0] += 1
                key_str = str(key)
                if not normalize_id(key_str):
                    continue
                key_nid = _make_id(stem, *(([parent_key] if parent_key else []) + [key_str]))
                if not key_nid:
                    continue
                add_node(key_nid, key_str)
                add_edge(parent_nid, key_nid, "contains")
                if isinstance(val, (dict, list)):
                    walk(val, key_nid, key_str, depth + 1)
        elif isinstance(obj, list):
            # Lists of scalars carry no key structure; only recurse into
            # structured items without minting index nodes (avoids explosion).
            for item in obj:
                if isinstance(item, (dict, list)):
                    walk(item, parent_nid, parent_key, depth + 1)

    walk(data, file_nid, None, 0)
    return {"nodes": nodes, "edges": edges}