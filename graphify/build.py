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
import networkx as nx
from .ids import make_id, normalize_id as _normalize_id
from .paths import default_graph_json as _default_graph_json
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


# Hyperedge member lists are canonically keyed `nodes` (see graphify/llm.py
# extraction spec), but LLM/subagent drift and externally-supplied graph.json
# sometimes emit `members` or `node_ids`. _normalize_hyperedge_members folds
# those aliases into `nodes` at ingest so every downstream consumer reads one
# canonical key — mirroring the `from`/`to` edge-endpoint tolerance below.
_HE_MEMBER_ALIASES = ("members", "node_ids")


def _normalize_hyperedge_members(he: object) -> None:
    """Canonicalize a hyperedge's member list onto the `nodes` key, in place.

    If `nodes` is already a list it wins (canonical), and only stray alias keys
    are dropped. Otherwise the first alias (`members`, then `node_ids`) that is a
    list is moved to `nodes`, deduped preserving order, with a single stderr
    WARNING naming the hyperedge id and alias used. Leftover alias keys are
    always removed so downstream code never re-reads them.
    """
    if not isinstance(he, dict):
        return
    if not isinstance(he.get("nodes"), list):
        for alias in _HE_MEMBER_ALIASES:
            val = he.get(alias)
            if isinstance(val, list):
                seen: set = set()
                deduped: list = []
                for ref in val:
                    try:
                        is_dupe = ref in seen
                    except TypeError:
                        is_dupe = False  # unhashable ref: keep it, validator flags it
                    if is_dupe:
                        continue
                    try:
                        seen.add(ref)
                    except TypeError:
                        pass
                    deduped.append(ref)
                he["nodes"] = deduped
                print(
                    f"[graphify] WARNING: hyperedge "
                    f"'{he.get('id', '?')}' uses field '{alias}' instead of "
                    f"'nodes'; normalizing.",
                    file=sys.stderr,
                )
                break
    # Drop any leftover alias keys regardless of which branch ran above.
    for alias in _HE_MEMBER_ALIASES:
        he.pop(alias, None)


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
            # Lexical relative_to failed. Retry with both sides fully resolved:
            # a symlinked scan root (macOS /var -> /private/var, or a symlinked
            # home/worktree) makes the raw prefixes differ even though they point
            # at the same dir, which otherwise silently defeats prune/replace
            # matching. Only the slow path resolves, so the common lexical match
            # stays filesystem-free.
            try:
                p = Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
            except (ValueError, OSError):
                pass
    return p


def _infer_merge_root(graph_path: Path) -> str | None:
    """Best-effort scan root for relativizing paths in build_merge when the caller
    passes no ``root`` (#1571).

    Prefers the committed ``graphify-out/.graphify_root`` marker — the authoritative
    scan root graphify records at build/watch time (#686/#1423) — then falls back to
    the directory that contains the output dir (``graph.json``'s grandparent, i.e.
    ``<root>/graphify-out/graph.json`` -> ``<root>``). Returns None if neither
    resolves, in which case normalization is a no-op (prior behavior).
    """
    try:
        marker = graph_path.parent / ".graphify_root"
        if marker.exists():
            recorded = marker.read_text(encoding="utf-8").strip()
            if recorded:
                return str(Path(recorded).resolve())
    except OSError:
        pass
    try:
        return str(graph_path.parent.parent.resolve())
    except Exception:
        return None


def edge_data(G: nx.Graph, u: str, v: str) -> dict:
    """Return one edge attribute dict for (u, v), tolerating MultiGraph.

    For MultiGraph/MultiDiGraph there can be multiple parallel edges;
    this returns the first one (sufficient for callers that only need
    relation/confidence for rendering). Fixes #796.
    """
    raw = G[u][v]
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        return next(iter(raw.values()), {})
    return raw


