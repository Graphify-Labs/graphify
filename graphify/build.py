# assemble node+edge dicts into a NetworkX graph, preserving edge direction
#
# Node deduplication — three layers:
#
# 1. Within a file (AST): each extractor tracks a `seen_ids` set. A node ID is
#    emitted at most once per file, so duplicate class/function definitions in
#    the same source file are collapsed to the first occurrence.
#
# 2. Between files (build): NetworkX G.add_node() is idempotent — calling it
#    twice with the same ID overwrites the attributes with the second call's
#    values. Nodes are added in extraction order (AST first, then semantic),
#    so if the same entity is extracted by both passes the semantic node
#    silently overwrites the AST node. This is intentional: semantic nodes
#    carry richer labels and cross-file context, while AST nodes have precise
#    source_location. If you need to change the priority, reorder extractions
#    passed to build().
#
# 3. Semantic merge (skill): before calling build(), the skill merges cached
#    and new semantic results using an explicit `seen` set keyed on node["id"],
#    so duplicates across cache hits and new extractions are resolved there
#    before any graph construction happens.
#
from __future__ import annotations
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from .store import GraphStore, DEFAULT_URI, graph_name_for
from .validate import validate_extraction


# Synonym mapper for known invalid file_type values that LLM subagents commonly
# emit. Keeps semantic intent close (markdown→document, tool→code) and falls
# back to "concept" for any other invalid value (see #840).
_FILE_TYPE_SYNONYMS = {
    "markdown": "document",
    "text": "document",
    "tool": "code",
    "library": "code",
    "pattern": "concept",
    "principle": "concept",
    "constraint": "concept",
    "tech": "concept",
    "technology": "concept",
    "data-source": "concept",
    "data_source": "concept",
    "gotcha": "concept",
    "framework": "concept",
}


