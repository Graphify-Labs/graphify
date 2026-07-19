"""n8n workflow extractor.

An n8n workflow is data-shaped JSON: ``extract_json`` deliberately skips it
(#1224) because a generic key-walk of one turns into hundreds of orphan
key-nodes. But the file *is* the program — its ``nodes`` array is the set of
steps and ``connections`` is the control flow between them. Extracting those
two structures gives the same signal an AST gives a source file, without any of
the key-node noise, so n8n workflows are routed here by content sniff before
generic ``.json`` dispatch.

Sticky notes are canvas annotations rather than steps, so they become
``document`` nodes: they carry the author's block structure ("Блок 1: …") and
are worth keeping, but they never participate in control flow.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

# n8n exports are machine-generated and can be large; the router in a real
# project runs past the 1 MiB ceiling extract_json uses for config files. The
# parse here is a single json.loads plus two shallow walks, not a per-key AST
# walk, so a higher ceiling is affordable.
_MAX_BYTES = 8 * 1024 * 1024

_STICKY_TYPE = "n8n-nodes-base.stickyNote"


def is_n8n_workflow_path(path: Path) -> bool:
    """Return True when ``path`` looks like an exported n8n workflow.

    Sniffs bytes rather than trusting the filename: n8n exports carry no naming
    convention. The ``n8n-nodes-base.`` marker appears in every export that has
    at least one built-in node; the structural fallback catches workflows built
    entirely from community nodes.
    """
    if path.suffix.lower() != ".json":
        return False
    try:
        with path.open("rb") as fh:
            head = fh.read(64 * 1024)
    except OSError:
        return False
    if b'"n8n-nodes-base.' in head:
        return True
    return b'"connections"' in head and b'"typeVersion"' in head


def _line_index(source: str) -> list[int]:
    """Byte-free offset→line lookup table: newline positions in ``source``."""
    offsets = []
    pos = source.find("\n")
    while pos != -1:
        offsets.append(pos)
        pos = source.find("\n", pos + 1)
    return offsets


def _line_of(offset: int, newlines: list[int]) -> int:
    """1-based line number for a character offset."""
    lo, hi = 0, len(newlines)
    while lo < hi:
        mid = (lo + hi) // 2
        if newlines[mid] < offset:
            lo = mid + 1
        else:
            hi = mid
    return lo + 1


def extract_n8n_workflow(path: Path) -> dict[str, Any]:
    """Extract steps and control flow from an exported n8n workflow.

    Behaviour matches the other extractors: ``{"nodes": [...], "edges": [...]}``
    on success, or the same shape plus ``error``/``skipped`` when the file can't
    be used.
    """
    try:
        with path.open("rb") as fh:
            raw = fh.read(_MAX_BYTES + 1)
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}
    if len(raw) > _MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "n8n workflow too large to index"}

    try:
        source = raw.decode("utf-8")
        doc = json.loads(source)
    except (UnicodeDecodeError, ValueError) as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), list):
        return {"nodes": [], "edges": [], "skipped": "not an n8n workflow export"}

    stem = _file_stem(path)
    str_path = str(path)
    newlines = _line_index(source)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    # n8n enforces unique node names within a workflow, and `connections` keys
    # are those names — so name→id is the join between the two structures.
    id_by_name: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int, file_type: str) -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": file_type,
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    def line_of_name(name: str) -> int:
        """Line where a node's own ``"name"`` key sits, or L1 if not found."""
        needle = f'"name": {json.dumps(name, ensure_ascii=False)}'
        offset = source.find(needle)
        return _line_of(offset, newlines) if offset != -1 else 1

    file_nid = _make_id(str(path))
    workflow_label = doc.get("name") or path.name
    add_node(file_nid, str(workflow_label), 1, "code")

    for entry in doc["nodes"]:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        nid = _make_id(stem, name)
        if not nid:
            continue
        node_type = entry.get("type") or ""
        line = line_of_name(name)
        is_sticky = node_type == _STICKY_TYPE
        add_node(nid, name, line, "document" if is_sticky else "code")
        add_edge(file_nid, nid, "contains", line)
        if not is_sticky:
            id_by_name[name] = nid

    connections = doc.get("connections")
    if isinstance(connections, dict):
        for src_name, outputs in connections.items():
            src_nid = id_by_name.get(src_name)
            if not src_nid or not isinstance(outputs, dict):
                continue
            line = line_of_name(src_name)
            for branches in outputs.values():
                if not isinstance(branches, list):
                    continue
                for branch in branches:
                    if not isinstance(branch, list):
                        continue
                    for conn in branch:
                        if not isinstance(conn, dict):
                            continue
                        tgt_nid = id_by_name.get(conn.get("node"))
                        if tgt_nid:
                            add_edge(src_nid, tgt_nid, "calls", line, context="call")

    return {"nodes": nodes, "edges": edges}