def edge_datas(G: nx.Graph, u: str, v: str) -> list[dict]:
    """Return every edge attribute dict for (u, v); always a list."""
    raw = G[u][v]
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        return list(raw.values())
    return [raw]


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

    The clustered build path runs edges through a NetworkX ``DiGraph``, which
    collapses parallel edges automatically. The ``--no-cluster`` and incremental
    ``update`` write paths bypass NetworkX and concatenate edge lists raw, so
    duplicates accumulate and edge counts become non-deterministic across build
    modes / repeated updates (#1317). Deduping on the connectivity identity is
    zero-signal-loss and restores idempotency. Callers that intentionally keep
    parallel edges (multigraph output) must not use this.
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


def _old_file_stems(rel: Path) -> list[str]:
    """Pre-migration stem forms a semantic fragment may have used for ``rel``.

    Ordered longest-first so prefix stripping is greedy and unambiguous:
      - one-parent form: ``parent.stem``  (the old _file_stem rule, #550-era)
      - zero-parent form: ``stem``        (the old llm.py prompt rule, #1509)
    """
    forms: list[str] = []
    parent = rel.parent.name
    if parent and parent not in (".", ""):
        forms.append(make_id(f"{parent}.{rel.stem}"))
    forms.append(make_id(rel.stem))
    # Dedupe while preserving order (top-level files collapse both forms).
    seen: set[str] = set()
    return [f for f in forms if f and not (f in seen or seen.add(f))]


def _semantic_id_remap(nodes: list, root: str | None) -> dict:
    """Re-derive non-AST node ids from ``source_file`` using the canonical
    full-path stem, so a cached/LLM fragment carrying a pre-migration short id
    reconciles with the AST node instead of spawning a ghost (#1504/#1509).

    Drift-proof by construction: the new id is computed from ``source_file`` in
    code, never trusted from the fragment's own ``id`` string. AST-origin nodes
    are skipped (they are already canonical via the extract() post-pass)."""
    from graphify.extractors.base import _file_stem  # local: avoid import cost at module load

    remap: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("_origin") == "ast":
            continue
        nid = node.get("id")
        sf = node.get("source_file")
        if not nid or not isinstance(nid, str) or not sf:
            continue
        sf_norm = _norm_source_file(str(sf), root) or str(sf)
        rel = Path(sf_norm)
        if rel.is_absolute():
            continue  # can't relativize (no/failed root) — leave id untouched
        new_stem = make_id(_file_stem(rel))
        if not new_stem:
            continue
        norm_nid = _normalize_id(nid)
        new_id: str | None = None
        for old_stem in _old_file_stems(rel):
            if old_stem == new_stem:
                continue  # already canonical for this form
            if norm_nid == old_stem:
                new_id = new_stem  # the file node itself
                break
            prefix = old_stem + "_"
            if norm_nid.startswith(prefix):
                entity = norm_nid[len(prefix):]
                new_id = make_id(new_stem, entity)
                break
        if new_id and new_id != nid:
            remap[nid] = new_id
    return remap


def graph_has_legacy_ids(nodes: list, root: str | Path | None = None, sample: int = 300) -> bool:
    """Whether a loaded graph still uses pre-#1504 node IDs (parent-dir / filename
    stem) rather than the full repo-relative path. Read-only consumers (query,
    serve) use this to nudge the user to rebuild, since they don't re-extract.

    Heuristic and cheap: only **file-level** nodes (source_location ``L1``) are
    inspected, because their ID is unambiguously the file stem. Symbol nodes are
    skipped — some extractors scope a symbol by package/directory (Go's
    ``_make_id(pkg_dir, name)`` → ``sub_thing``), which can coincide with an old
    file-stem form and would otherwise false-positive. Returns True as soon as one
    file node's ID matches an OLD stem form but not the canonical full-path form."""
    from graphify.extractors.base import _file_stem
    _r = str(root) if root is not None else None
    checked = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("source_location") or "") != "L1":
            continue  # only file-level nodes carry an unambiguous file-stem ID
        nid = node.get("id")
        sf = node.get("source_file")
        if not nid or not isinstance(nid, str) or not sf:
            continue
        rel = Path(_norm_source_file(str(sf), _r) or str(sf))
        if rel.is_absolute():
            continue
        new_stem = make_id(_file_stem(rel))
        if not new_stem:
            continue
        norm = _normalize_id(nid)
        if norm == new_stem or norm.startswith(new_stem + "_"):
            checked += 1
        else:
            for old in _old_file_stems(rel):
                if old != new_stem and (norm == old or norm.startswith(old + "_")):
                    return True
            checked += 1
        if checked >= sample:
            break
    return False