def _search_norm_label(label: str) -> str:
    """Diacritic-stripped, lowercased label for in-engine search prefiltering.
    Must match serve._strip_diacritics(label).lower() so Cypher CONTAINS prefilters
    agree with the Python scoring tiers."""
    nfkd = unicodedata.normalize("NFKD", label or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _normalize_id(s: str) -> str:
    r"""Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor. Must stay in sync
    with extract._make_id — NFKC normalization, \w with re.UNICODE, underscore
    collapse, and casefold must all match (#811).
    """
    s = unicodedata.normalize("NFKC", s)
    cleaned = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").casefold()


def _norm_source_file(p: str | None, root: str | None = None) -> str | None:
    """Normalize path separators and relativize absolute paths.

    Converts backslashes to forward slashes (Windows compatibility) and, when
    root is provided, strips the absolute prefix from paths produced by semantic
    subagents so source_file is always repo-relative (fixes #932).
    """
    if not p:
        return p
    p = p.replace("\\", "/")
    if root and os.path.isabs(p):
        try:
            p = Path(p).relative_to(root).as_posix()
        except ValueError:
            pass
    return p


def edge_data(G, u: str, v: str) -> dict:
    """Return one edge attribute dict for (u, v).

    FalkorDB stores parallel edges natively; ``G[u][v]`` returns the first
    edge's attributes, which is sufficient for callers that only need
    relation/confidence for rendering. Fixes #796.
    """
    return G[u][v]


def edge_datas(G, u: str, v: str) -> list[dict]:
    """Return edge attribute dict(s) for (u, v); always a list."""
    return [G[u][v]]


def dedupe_nodes(nodes: list[dict]) -> list[dict]:
    """Collapse nodes sharing an ``id``, last-writer-wins on attributes.

    Mirrors what ``build_from_json``'s ``G.add_node`` does implicitly (idempotent;
    a later node overwrites an earlier one's attributes). The ``--no-cluster``
    write path dumps the raw node list without building a graph, so same-id nodes
    — e.g. a Swift ``type=module`` anchor emitted once per importing file (#1327)
    — would otherwise appear as duplicates. Insertion order follows each id's
    first appearance; the retained dict is the last one seen.
    """
    by_id: dict = {}
    for n in nodes:
        nid = n.get("id")
        if nid is None:
            continue
        by_id[nid] = n
    return list(by_id.values())


def dedupe_edges(edges: list[dict]) -> list[dict]:
    """Collapse exact parallel edges by ``(source, target, relation)``, keeping the
    first occurrence.

    The clustered build path runs edges through the GraphStore dedup (collapses
    parallel edges). The ``--no-cluster`` and incremental ``update`` write paths
    concatenate edge lists raw, so duplicates accumulate and edge counts become
    non-deterministic across build modes / repeated updates (#1317). Deduping on
    the connectivity identity is zero-signal-loss and restores idempotency.
    Callers that intentionally keep parallel edges (multigraph output) must not
    use this.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in edges:
        key = (e.get("source"), e.get("target"), e.get("relation"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def build_from_json(
    extraction: dict,
    *,
    directed: bool = False,
    root: str | Path | None = None,
    store: GraphStore | None = None,
    graph_name: str = "graphify",
    uri: str = DEFAULT_URI,
) -> GraphStore:
    """Build a FalkorDB-backed graph (GraphStore) from an extraction dict.

    Edges are always stored in their native source→target orientation. When
    ``directed`` is False (default) a reverse-direction duplicate of the same
    node pair + relation is collapsed to the first-seen edge, matching the old
    undirected nx.Graph semantics; when True both directions are kept.
    root: if given, absolute source_file paths from semantic subagents are made
        relative to root so all nodes share a consistent path key (#932).
    store: build into this GraphStore (cleared first); otherwise a new one is
        created for ``graph_name`` at ``uri``.
    """
    _root = str(Path(root).resolve()) if root else None
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    # Canonicalize legacy node/edge schema before validation.
    for node in extraction.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if "source" in node and "source_file" not in node:
            # Count edges that reference this node so the warning is actionable (#479)
            node_id = node.get("id", "?")
            affected_edges = sum(
                1 for e in extraction.get("edges", [])
                if e.get("source") == node_id or e.get("target") == node_id
            )
            print(
                f"[graphify] WARNING: node '{node_id}' uses field 'source' instead of "
                f"'source_file' — {affected_edges} edge(s) may be misrouted. "
                f"Rename the field to 'source_file' to silence this warning.",
                file=sys.stderr,
            )
            node["source_file"] = node.pop("source")
        # Default missing/None file_type to "concept" so legacy graph.json
        # entries (and stub nodes preserved by `_rebuild_code` from older
        # graphify versions that didn't always populate file_type) don't
        # trigger spurious "invalid file_type 'None'" validator warnings (#660).
        if node.get("file_type") in (None, ""):
            node["file_type"] = "concept"
        ft = node.get("file_type", "")
        if ft and ft not in {"code", "document", "paper", "image", "rationale", "concept"}:
            node["file_type"] = _FILE_TYPE_SYNONYMS.get(ft, "concept")

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    # Collect node attributes in extraction order (last write wins per id), the
    # same idempotent-overwrite semantics nx.add_node had.
    node_attrs: dict[str, dict] = {}
    node_order: list[str] = []
    for node in extraction.get("nodes", []):
        if "source_file" in node:
            node["source_file"] = _norm_source_file(node["source_file"], _root)
        nid = node["id"]
        if nid not in node_attrs:
            node_order.append(nid)
        attrs = {k: v for k, v in node.items() if k != "id"}
        # Stored searchable label so query/explain can prefilter candidates in
        # the engine (Cypher CONTAINS) instead of scanning every node in Python.
        attrs["norm_label"] = _search_norm_label(str(attrs.get("label", "")))
        node_attrs[nid] = attrs
    node_set = set(node_attrs)

    # #1145 (extended): merge LLM ghost-duplicate nodes into AST canonical nodes.
    # Original bug: AST uses parent-qualified IDs (mingpt_bpe_get_pairs) while LLM
    # uses bare-stem IDs (bpe_get_pairs) — different IDs, same symbol.
    # Original fix only caught LLM nodes with source_location=None; LLM now
    # populates source_location, so those ghosts survived. Extended fix: use
    # _origin=="ast" as the canonical signal. AST nodes always win; any non-AST
    # node sharing (basename, label) with an AST node is a ghost.
    _loc_nodes: dict[tuple[str, str], str] = {}   # (basename, label) -> canonical node id
    _loc_collisions: set[tuple[str, str]] = set()  # keys shared by 2+ AST nodes
    _noloc_nodes: dict[tuple[str, str], str] = {}  # (basename, label) -> ghost node id

    # Pass 1: collect canonical nodes — AST-origin nodes take precedence over LLM nodes.
    # When 2+ AST nodes share a key (same-named symbols in same-named files across
    # directories, e.g. render in two index.ts), the key is ambiguous: merging a
    # ghost would pick an arbitrary winner via set-iteration order (#1257). Track
    # those keys so Pass 2 skips them — same conservatism as
    # _rewire_unique_stub_nodes, which only merges when exactly one real def exists.
    for nid in node_set:
        attrs = node_attrs[nid]
        label = str(attrs.get("label", "")).strip()
        sf = str(attrs.get("source_file", ""))
        basename = Path(sf).name if sf else ""
        if not label or not basename:
            continue
        is_ast = attrs.get("_origin") == "ast"
        if attrs.get("source_location") or is_ast:
            key = (basename, label)
            if is_ast:
                # Two AST nodes on the same key is an ambiguous collision.
                if key in _loc_nodes and node_attrs[_loc_nodes[key]].get("_origin") == "ast":
                    _loc_collisions.add(key)
                # AST-origin nodes always overwrite a prior non-AST entry.
                _loc_nodes[key] = nid
            elif key not in _loc_nodes:
                _loc_nodes[key] = nid

    # Pass 2: find ghosts — non-AST nodes that have an AST canonical twin.
    for nid in node_set:
        attrs = node_attrs[nid]
        if attrs.get("_origin") == "ast":
            continue  # AST nodes are never ghosts
        label = str(attrs.get("label", "")).strip()
        sf = str(attrs.get("source_file", ""))
        basename = Path(sf).name if sf else ""
        if not label or not basename:
            continue
        key = (basename, label)
        if key in _loc_collisions:
            continue  # ambiguous key: no safe canonical winner, leave ghost intact
        if key in _loc_nodes and _loc_nodes[key] != nid:
            _noloc_nodes[key] = nid
    # For every ghost that has an AST counterpart, record a remap.
    _ghost_remap: dict[str, str] = {}  # ghost_id -> canonical_id
    for key, sem_id in _noloc_nodes.items():
        ast_id = _loc_nodes.get(key)
        if ast_id is not None:
            _ghost_remap[sem_id] = ast_id
    # Remove ghost nodes; edges will be re-pointed via norm_to_id.
    for ghost_id in _ghost_remap:
        node_attrs.pop(ghost_id, None)
        node_set.discard(ghost_id)

    # Normalized ID map: lets edges survive when the LLM generates IDs with
    # slightly different casing or punctuation than the AST extractor.
    # e.g. "Session_ValidateToken" maps to "session_validatetoken".
    norm_to_id: dict[str, str] = {_normalize_id(nid): nid for nid in node_set}
    # Also map ghost IDs to their canonical AST replacements.
    for ghost_id, canonical_id in _ghost_remap.items():
        norm_to_id[_normalize_id(ghost_id)] = canonical_id
        norm_to_id[ghost_id] = canonical_id
    edge_items: list[tuple[str, str, dict]] = []
    seen_exact: set[tuple] = set()  # (src, tgt, relation) — collapse exact directed dups
    seen_pairs: dict[tuple, tuple[str, str]] = {}  # (unordered pair, relation) -> first src/tgt
    # Iterate edges in a deterministic order. The graph is undirected and stores
    # direction in _src/_tgt; when two edges collapse onto the same node pair the
    # last write wins, so an unstable iteration order flips _src/_tgt run-to-run
    # and makes the serialized graph churn. Sorting fixes the last-write outcome.
    for edge in sorted(
        extraction.get("edges", []),
        key=lambda e: (
            str(e.get("source", e.get("from", ""))),
            str(e.get("target", e.get("to", ""))),
            str(e.get("relation", "")),
        ),
    ):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        # Remap mismatched IDs via normalization before dropping the edge.
        if src not in node_set:
            src = norm_to_id.get(_normalize_id(src), src)
        if tgt not in node_set:
            tgt = norm_to_id.get(_normalize_id(tgt), tgt)
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        # Backfill source_file from the endpoint nodes (every node carries one).
        # Semantic/LLM edges occasionally omit it, which downstream validation
        # flags and leaves query results with no file reference (#1279).
        if not attrs.get("source_file"):
            attrs["source_file"] = (
                node_attrs[src].get("source_file")
                or node_attrs[tgt].get("source_file")
                or ""
            )
        if "source_file" in attrs:
            attrs["source_file"] = _norm_source_file(attrs["source_file"], _root)
        # Drop cross-language INFERRED `calls` edges — same short names (render,
        # parse, etc.) appear across language boundaries in multi-language chunks,
        # producing phantom edges that don't represent real call relationships.
        if attrs.get("relation") == "calls" and attrs.get("confidence") == "INFERRED":
            _LANG_FAMILY: dict[str, str] = {
                ".py": "py", ".pyi": "py",
                ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
                ".ts": "js", ".tsx": "js",
                ".go": "go", ".rs": "rs",
                ".java": "jvm", ".kt": "jvm", ".scala": "jvm", ".groovy": "jvm",
                ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
                ".rb": "rb", ".php": "php", ".cs": "cs", ".swift": "swift", ".lua": "lua",
            }
            src_ext = Path(node_attrs[src].get("source_file") or "").suffix.lower()
            tgt_ext = Path(node_attrs[tgt].get("source_file") or "").suffix.lower()
            if src_ext and tgt_ext and _LANG_FAMILY.get(src_ext) != _LANG_FAMILY.get(tgt_ext):
                continue
        # Edges are stored DIRECTED in their native source→target orientation, so
        # direction survives without the old _src/_tgt markers. When the graph is
        # undirected (default) and the same node pair appears again with the same
        # relation (in either direction), collapse to the first-seen edge so the
        # original direction wins, matching the old nx.Graph behaviour (#1061).
        # Collapse exact directed duplicates always (same as nx.DiGraph / the old
        # MERGE upsert) so the fresh CREATE path doesn't emit duplicate edges.
        exact_key = (src, tgt, attrs.get("relation"))
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)
        if not directed:
            pair_key = (frozenset((src, tgt)), attrs.get("relation"))
            if pair_key in seen_pairs:
                continue
            seen_pairs[pair_key] = (src, tgt)
        edge_items.append((src, tgt, attrs))

    if store is None:
        store = GraphStore(graph_name=graph_name, uri=uri, directed=True)
    store.clear()
    # Fresh build into a cleared graph: ids are unique and there are no existing
    # edges, so CREATE (no MERGE existence-check) is correct and much faster.
    store.add_nodes_from([(nid, node_attrs[nid]) for nid in node_order if nid in node_attrs], fresh=True)
    store.add_edges_from(edge_items, fresh=True)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        store.graph["hyperedges"] = hyperedges
        store.save_meta()
    # Warm + persist the hub-threshold (p99 degree) so query traversals don't
    # recompute it on every invocation.
    try:
        store._hub_threshold()
    except Exception:
        pass
    return store


def build(
    extractions: list[dict],
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
    store: GraphStore | None = None,
    graph_name: str = "graphify",
    uri: str = DEFAULT_URI,
) -> GraphStore:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    dedup=True (default) runs entity deduplication before building the graph.
    dedup_llm_backend: if set (e.g. "gemini", "claude", or "kimi"), uses LLM to resolve
        ambiguous pairs in the 75–92 Jaro-Winkler score zone.
    root: if given, absolute source_file paths are made relative to root (#932).

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    if dedup and combined["nodes"]:
        # Imported lazily so dedup=False callers don't require the datasketch dep.
        from graphify.dedup import deduplicate_entities

        combined["nodes"], combined["edges"] = deduplicate_entities(
            combined["nodes"], combined["edges"], communities={},
            dedup_llm_backend=dedup_llm_backend,
        )
    return build_from_json(
        combined, directed=directed, root=root, store=store, graph_name=graph_name, uri=uri
    )


def _norm_label(label: str | None) -> str:
    """Canonical dedup key — Unicode-aware, preserves CJK/word characters."""
    if not isinstance(label, str):
        label = "" if label is None else str(label)
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_ ]+", " ", label.casefold(), flags=re.UNICODE).strip()


def deduplicate_by_label(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge nodes that share a normalised label, rewriting edge references.

    Prefers IDs without chunk suffixes (_c\\d+) and shorter IDs when tied.
    Drops self-loops created by the merge. Called in build() automatically.
    """
    _CHUNK_SUFFIX = re.compile(r"_c\d+$")
    canonical: dict[str, dict] = {}  # norm_label -> surviving node
    remap: dict[str, str] = {}       # old_id -> surviving_id

    for node in nodes:
        key = _norm_label(node.get("label", node.get("id", "")))
        if not key:
            continue
        existing = canonical.get(key)
        if existing is None:
            canonical[key] = node
        else:
            has_suffix = bool(_CHUNK_SUFFIX.search(node["id"]))
            existing_has_suffix = bool(_CHUNK_SUFFIX.search(existing["id"]))
            if has_suffix and not existing_has_suffix:
                remap[node["id"]] = existing["id"]
            elif existing_has_suffix and not has_suffix:
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            elif len(node["id"]) < len(existing["id"]):
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            else:
                remap[node["id"]] = existing["id"]

    if not remap:
        return nodes, edges

    print(f"[graphify] Deduplicated {len(remap)} duplicate node(s) by label.", file=sys.stderr)
    deduped_nodes = list(canonical.values())
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] != e["target"]:
            deduped_edges.append(e)
    return deduped_nodes, deduped_edges


def build_merge(
    new_chunks: list[dict],
    graph_name: str = "graphify",
    prune_sources: list[str] | None = None,
    *,
    uri: str = DEFAULT_URI,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
) -> GraphStore:
    """Merge new chunks into the existing FalkorDB graph and persist.

    Re-extracted files REPLACE their prior contribution: any source_file present
    in new_chunks is dropped from the loaded graph before merging, so a changed
    file's stale nodes/edges don't accumulate. Files absent from new_chunks are
    preserved unchanged; deleted files are removed via prune_sources.
    Safe to call repeatedly.
    root: if given, absolute source_file paths in new_chunks are made relative (#932).
    """
    store = GraphStore(graph_name=graph_name, uri=uri, directed=True)
    # Pull the existing graph back out of FalkorDB as an extraction-shaped chunk.
    # Edges are stored in true direction, so (u, v) are the real source/target.
    existing_nodes = [dict(attrs, id=nid) for nid, attrs in store.nodes(data=True)]
    existing_edges = []
    for u, v, a in store.edges(data=True):
        e = {k: val for k, val in a.items()}
        e["source"], e["target"] = u, v
        existing_edges.append(e)
    had_graph = bool(existing_nodes)

    # Re-extracted files REPLACE their prior contribution (#1344/#1007). Every
    # source_file present in new_chunks is dropped from the loaded base before
    # merging, so a CHANGED file's stale nodes/edges don't accumulate across
    # incremental updates. Without this, build() merges old+new for the same file
    # and only exact-duplicate edges collapse — edges/nodes that disappeared from
    # the new version survive forever. Brand-new files aren't in base (no-op);
    # genuinely deleted files are still handled via prune_sources. Matched in both
    # raw and _norm_source_file form because new_chunks may carry absolute win32
    # paths while the stored graph keeps relative posix.
    _replace_root = str(Path(root).resolve()) if root is not None else None
    new_sources: set[str] = set()
    for ch in new_chunks:
        for n in ch.get("nodes", []):
            sf = n.get("source_file")
            if not sf:
                continue
            new_sources.add(sf)
            norm = _norm_source_file(sf, _replace_root)
            if norm:
                new_sources.add(norm)
    if new_sources:
        def _kept(item: dict) -> bool:
            sf = item.get("source_file")
            return sf not in new_sources and _norm_source_file(sf, _replace_root) not in new_sources
        existing_nodes = [n for n in existing_nodes if _kept(n)]
        existing_edges = [e for e in existing_edges if _kept(e)]

    base = [{"nodes": existing_nodes, "edges": existing_edges}] if had_graph else []

    all_chunks = base + list(new_chunks)
    G = build(
        all_chunks, directed=directed, dedup=dedup, dedup_llm_backend=dedup_llm_backend,
        root=root, store=store, graph_name=graph_name, uri=uri,
    )

    # Prune nodes and edges from deleted source files
    if prune_sources:
        # Build a set containing both the raw form (matches nodes that kept
        # absolute source_file) and the normalised relative form (matches nodes
        # that were relativised by _norm_source_file at build time).
        # .resolve() handles symlinked roots and redundant ".." / "./" segments
        # so Path.relative_to() succeeds even when the scan root is a symlink.
        # (#1007: manifest absolute paths vs graph relative source_file mismatch)
        _root_str = str(Path(root).resolve()) if root is not None else None
        prune_set: set[str] = set()
        for p in prune_sources:
            if not p:
                continue
            prune_set.add(p)
            norm = _norm_source_file(p, _root_str)
            if norm:
                prune_set.add(norm)
        to_remove = [
            n for n, d in G.nodes(data=True)
            if d.get("source_file") in prune_set
        ]
        G.remove_nodes_from(to_remove)
        n_files = len(prune_sources)
        n_nodes = len(to_remove)
        if n_nodes:
            print(
                f"[graphify] Pruned {n_nodes} node(s) from {n_files} deleted source file(s).",
                file=sys.stderr,
            )

        edges_to_remove = [
            (u, v) for u, v, d in G.edges(data=True)
            if d.get("source_file") in prune_set
        ]
        if edges_to_remove:
            G.remove_edges_from(edges_to_remove)
            print(
                f"[graphify] Pruned {len(edges_to_remove)} edge(s) from deleted source file(s).",
                file=sys.stderr,
            )

        if not n_nodes and not edges_to_remove:
            print(
                f"[graphify] {n_files} source file(s) deleted since last run — "
                f"no matching nodes or edges in graph, already clean.",
                file=sys.stderr,
            )

    # Safety check: refuse to shrink the graph silently (#479)
    # Skip when dedup or prune_sources is active — shrinkage is intentional there.
    if existing_nodes and not dedup and not prune_sources:
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )

    return G


def prefix_graph_for_global(G, repo_tag: str, target: GraphStore) -> GraphStore:
    """Copy G's nodes/edges into `target` with all node IDs prefixed repo_tag::.

    Labels are preserved unchanged (for display). A 'local_id' attribute is added
    so the original ID can be recovered, and 'repo' is set on every node. Edges
    are rewritten to the prefixed IDs.
    """
    def _pfx(n: str) -> str:
        return f"{repo_tag}::{n}"

    nodes = []
    for nid, data in G.nodes(data=True):
        attrs = dict(data)
        attrs["repo"] = repo_tag
        attrs.setdefault("local_id", nid)
        nodes.append((_pfx(nid), attrs))
    edges = [(_pfx(u), _pfx(v), dict(a)) for u, v, a in G.edges(data=True)]
    target.add_nodes_from(nodes)
    target.add_edges_from(edges)
    return target


def prune_repo_from_graph(G: GraphStore, repo_tag: str) -> int:
    """Remove all nodes tagged with repo_tag from G. Returns count removed."""
    return G.prune_repo(repo_tag)
