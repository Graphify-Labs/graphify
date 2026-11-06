"""scip_ingest.py — SCIP JSON ingestion (simplified subset).

Reads a simplified SCIP-style JSON structure and converts it into
Graphify nodes and edges. NOT a full SCIP protobuf implementation —
this is a skeleton that consumes the simplified shape described below.

Not wired to the CLI in this phase.

Entry point:
  ingest_scip_json(doc: object, source_file: str = "",
      language: str = "python") -> dict[str, Any]

  Returns {"nodes": [...], "edges": [...]} compatible with Graphify's
  extraction result format. All edges emitted are endpoint-safe — the
  function builds a symbol → node_id index in a first pass and either
  resolves relationship targets via that index or creates a stub
  external node so `build_from_json()` will keep the edge.

Supported (simplified) JSON shape:
  documents[]: { relative_path, language, symbols[] }
  symbols[]:   { symbol, kind, display_name, documentation[],
                 relationships[], occurrences[] }
  relationships[]: { symbol, is_reference, is_implementation,
                     is_type_definition, is_definition }
  occurrences[]: { range[], symbol, symbol_roles }

This shape diverges from the official SCIP protobuf (where occurrences
live on the document, not on each symbol). We consume the simplified
shape that LLM-generated SCIP-style JSON commonly produces.

Real SCIP indexes:
  ingest_scip_index(source: str | PathLike | bytes) -> ScipIngestResult

  Reads an ``index.scip`` written by a SCIP indexer (scip-python,
  scip-typescript, rust-analyzer, ...), decodes it with
  ``graphify.scip_index`` (no protobuf dependency) and maps its
  document-level occurrences onto the shape above, then runs the same
  two passes. See ``ingest_scip_index`` for the mapping and its limits.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, TypedDict

from graphify.scip_index import (
    ScipDecodeError,
    ScipIndex,
    ScipOccurrence,
    ScipSymbol,
    decode_scip_index,
    symbol_display_name,
)
from graphify.security import _max_graph_file_bytes, sanitize_metadata


class _ScipIngestFields(TypedDict):
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]


class ScipIngestResult(_ScipIngestFields, total=False):
    """What ``ingest_scip_index`` returns; ``error`` only when the index could not be read."""

    error: str


class _IngestSymbol(ScipSymbol):
    """A SCIP symbol with its document's occurrences of it, as ``ingest_scip_json`` reads them."""

    occurrences: list[ScipOccurrence]


class _IngestDocument(TypedDict):
    relative_path: str
    language: str
    symbols: list[_IngestSymbol]


class _IngestShape(TypedDict):
    documents: list[_IngestDocument]