def build_from_json(extraction: dict, *, directed: bool = False, root: str | Path | None = None) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    root: if given, absolute source_file paths from semantic subagents are made
        relative to root so all nodes share a consistent path key (#932).
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

    # Canonicalize hyperedge member lists (#1561): producers sometimes key the
    # member list `members`/`node_ids` instead of `nodes`. Fold aliases onto
    # `nodes` here — BEFORE validation and the semantic-rekey loop below — so
    # every downstream consumer (rekey, source_file relativize, to_json) reads
    # one canonical key, the same way edge endpoints alias from/to at build.
    for he in extraction.get("hyperedges", []) or []:
        _normalize_hyperedge_members(he)

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    # Deterministic semantic re-key (#1504/#1509): the node-ID stem is now the
    # full repo-relative path (docs/v1/api/README.md -> docs_v1_api_readme), but
    # the semantic cache is UNVERSIONED, so a cached/LLM fragment can still carry
    # an OLD short id whose stem was just the immediate parent dir (api_readme),
    # or a prompt-drifting id with zero parent dirs (readme). Rather than trust
    # LLM prose to emit the right stem, we re-derive every non-AST node's id from
    # its own source_file in code, so a drifted fragment physically reconciles
    # with the AST node instead of spawning a ghost / a re-bill. AST-origin nodes
    # already carry canonical ids (the extract() id-remap post-pass guarantees it)
    # and are left untouched.
    _rekey: dict[str, str] = _semantic_id_remap(extraction.get("nodes", []), _root)
    if _rekey:
        for node in extraction.get("nodes", []):
            if isinstance(node, dict) and node.get("id") in _rekey:
                node["id"] = _rekey[node["id"]]
        for edge in extraction.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("source") in _rekey:
                edge["source"] = _rekey[edge["source"]]
            if edge.get("target") in _rekey:
                edge["target"] = _rekey[edge["target"]]
        for he in extraction.get("hyperedges", []) or []:
            if isinstance(he, dict) and isinstance(he.get("nodes"), list):
                he["nodes"] = [_rekey.get(n, n) for n in he["nodes"]]

    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        # Skip dict nodes with a missing or non-hashable id (e.g. a list emitted
        # by a buggy LLM extraction) so NetworkX add_node never raises
        # TypeError: unhashable type. Non-dict nodes are deliberately left to
        # raise as before, so callers that probe build for shape errors (e.g.
        # the multigraph diagnostic) still observe the malformed shape.
        if isinstance(node, dict):
            if "id" not in node:
                continue
            try:
                hash(node["id"])
            except TypeError:
                print(
                    f"[graphify] WARNING: skipping node with non-hashable id "
                    f"{node['id']!r} (must be a string).",
                    file=sys.stderr,
                )
                continue
            if "source_file" in node:
                node["source_file"] = _norm_source_file(node["source_file"], _root)
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())

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
        attrs = G.nodes[nid]
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
                if key in _loc_nodes and G.nodes[_loc_nodes[key]].get("_origin") == "ast":
                    _loc_collisions.add(key)
                # AST-origin nodes always overwrite a prior non-AST entry.
                _loc_nodes[key] = nid
            elif key not in _loc_nodes:
                _loc_nodes[key] = nid

    # Pass 2: find ghosts — non-AST nodes that have an AST canonical twin.
    for nid in node_set:
        attrs = G.nodes[nid]
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
    # Remove ghost nodes from the graph; edges will be re-pointed via norm_to_id.
    for ghost_id in _ghost_remap:
        G.remove_node(ghost_id)
        node_set.discard(ghost_id)

    # Normalized ID map: lets edges survive when the LLM generates IDs with
    # slightly different casing or punctuation than the AST extractor.
    # e.g. "Session_ValidateToken" maps to "session_validatetoken".
    norm_to_id: dict[str, str] = {_normalize_id(nid): nid for nid in node_set}
    # Also map ghost IDs to their canonical AST replacements.
    for ghost_id, canonical_id in _ghost_remap.items():
        norm_to_id[_normalize_id(ghost_id)] = canonical_id
        norm_to_id[ghost_id] = canonical_id
    # Pre-migration alias index (#1504): register each canonical node's OLD-stem id
    # forms as aliases so a stale-id edge endpoint coming from an un-re-keyed
    # fragment (e.g. an incremental update whose fragment references a symbol in a
    # file that was NOT re-extracted) still resolves to the migrated node instead
    # of dangling. Only fills gaps — never overrides a real node id.
    from graphify.extractors.base import _file_stem as _fs
    for nid in node_set:
        attrs = G.nodes[nid]
        sf = attrs.get("source_file")
        if not sf:
            continue
        rel = Path(str(sf))
        if rel.is_absolute():
            continue
        new_stem = make_id(_fs(rel))
        suffix = ""
        if _normalize_id(nid).startswith(new_stem):
            suffix = _normalize_id(nid)[len(new_stem):]  # leading "_entity" or ""
        for old_stem in _old_file_stems(rel):
            if old_stem == new_stem:
                continue
            alias = old_stem + suffix
            norm_to_id.setdefault(_normalize_id(alias), nid)
            norm_to_id.setdefault(alias, nid)
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
        # Skip edges with non-hashable endpoints (e.g. a list emitted by a buggy
        # LLM extraction) so the `not in node_set` membership test below never
        # raises TypeError: unhashable type. The validator already reported these.
        try:
            hash(src)
            hash(tgt)
        except TypeError:
            print(
                f"[graphify] WARNING: skipping edge with non-hashable endpoint "
                f"(source={src!r}, target={tgt!r}).",
                file=sys.stderr,
            )
            continue
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
                G.nodes[src].get("source_file")
                or G.nodes[tgt].get("source_file")
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
                # C, C++, and ObjC interoperate within one compilation unit: a method
                # declared in a shared `.h` is defined/called from a `.c`/`.cpp`/`.m`
                # sibling, so a cross-file INFERRED call from impl to its header decl
                # is legitimate, not a phantom name-collision across languages. Treat
                # the whole C family as one so the receiver-typed C++/ObjC member-call
                # resolvers' header-targeting edges survive build (#1547/#1556).
                ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c", ".hpp": "c",
                ".cxx": "c", ".hh": "c", ".hxx": "c",
                ".cu": "c", ".cuh": "c", ".metal": "c", ".m": "c", ".mm": "c",
                ".rb": "rb", ".php": "php", ".cs": "cs", ".swift": "swift", ".lua": "lua",
            }
            src_ext = Path(G.nodes[src].get("source_file") or "").suffix.lower()
            tgt_ext = Path(G.nodes[tgt].get("source_file") or "").suffix.lower()
            if src_ext and tgt_ext and _LANG_FAMILY.get(src_ext) != _LANG_FAMILY.get(tgt_ext):
                continue
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        # When the graph is undirected and the same node pair appears twice with
        # the same relation but opposite directions (e.g. a `calls` b and b `calls` a),
        # nx.Graph collapses them into one edge. The deterministic sort above means
        # the lexicographically-later direction would systematically overwrite the
        # earlier one's _src/_tgt, silently flipping the surviving edge's caller
        # and callee. First-seen direction wins instead — drop the redundant
        # reverse-direction duplicate so the original direction is preserved (#1061).
        if not G.is_directed() and G.has_edge(src, tgt):
            existing = edge_data(G, src, tgt)
            if existing.get("relation") == attrs.get("relation") and (
                existing.get("_src") == tgt and existing.get("_tgt") == src
            ):
                continue
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        # Relativize hyperedge source_file the same way nodes and edges are
        # (above), so to_json — which has no root and writes G.graph["hyperedges"]
        # verbatim — never leaks an absolute path from a semantic subagent (#1418).
        for he in hyperedges:
            if isinstance(he, dict) and he.get("source_file"):
                he["source_file"] = _norm_source_file(he["source_file"], _root)
        G.graph["hyperedges"] = hyperedges
    return G


