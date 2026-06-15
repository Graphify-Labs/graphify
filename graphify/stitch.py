"""Post-merge incremental stitch — wire changed-file subgraphs to the existing graph.

After incremental ``build_merge``, re-extracted files often contain mentions of
symbols and paths elsewhere in the corpus, but the LLM chunk lacked that context.
This module adds conservative ``references`` edges by scanning changed files on
disk and resolving mentions against the full merged graph.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import networkx as nx

from graphify.build import source_path_aliases
from graphify.symbol_resolution import existing_edge_pairs, normalise_callable_label

_BACKTICK = re.compile(r"`([^`]+)`")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_PATH_EXT = re.compile(
    r"\.(?:md|py|ts|tsx|js|jsx|java|go|rs|txt|rst|pdf)(?:$|[#?])",
    re.IGNORECASE,
)
_MIN_SYMBOL_LEN = 3


def _stitch_label_index(G: nx.Graph) -> dict[str, list[str]]:
    """Map normalised label -> node ids (code, document, and concept nodes)."""
    index: dict[str, list[str]] = {}
    for nid, data in G.nodes(data=True):
        if data.get("file_type") == "rationale":
            continue
        label = str(data.get("label", "")).strip().strip("()")
        if not label or len(label) < _MIN_SYMBOL_LEN:
            continue
        if label.endswith((".py", ".md", ".ts", ".tsx", ".js", ".jsx")):
            continue
        key = normalise_callable_label(label)
        if key:
            index.setdefault(key, []).append(nid)
    return index


def _nodes_for_source_file(G: nx.Graph, path: str, root: Path) -> list[str]:
    aliases = source_path_aliases(path, root)
    if not aliases:
        return []
    found: list[str] = []
    for nid, data in G.nodes(data=True):
        sf = data.get("source_file")
        if sf and source_path_aliases(str(sf), root) & aliases:
            found.append(nid)
    return found


def _source_file_matches_path(source_file: str | None, rel: Path, root: Path) -> bool:
    if not source_file:
        return False
    changed = source_path_aliases(rel.as_posix(), root)
    return bool(source_path_aliases(str(source_file), root) & changed)


def _is_foreign_attribution(source_file: str | None, rel: Path, root: Path) -> bool:
    """True when source_file points at a different existing file than *rel*."""
    if not source_file:
        return False
    if _source_file_matches_path(source_file, rel, root):
        return False
    disk = Path(source_file)
    if not disk.is_absolute():
        disk = root / disk
    return disk.is_file()


def _fallback_local_nodes(
    G: nx.Graph,
    new_ids: set[str],
    rel: Path,
    root: Path,
) -> list[str]:
    """Fresh extraction nodes for stitch anchors when source_file was wrong.

    Keeps nodes attributed to missing/hallucinated paths; drops nodes the LLM
    placed under a different on-disk file (e.g. calendar.md while stitching array.md).
    """
    kept: list[str] = []
    for nid in sorted(new_ids):
        if nid not in G:
            continue
        sf = G.nodes[nid].get("source_file")
        if _is_foreign_attribution(str(sf) if sf else None, rel, root):
            continue
        kept.append(nid)
    return kept


def _pick_path_target_anchor(node_ids: list[str], G: nx.Graph, rel_path: Path) -> str | None:
    """Pick a file-level target for a path mention; never an arbitrary code symbol."""
    if not node_ids:
        return None
    stem = rel_path.stem.lower().replace("_", " ")
    doc_nodes = [n for n in node_ids if n.endswith("_document")]
    if doc_nodes:
        return sorted(doc_nodes)[0]
    for nid in sorted(node_ids):
        data = G.nodes[nid]
        if data.get("file_type") not in ("document", "concept", "paper"):
            continue
        label = str(data.get("label", "")).lower().replace("_", " ")
        if stem in label or label in stem:
            return nid
    return None


def _pick_file_anchor(node_ids: list[str], G: nx.Graph, rel_path: Path) -> str | None:
    if not node_ids:
        return None
    stem = rel_path.stem.lower().replace("_", " ")
    doc_nodes = [n for n in node_ids if n.endswith("_document")]
    if doc_nodes:
        return sorted(doc_nodes)[0]
    for nid in node_ids:
        data = G.nodes[nid]
        ft = data.get("file_type")
        label = str(data.get("label", "")).lower().replace("_", " ")
        if ft in ("document", "concept", "paper") and stem in label:
            return nid
    return sorted(node_ids)[0]


def _looks_like_path(token: str) -> bool:
    token = token.strip()
    if "/" in token or "\\" in token:
        return True
    return bool(_PATH_EXT.search(token))


def _resolve_path_target(token: str, root: Path, G: nx.Graph) -> list[str]:
    token = token.strip().split("#")[0].split("?")[0]
    if not token:
        return []
    candidates = [token]
    if not Path(token).is_absolute():
        candidates.append(str(root / token))
    for cp in candidates:
        nids = _nodes_for_source_file(G, cp, root)
        if not nids:
            continue
        try:
            rel = (
                Path(cp).resolve().relative_to(root.resolve())
                if Path(cp).is_absolute()
                else Path(token)
            )
        except ValueError:
            rel = Path(token)
        anchor = _pick_path_target_anchor(nids, G, rel)
        return [anchor] if anchor else []
    return []


def _resolve_symbol_targets(
    token: str,
    label_index: dict[str, list[str]],
    local_ids: set[str],
    G: nx.Graph,
) -> list[str]:
    key = normalise_callable_label(token)
    if not key or len(key) < _MIN_SYMBOL_LEN:
        return []
    cands = label_index.get(key, [])
    if not cands:
        return []
    external = [c for c in cands if c not in local_ids]
    if len(external) == 1:
        return external
    if len(external) > 1:
        by_source: dict[str, list[str]] = {}
        for nid in external:
            sf = str(G.nodes[nid].get("source_file", ""))
            by_source.setdefault(sf, []).append(nid)
        if len(by_source) == 1:
            return [sorted(by_source[next(iter(by_source))])[0]]
        return []
    return []


def _edge_triples_from_graph(G: nx.Graph) -> set[tuple[str, str, str]]:
    edges = [
        {
            "source": d.get("_src", u),
            "target": d.get("_tgt", v),
            "relation": d.get("relation", ""),
        }
        for u, v, d in G.edges(data=True)
    ]
    return existing_edge_pairs(edges)


def stitch_incremental_links(
    G: nx.Graph,
    changed_paths: list[str],
    *,
    root: str | Path,
    new_node_ids: set[str] | frozenset[str] | None = None,
) -> int:
    """Add ``references`` edges from changed files to the rest of the graph.

    Scans each changed file for backtick identifiers and markdown path links,
    resolves them against *G*, and attaches edges from the changed file's anchor
    node. Returns the number of edges added.

    When the LLM attributes re-extracted nodes to the wrong ``source_file``,
    pass *new_node_ids* (node ids from the fresh extraction) so anchors can
    still be chosen for stitch edges.
    """
    if not changed_paths:
        return 0
    root_path = Path(root).resolve()
    new_ids = set(new_node_ids or ())
    label_index = _stitch_label_index(G)
    known = _edge_triples_from_graph(G)
    added = 0

    for path_str in changed_paths:
        disk_path = Path(path_str)
        if not disk_path.is_absolute():
            disk_path = root_path / disk_path
        if not disk_path.is_file():
            continue
        try:
            rel = disk_path.resolve().relative_to(root_path)
        except ValueError:
            rel = Path(path_str)
        try:
            text = disk_path.read_text(encoding="utf-8")
        except OSError:
            continue

        local_nids = _nodes_for_source_file(G, str(rel), root_path)
        if not local_nids and new_ids:
            local_nids = _fallback_local_nodes(G, new_ids, rel, root_path)
        anchor = _pick_file_anchor(local_nids, G, rel)
        if not anchor:
            continue

        local_ids = set(local_nids)
        seen_tokens: set[str] = set()

        for token in _BACKTICK.findall(text) + _MD_LINK.findall(text):
            token = token.strip()
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)

            if _looks_like_path(token):
                targets = _resolve_path_target(token, root_path, G)
            else:
                targets = _resolve_symbol_targets(token, label_index, local_ids, G)

            for tgt in targets:
                if tgt == anchor:
                    continue
                triple = (anchor, tgt, "references")
                if triple in known:
                    continue
                known.add(triple)
                G.add_edge(
                    anchor,
                    tgt,
                    relation="references",
                    confidence="EXTRACTED",
                    confidence_score=1.0,
                    source_file=rel.as_posix(),
                    weight=1.0,
                    _src=anchor,
                    _tgt=tgt,
                )
                added += 1

    if added:
        print(
            f"[graphify] Stitched {added} cross-file reference edge(s) "
            f"for {len(changed_paths)} changed file(s).",
            file=sys.stderr,
        )
    return added