def ingest_scip_json(
    doc: object,
    source_file: str = "",
    language: str = "python",
) -> dict[str, Any]:
    """Convert a SCIP-style JSON document into Graphify nodes and edges.

    Parameter ``doc`` is ``object`` (not ``dict[str, Any]``) because SCIP
    documents come from external tools — we may be handed arbitrary
    deserialized JSON. The first check rejects anything that isn't a dict
    and returns the empty result.

    Two-pass design:
      1. Build a ``symbol_str → node_id`` index across every valid symbol
         in every valid document, plus collect per-symbol metadata.
      2. Emit nodes for every indexed symbol and then emit relationship
         edges. Relationship targets are resolved via the index when
         present; otherwise a stub ``scip_external`` node is added so
         edges never dangle.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str, str | None]] = set()

    if not isinstance(doc, dict):
        return {"nodes": nodes, "edges": edges}

    documents = doc.get("documents", [])
    if not isinstance(documents, list):
        return {"nodes": nodes, "edges": edges}

    # ---- pass 1: build symbol → node_id indices -----------------------------
    # Two indices so relationship resolution can be document-aware:
    #   per_doc:  (symbol_id, doc_path) → node_id  (same-document precedence)
    #   global:   symbol_id              → list[node_id] (cross-document fallback,
    #                                                     used only when unambiguous)
    per_doc_index: dict[tuple[str, str], str] = {}
    global_index: dict[str, list[str]] = {}
    # Per-symbol metadata kept for pass-2 node emission (avoids re-walking
    # the document tree).
    symbol_records: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        doc_path = _coerce_str(document.get("relative_path"), source_file)
        doc_language = _coerce_str(document.get("language"), language)
        symbols = document.get("symbols", [])
        if not isinstance(symbols, list):
            continue
        for symbol in symbols:
            if not isinstance(symbol, dict):
                continue
            symbol_id = _coerce_str(symbol.get("symbol"), "")
            if not symbol_id:
                continue
            node_id = _make_scip_node_id(symbol_id, doc_path)
            per_doc_index.setdefault((symbol_id, doc_path), node_id)
            # Dedupe node_ids in the global index — duplicate symbol records
            # within the SAME document produce identical node_ids, and we
            # don't want them to look like cross-document ambiguity.
            candidates = global_index.setdefault(symbol_id, [])
            if node_id not in candidates:
                candidates.append(node_id)
            symbol_records.append(
                {
                    "node_id": node_id,
                    "symbol_id": symbol_id,
                    "doc_path": doc_path,
                    "language": doc_language,
                    "raw": symbol,
                }
            )

    # ---- pass 2: emit nodes + relationship edges -----------------------------
    for record in symbol_records:
        _emit_symbol_node(record, nodes, seen_node_ids)
        _emit_relationships(
            record,
            per_doc_index,
            global_index,
            nodes,
            edges,
            seen_node_ids,
            seen_edges,
        )

    return {"nodes": nodes, "edges": edges}


def ingest_scip_index(source: str | os.PathLike[str] | bytes) -> ScipIngestResult:
    """Convert a real SCIP index (``index.scip``) into Graphify nodes and edges.

    ``source`` is the path of an index file or its bytes. The index is decoded
    by :func:`graphify.scip_index.decode_scip_index` and mapped onto the shape
    :func:`ingest_scip_json` reads, then ingested by it:

    * each symbol a document defines (its ``SymbolInformation``) gets that
      document's occurrences of the symbol, definitions first, so the node's
      ``source_location`` is the line of its definition;
    * SCIP lines are zero-based; they are turned into Graphify's one-based
      lines here, so ``L1`` is the first line of the file;
    * document-local symbols (``local 12``) are left out: they have no
      identity outside their file and carry no name;
    * a symbol without a ``display_name`` (most indexers leave it out) is
      labelled from its last descriptor: ``Square``, ``area()``;
    * relationships become edges exactly as for the JSON shape.

    References between symbols (occurrences without the Definition role) are
    not turned into edges yet: an occurrence does not say which enclosing
    symbol it belongs to unless the indexer writes ``enclosing_range``, and
    guessing would create relationships the index does not state.

    Returns ``{"nodes", "edges"}``. An unreadable, oversized or malformed
    index returns the empty result with an ``"error"`` key instead of raising,
    like ``extract_mcp_config``.
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        try:
            if os.path.getsize(source) > _max_graph_file_bytes():
                return {"nodes": [], "edges": [], "error": "scip index too large to ingest"}
            with open(source, "rb") as handle:
                # Read one byte past the cap: a pipe or device reports no size, so getsize alone cannot bound it.
                data = handle.read(_max_graph_file_bytes() + 1)
        except OSError as exc:
            return {"nodes": [], "edges": [], "error": f"scip_ingest read error: {exc}"}
    if len(data) > _max_graph_file_bytes():
        return {"nodes": [], "edges": [], "error": "scip index too large to ingest"}
    try:
        index = decode_scip_index(data)
    except ScipDecodeError as exc:
        return {"nodes": [], "edges": [], "error": f"scip_ingest decode error: {exc}"}
    result = ingest_scip_json(_index_to_ingest_shape(index))
    return {"nodes": result["nodes"], "edges": result["edges"]}