def build(
    extractions: list[dict],
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
) -> nx.Graph:
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
    from graphify.dedup import deduplicate_entities
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    if dedup and combined["nodes"]:
        combined["nodes"], combined["edges"] = deduplicate_entities(
            combined["nodes"], combined["edges"], communities={},
            dedup_llm_backend=dedup_llm_backend,
        )
    return build_from_json(combined, directed=directed, root=root)


def _norm_label(label: str | None) -> str:
    """Canonical dedup key — Unicode-aware, preserves CJK/word characters."""
    if not isinstance(label, str):
        label = "" if label is None else str(label)
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_ ]+", " ", label.casefold(), flags=re.UNICODE).strip()


def deduplicate_by_label(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge nodes that share a normalised label, rewriting edge references.

    Prefers IDs without chunk suffixes (_c\\d+) and shorter IDs when tied.
    Drops self-loops created by the merge.

    Dormant: this is NOT wired into ``build()`` — the active dedup path is
    ``deduplicate_entities`` (imported and called in ``build``), which supersedes
    it. The previous "Called in build() automatically" note was never true. It
    also merges by label alone with no ``file_type`` guard, so it must not be
    enabled for code nodes: same-label symbols from different files/packages
    (e.g. two ``Account`` types) would collapse into one — the cross-file
    conflation ``deduplicate_entities`` deliberately avoids for code (#1205).
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
    graph_path: str | Path | None = None,
    prune_sources: list[str] | None = None,
    *,
    directed: bool = False,
    dedup: bool = True,
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
) -> nx.Graph:
    """Load existing graph.json, merge new chunks into it, and save back.

    Re-extracted files REPLACE their prior contribution: any source_file present
    in new_chunks is dropped from the loaded graph before merging, so a changed
    file's stale nodes/edges don't accumulate. Files absent from new_chunks are
    preserved unchanged; deleted files are removed via prune_sources.
    Safe to call repeatedly.
    root: if given, absolute source_file paths in new_chunks are made relative (#932).
    """
    graph_path = Path(graph_path if graph_path is not None else _default_graph_json())
    if graph_path.exists():
        # Read JSON directly instead of going through node_link_graph().
        # The latter rebuilds an undirected nx.Graph and then enumerating
        # edges() yields endpoints based on node insertion order, which
        # silently flips directional edges (e.g. `calls`) when the callee
        # was inserted before the caller. The _src/_tgt direction-preserving
        # attrs are popped before saving in export.py, so going through the
        # NetworkX round-trip loses direction permanently (#760).
        from graphify.security import check_graph_file_size_cap
        check_graph_file_size_cap(graph_path)
        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(
                f"Cannot read {graph_path} for incremental merge: {exc}. "
                "Delete the file and run a full rebuild."
            ) from exc
        links_key = "links" if "links" in data else "edges"
        existing_nodes = list(data.get("nodes", []))
        existing_edges = list(data.get(links_key, []))
        existing_hyperedges = list(data.get("hyperedges", []))
        had_graph = True
    else:
        existing_nodes = []
        existing_edges = []
        existing_hyperedges = []
        had_graph = False

    # Effective root for relativizing absolute source_file / prune paths back to the
    # stored relative source_file keys. When the caller passes root we use it;
    # otherwise fall back to the graph's recorded scan root, so absolute
    # prune_sources and new-chunk paths still match even when a caller omits root
    # (#1571 — the skill's --update runbook calls build_merge without root, so
    # absolute deleted-file paths never matched the relative node keys and their
    # nodes survived as ghosts).
    _eff_root = (
        str(Path(root).resolve()) if root is not None
        else _infer_merge_root(graph_path)
    )

    # Re-extracted files REPLACE their prior contribution. Every source_file
    # present in new_chunks is dropped from the loaded base before merging, so a
    # CHANGED file's stale nodes/edges don't accumulate across incremental
    # updates. Without this, build() merges old+new for the same file and only
    # exact-duplicate edges collapse — edges/nodes that disappeared from the new
    # version survive forever. Brand-new files aren't in base, so this is a no-op
    # for them; genuinely deleted files are still handled via prune_sources.
    # Matched in both raw and _norm_source_file form because new_chunks may carry
    # absolute win32 paths while the stored graph keeps relative posix (#1007).
    _replace_root = _eff_root
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
    G = build(all_chunks, directed=directed, dedup=dedup, dedup_llm_backend=dedup_llm_backend, root=root)

    # Prune set for deleted source files — both the raw form (matches nodes that
    # kept absolute source_file) and the normalised relative form (matches nodes
    # relativised by _norm_source_file at build time). .resolve() (via _eff_root)
    # handles symlinked roots and ".." / "./" segments so Path.relative_to()
    # succeeds even when the scan root is a symlink. (#1007, #1571)
    prune_set: set[str] = set()
    for p in (prune_sources or []):
        if not p:
            continue
        prune_set.add(p)
        norm = _norm_source_file(p, _eff_root)
        if norm:
            prune_set.add(norm)

    # Carry forward hyperedges from files that were neither re-extracted nor
    # deleted (#1574). build() only sees the new chunks' hyperedges, so without
    # this every --update collapses the graph's hyperedge set down to just the
    # changed files'. Re-extracted files' prior hyperedges are dropped (their new
    # version is already in G — replace-per-source, like nodes/edges); deleted
    # files' are dropped via prune_set. id-dedup (attach_hyperedges) so a carried
    # hyperedge never duplicates one the new chunks re-emitted. Mirrors watch.py,
    # which already preserves existing hyperedges across a rebuild.
    if existing_hyperedges:
        carried = []
        for he in existing_hyperedges:
            if not isinstance(he, dict):
                continue
            sf = he.get("source_file")
            norm = _norm_source_file(sf, _eff_root)
            if sf in new_sources or norm in new_sources:
                continue  # re-extracted — replaced by the new chunk's version
            if sf in prune_set or norm in prune_set:
                continue  # deleted — pruned
            carried.append(he)
        if carried:
            from graphify.export import attach_hyperedges
            attach_hyperedges(G, carried)

    # Prune nodes and edges from deleted source files
    if prune_sources:
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
    if graph_path.exists() and not dedup and not prune_sources:
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )

    return G


def prefix_graph_for_global(G: nx.Graph, repo_tag: str) -> nx.Graph:
    """Return a copy of G with all node IDs prefixed with repo_tag::.

    Labels are preserved unchanged (for display). A 'local_id' attribute
    is added to each node so the original ID can be recovered. Edges are
    rewritten to match the new prefixed IDs. The 'repo' attribute is set
    on every node.
    """
    relabel = {n: f"{repo_tag}::{n}" for n in G.nodes}
    H = nx.relabel_nodes(G, relabel, copy=True)
    for node, data in H.nodes(data=True):
        data["repo"] = repo_tag
        data.setdefault("local_id", node.split("::", 1)[1])
    return H


def prune_repo_from_graph(G: nx.Graph, repo_tag: str) -> int:
    """Remove all nodes tagged with repo_tag from G in-place. Returns count removed."""
    to_remove = [n for n, d in G.nodes(data=True) if d.get("repo") == repo_tag]
    G.remove_nodes_from(to_remove)
    return len(to_remove)
