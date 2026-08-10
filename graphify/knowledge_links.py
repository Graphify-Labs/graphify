"""Validated, explicit cross-domain links supplied by a repository manifest."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

import networkx as nx


SCHEMA = "tetra.knowledge-graph-links.v1"
MANIFEST_PATH = Path("docs/contracts/knowledge_graph_links.v1.json")
ALLOWED_RELATIONS = frozenset({
    "implemented_by", "validated_by", "tests", "evidence_for", "references",
})


class KnowledgeLinkError(ValueError):
    pass


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise KnowledgeLinkError(f"{field} must be a non-empty repo-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise KnowledgeLinkError(f"{field} must be a portable repo-relative path: {value!r}")
    return path.as_posix()


def _load(root: Path) -> tuple[Path, list[dict[str, Any]]] | None:
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeLinkError(f"cannot read {MANIFEST_PATH.as_posix()}: {exc}") from exc
    if payload.get("schema") != SCHEMA:
        raise KnowledgeLinkError(f"manifest schema must be {SCHEMA!r}")
    links = payload.get("links")
    if not isinstance(links, list):
        raise KnowledgeLinkError("manifest links must be an array")
    return manifest_path, links


def _endpoint_node(G: nx.Graph, root: Path, endpoint: Any, field: str) -> str:
    if not isinstance(endpoint, dict):
        raise KnowledgeLinkError(f"{field} must be an object")
    path = _relative_path(endpoint.get("path"), f"{field}.path")
    if not (root / path).is_file():
        raise KnowledgeLinkError(f"{field}.path does not exist: {path}")
    symbol = endpoint.get("symbol")
    if symbol is not None and (not isinstance(symbol, str) or not symbol):
        raise KnowledgeLinkError(f"{field}.symbol must be a non-empty string")
    candidates: list[str] = []
    for node_id, data in G.nodes(data=True):
        source_file = str(data.get("source_file") or "").replace("\\", "/").removeprefix("./")
        if source_file != path:
            continue
        label = str(data.get("label") or "")
        if symbol is not None:
            if label == symbol or label.removesuffix("()") == symbol.removesuffix("()"):
                candidates.append(str(node_id))
            continue
        basename = PurePosixPath(path).name
        if label in {basename, path} or label.endswith("/" + basename):
            candidates.append(str(node_id))
    if len(candidates) != 1:
        detail = "missing" if not candidates else f"ambiguous ({len(candidates)} matches)"
        symbol_detail = f" symbol {symbol!r}" if symbol else " file node"
        raise KnowledgeLinkError(f"{field}{symbol_detail} is {detail}: {path}")
    return candidates[0]


def apply_knowledge_links(G: nx.Graph, root: str | Path | None) -> dict[str, int]:
    if root is None:
        return {"loaded": 0, "applied": 0}
    resolved_root = Path(root).resolve()
    loaded = _load(resolved_root)
    if loaded is None:
        return {"loaded": 0, "applied": 0}
    manifest_path, links = loaded
    seen: set[tuple[str, str, str]] = set()
    resolved: list[tuple[str, str, str, str]] = []
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            raise KnowledgeLinkError(f"links[{index}] must be an object")
        relation = link.get("relation")
        if relation not in ALLOWED_RELATIONS:
            raise KnowledgeLinkError(f"links[{index}].relation is not allowed: {relation!r}")
        rationale = link.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise KnowledgeLinkError(f"links[{index}].rationale must be non-empty")
        source = _endpoint_node(G, resolved_root, link.get("source"), f"links[{index}].source")
        target = _endpoint_node(G, resolved_root, link.get("target"), f"links[{index}].target")
        key = (source, target, relation)
        if key in seen:
            raise KnowledgeLinkError(f"duplicate knowledge link at links[{index}]")
        seen.add(key)
        resolved.append((source, target, relation, rationale.strip()))
    source_file = manifest_path.relative_to(resolved_root).as_posix()
    for source, target, relation, rationale in resolved:
        G.add_edge(
            source, target, relation=relation, confidence="EXTRACTED",
            confidence_score=1.0, weight=1.0, source_file=source_file,
            source_location=None, rationale=rationale, _origin="manifest",
        )
    return {"loaded": len(links), "applied": len(resolved)}