def _index_to_ingest_shape(index: ScipIndex) -> _IngestShape:
    """Move each document's occurrences under the symbols it defines (see ``ingest_scip_index``)."""
    documents: list[_IngestDocument] = []
    for document in index["documents"]:
        by_symbol: dict[str, list[ScipOccurrence]] = {}
        for occurrence in document["occurrences"]:
            rng, symbol = occurrence["range"], occurrence["symbol"]
            if not symbol or not rng:
                continue
            by_symbol.setdefault(symbol, []).append(
                {
                    "range": [rng[0] + 1, *rng[1:]],  # zero-based SCIP line -> one-based
                    "symbol": symbol,
                    "symbol_roles": occurrence["symbol_roles"],
                }
            )
        symbols: list[_IngestSymbol] = []
        for info in document["symbols"]:
            symbol = info["symbol"]
            if not symbol or symbol.startswith("local "):
                continue
            occurrences = sorted(
                by_symbol.get(symbol, []),
                key=lambda o: (not o["symbol_roles"] & _SCIP_ROLE_DEFINITION, o["range"]),
            )
            ingest_symbol: _IngestSymbol = {
                "symbol": symbol,
                "kind": info["kind"],
                "documentation": info["documentation"],
                "relationships": info["relationships"],
                "display_name": info.get("display_name") or symbol_display_name(symbol),
                "occurrences": occurrences,
            }
            if "enclosing_symbol" in info:
                ingest_symbol["enclosing_symbol"] = info["enclosing_symbol"]
            symbols.append(ingest_symbol)
        documents.append(
            {
                "relative_path": document["relative_path"],
                "language": document.get("language", ""),
                "symbols": symbols,
            }
        )
    return {"documents": documents}


_SCIP_ROLE_DEFINITION = 0x1  # SymbolRole.Definition in scip.proto


def _emit_symbol_node(
    record: dict[str, Any],
    nodes: list[dict[str, Any]],
    seen_node_ids: set[str],
) -> None:
    """Append the canonical node for a SCIP symbol record."""
    node_id = record["node_id"]
    if node_id in seen_node_ids:
        return
    raw = record["raw"]
    symbol_id = record["symbol_id"]
    doc_path = record["doc_path"]
    kind = _coerce_str(raw.get("kind"), "unknown")
    display_name = _coerce_str(raw.get("display_name"), "")
    documentation = raw.get("documentation", [])
    description = ""
    if isinstance(documentation, list) and documentation:
        first = documentation[0]
        if isinstance(first, str):
            description = first
    occurrences = raw.get("occurrences", [])
    sourceline = _first_occurrence_line(occurrences)
    suffix = symbol_id.split("#")[-1] if "#" in symbol_id else symbol_id
    label = display_name or suffix or symbol_id
    seen_node_ids.add(node_id)  # label uses display_name or suffix (never empty for valid symbols)
    nodes.append(
        {
            "id": node_id,
            "label": label,
            "file_type": _scip_kind_to_file_type(kind),
            "source_file": doc_path,
            "source_location": f"L{sourceline}" if sourceline else "",
            "metadata": sanitize_metadata(_build_scip_metadata(symbol_id, kind, description)),
        }
    )


def _emit_relationships(
    record: dict[str, Any],
    per_doc_index: dict[tuple[str, str], str],
    global_index: dict[str, list[str]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    seen_node_ids: set[str],
    seen_edges: set[tuple[str, str, str, str | None]],
) -> None:
    """Append edges (and stub nodes when needed) for a symbol's relationships.

    Relationship target resolution order:
      1. Same-document `(target_symbol, doc_path)` — duplicate local symbol
         names across files route to THIS file's symbol, not another's.
      2. Unique cross-document match — when the symbol exists in exactly
         one document and that document is different from the source.
      3. Stub external node — for symbols not declared in any document
         OR ambiguous duplicates across multiple documents (refusing to
         guess silently).
    """
    raw = record["raw"]
    source_node_id = record["node_id"]
    doc_path = record["doc_path"]
    occurrences = raw.get("occurrences", [])
    sourceline = _first_occurrence_line(occurrences)
    relationships = raw.get("relationships")
    if not isinstance(relationships, list):
        return
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        target_symbol = _coerce_str(rel.get("symbol"), "")
        if not target_symbol:
            continue
        target_node_id = _resolve_relationship_target(
            target_symbol,
            doc_path,
            per_doc_index,
            global_index,
        )
        if target_node_id is None:
            # External relationship target: emit a stub node so the edge
            # is never dangling. The stub uses the source document's path
            # as its host context.
            target_node_id = _make_scip_node_id(target_symbol, doc_path)
            if target_node_id not in seen_node_ids:
                seen_node_ids.add(target_node_id)
                suffix = target_symbol.split("#")[-1] if "#" in target_symbol else target_symbol
                nodes.append(
                    {
                        "id": target_node_id,
                        "label": suffix or target_symbol,
                        "file_type": "code",
                        "source_file": doc_path,
                        "source_location": "",
                        "metadata": sanitize_metadata(
                            _build_scip_metadata(target_symbol, "external", "")
                        ),
                    }
                )
        relation = _scip_relation_for(rel)
        source_location = f"L{sourceline}" if sourceline else ""
        key = (source_node_id, target_node_id, relation, source_location)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(
            {
                "source": source_node_id,
                "target": target_node_id,
                "relation": relation,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": doc_path,
                "source_location": source_location,
                "weight": 1.0,
                "context": "scip",
                "metadata": sanitize_metadata({"scip_relationship": rel}),
            }
        )


def _resolve_relationship_target(
    target_symbol: str,
    source_doc_path: str,
    per_doc_index: dict[tuple[str, str], str],
    global_index: dict[str, list[str]],
) -> str | None:
    """Resolve a SCIP relationship target to an emitted node id, or None.

    Resolution order:
      1. Same-document match — `(target_symbol, source_doc_path)`.
      2. Unique cross-document match — exactly one node id in the global
         index for this symbol AND it isn't the same document we already
         tried.
      3. None — symbol is either absent globally OR ambiguous (defined in
         multiple documents). The caller emits a stub external node.
    """
    same_doc = per_doc_index.get((target_symbol, source_doc_path))
    if same_doc is not None:
        return same_doc
    candidates = global_index.get(target_symbol, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def _is_true(value: object) -> bool:
    """Return True only when value is exactly the boolean True.

    Used for SCIP relationship flags. Truthy strings like ``"false"`` are
    common in untrusted external JSON and must NOT count as a set flag.
    """
    return value is True


def _scip_relation_for(rel: dict[str, Any]) -> str:
    """Pick the Graphify relation tag for a SCIP relationship dict.

    Flags are accepted only when the value is exactly ``True`` — protects
    against truthy-but-misleading values like ``"false"`` in external JSON.
    """
    if _is_true(rel.get("is_implementation")):
        return "scip_impl"
    if _is_true(rel.get("is_type_definition")):
        return "scip_typed"
    if _is_true(rel.get("is_definition")):
        return "scip_def"
    return "scip_ref"


def _first_occurrence_line(occurrences: object) -> int:
    """Read the 1-based line number from the first occurrence range, defensively.

    Note: ``bool`` is a subclass of ``int`` in Python — ``isinstance(True, int)``
    is True. We explicitly exclude booleans so a malformed ``range: [True, …]``
    cannot produce ``source_location = "LTrue"``.
    """
    if not isinstance(occurrences, list) or not occurrences:
        return 0
    first = occurrences[0]
    if not isinstance(first, dict):
        return 0
    rng = first.get("range", [])
    if not isinstance(rng, list) or len(rng) < 1:
        return 0
    line = rng[0]
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        return 0
    return line


def _coerce_str(value: object, default: str) -> str:
    """Return ``value`` if it is a string, else the ``default`` (also a string)."""
    if isinstance(value, str):
        return value
    if isinstance(default, str):
        return default
    return ""


def _make_scip_node_id(symbol: str, source_file: str) -> str:
    """Derive a stable Graphify node ID from a SCIP symbol identifier.

    Uses SHA-1 truncated to 12 hex chars (48 bits). This is an identifier,
    not a security boundary — collision risk is acceptable at this scale
    given the per-document scoping prefix.
    """
    raw = f"{source_file}:{symbol}"
    h = hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    parts = symbol.split("#")
    suffix = parts[-1] if parts else symbol
    suffix = re.sub(r"[^a-zA-Z0-9_]", "_", suffix).strip("_").lower()
    if suffix:
        return f"scip_{suffix}_{h}"
    return f"scip_{h}"


def _scip_kind_to_file_type(kind: str) -> str:
    """Map SCIP symbol kind to a Graphify file_type."""
    # All SCIP symbols are code entities (functions, methods, classes, …);
    # the `kind` is preserved in metadata for downstream consumers.
    _ = kind  # acknowledged but not currently used for file_type routing
    return "code"


def _build_scip_metadata(symbol_id: str, kind: str, description: str) -> dict[str, str]:
    """Build metadata for a SCIP node."""
    meta: dict[str, str] = {
        "scip_symbol": symbol_id,
        "scip_kind": kind,
    }
    if description:
        meta["scip_description"] = description
    return meta
