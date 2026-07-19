"""Graph analysis: god nodes (most connected), surprising connections (cross-community), suggested questions."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from graphify.helix.access import (
    degree as _degree,
    degree_map,
    edge_rows as _edges,
    first_edge_attributes as edge_data,
    node_attributes,
    node_ids,
)
from graphify.helix.model import graphify_attributes


def _graphify_betweenness_options():
    from helixdb.graph import BetweennessOptions

    return BetweennessOptions(mode="auto", sample_count=100, seed=42, exact_through=1_000)

# Builtin/mock names that can appear as annotation-derived nodes in pre-existing
# graphs. Excluded from god-node ranking so they don't displace real abstractions
# even if they weren't filtered at extraction time (#1147).
_BUILTIN_NOISE_LABELS = frozenset({
    "str", "int", "float", "bool", "bytes", "bytearray", "complex", "object",
    "True", "False",
    "MagicMock", "Mock", "AsyncMock", "NonCallableMock",
    "NonCallableMagicMock", "PropertyMock", "patch", "sentinel",
    # Python stdlib types commonly confused for project symbols
    "Path", "Any", "Optional", "List", "Dict", "Set", "Tuple", "Union",
    "Callable", "Type", "ClassVar", "Final", "Literal", "Protocol",
    "Counter", "defaultdict", "OrderedDict", "datetime", "Enum",
    "os", "sys", "re", "json", "io", "abc", "typing",
})

# Language families — extensions sharing a runtime can legitimately call each other
_LANG_FAMILY: dict[str, str] = {
    **{e: "python" for e in (".py", ".pyw")},
    **{e: "js" for e in (".js", ".jsx", ".mjs", ".cjs", ".ejs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte")},
    **{e: "go" for e in (".go",)},
    **{e: "rust" for e in (".rs",)},
    **{e: "jvm" for e in (".java", ".kt", ".kts", ".scala")},
    **{e: "c" for e in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp")},
    **{e: "ruby" for e in (".rb", ".rake")},
    **{e: "swift" for e in (".swift",)},
    **{e: "dotnet" for e in (".cs",)},
    **{e: "php" for e in (".php",)},
    **{e: "r" for e in (".r",)},
}


def _cross_language(src_a: str, src_b: str) -> bool:
    """Return True if two source files belong to different language families."""
    ext_a = Path(src_a).suffix.lower()
    ext_b = Path(src_b).suffix.lower()
    fam_a = _LANG_FAMILY.get(ext_a)
    fam_b = _LANG_FAMILY.get(ext_b)
    if fam_a is None or fam_b is None:
        return False
    return fam_a != fam_b


def _node_community_map(communities: dict[int, list[str]]) -> dict[str, int]:
    """Invert communities dict: node_id -> community_id."""
    return {n: cid for cid, nodes in communities.items() for n in nodes}


def _is_file_node(G: Any, node_id: str) -> bool:
    """
    Return True if this node is a file-level hub node (e.g. 'client', 'models')
    or an AST method stub (e.g. '.auth_flow()', '.__init__()').

    These are synthetic nodes created by the AST extractor and should be excluded
    from god nodes, surprising connections, and knowledge gap reporting.
    """
    attrs = node_attributes(G, node_id)
    label = attrs.get("label", "")
    if not label:
        return False
    # File-level hub: label matches the actual source filename (not just any label ending in .py)
    source_file = attrs.get("source_file", "")
    if source_file:
        from pathlib import Path as _Path
        if label == _Path(source_file).name:
            return True
    # Method stub: AST extractor labels methods as '.method_name()'
    if label.startswith(".") and label.endswith("()"):
        return True
    # Module-level function stub: labeled 'function_name()' - only has a contains edge
    # These are real functions but structurally isolated by definition; not a gap worth flagging
    if label.endswith("()") and _degree(G, node_id) <= 1:
        return True
    return False


_JSON_NOISE_LABELS: frozenset[str] = frozenset({
    "start", "end", "name", "id", "type", "properties",
    "value", "key", "data", "items", "title", "description", "version",
    "dependencies", "devdependencies", "peerdependencies",
    "optionaldependencies", "bundleddependencies", "bundledependencies",
})


def _is_json_key_node(G: Any, node_id: str) -> bool:
    attrs = node_attributes(G, node_id)
    src = (attrs.get("source_file") or "").lower()
    if not src.endswith(".json"):
        return False
    label = (attrs.get("label") or "").strip().lower()
    return label in _JSON_NOISE_LABELS


def god_nodes(G: Any, top_n: int = 10) -> list[dict]:
    """Return the top_n most-connected real entities - the core abstractions.

    File-level hub nodes are excluded: they accumulate import/contains edges
    mechanically and don't represent meaningful architectural abstractions.
    """
    degree = {row.node_id: int(row.degree) for row in G.degrees()}
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)
    result = []
    for node_id, deg in sorted_nodes:
        if _is_file_node(G, node_id) or _is_concept_node(G, node_id) or _is_json_key_node(G, node_id):
            continue
        if node_attributes(G, node_id).get("label", "") in _BUILTIN_NOISE_LABELS:
            continue
        result.append({
            "id": node_id,
            "label": node_attributes(G, node_id).get("label", node_id),
            "degree": deg,
        })
        if len(result) >= top_n:
            break
    return result


def surprising_connections(
    G: Any,
    communities: dict[int, list[str]] | None = None,
    top_n: int = 5,
) -> list[dict]:
    """
    Find connections that are genuinely surprising - not obvious from file structure.

    Strategy:
    - Multi-file corpora: cross-file edges between real entities (not concept nodes).
      Sorted AMBIGUOUS → INFERRED → EXTRACTED.
    - Single-file / single-source corpora: cross-community edges that bridge
      distant parts of the graph (betweenness centrality on edges).
      These reveal non-obvious structural couplings.

    Concept nodes (empty source_file, or injected semantic annotations) are excluded
    from surprising connections because they are intentional, not discovered.
    """
    # Identify unique source files (ignore empty/null source_file)
    source_files = {
        data.get("source_file", "")
        for node in G.nodes()
        if (data := graphify_attributes(node.attributes)) is not None
        if data.get("source_file", "")
    }
    is_multi_source = len(source_files) > 1

    if is_multi_source:
        return _cross_file_surprises(G, communities or {}, top_n)
    else:
        return _cross_community_surprises(G, communities or {}, top_n)


def _is_concept_node(G: Any, node_id: str) -> bool:
    """
    Return True if this node is a manually-injected semantic concept node
    rather than a real entity found in source code.

    Signals:
    - Empty source_file
    - source_file doesn't look like a real file path (no extension)
    """
    data = node_attributes(G, node_id)
    source = data.get("source_file", "")
    if not source:
        return True
    # Has no file extension → probably a concept label, not a real file
    if "." not in source.split("/")[-1]:
        return True
    return False


from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS, IMAGE_EXTENSIONS


def _file_category(path: str) -> str:
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in PAPER_EXTENSIONS:
        return "paper"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "doc"


def _top_level_dir(path: str) -> str:
    """Return the first path component - used to detect cross-repo edges."""
    return path.split("/")[0] if "/" in path else path


def _surprise_score(
    G: Any,
    u: str,
    v: str,
    data: dict,
    node_community: dict[str, int],
    u_source: str,
    v_source: str,
    degrees: dict[str, int] | None = None,
) -> tuple[int, list[str]]:
    """Score how surprising a cross-file edge is. Returns (score, reasons)."""
    score = 0
    reasons: list[str] = []

    # 1. Confidence weight - uncertain connections are more noteworthy
    conf = data.get("confidence", "EXTRACTED")
    relation = data.get("relation", "")
    conf_bonus = {"AMBIGUOUS": 3, "INFERRED": 2, "EXTRACTED": 1}.get(conf, 1)

    cat_u = _file_category(u_source)
    cat_v = _file_category(v_source)

    # Suppress all structural bonuses for INFERRED calls/uses that cross language
    # boundaries or connect code to a doc file.  Both cases are resolver pollution:
    # label-matching fires across language families in monorepos, and code→doc
    # "calls" edges are extraction artefacts, not real architecture.
    # Excludes `semantically_similar_to` (genuine cross-boundary insight) and all
    # AMBIGUOUS/EXTRACTED edges (not from the resolver path).
    _suppress_structural = (
        conf == "INFERRED"
        and relation in ("calls", "uses")
        and (_cross_language(u_source, v_source) or {cat_u, cat_v} == {"code", "doc"})
    )
    if _suppress_structural:
        conf_bonus = 0

    score += conf_bonus
    if conf in ("AMBIGUOUS", "INFERRED"):
        reasons.append(f"{conf.lower()} connection - not explicitly stated in source")

    # 2. Cross file-type bonus - code↔paper or code↔image is non-obvious
    if cat_u != cat_v and not _suppress_structural:
        score += 2
        reasons.append(f"crosses file types ({cat_u} ↔ {cat_v})")

    # 3. Cross-repo bonus - different top-level directory
    if _top_level_dir(u_source) != _top_level_dir(v_source) and not _suppress_structural:
        score += 2
        reasons.append("connects across different repos/directories")

        # 4. Cross-community bonus - Leiden says these are structurally distant
    cid_u = node_community.get(u)
    cid_v = node_community.get(v)
    if cid_u is not None and cid_v is not None and cid_u != cid_v and not _suppress_structural:
        score += 1
        reasons.append("bridges separate communities")

    # 4b. Semantic similarity bonus - non-obvious conceptual links score higher
    if data.get("relation") == "semantically_similar_to":
        score = int(score * 1.5)
        reasons.append("semantically similar concepts with no structural link")

    # 5. Peripheral→hub: a low-degree node connecting to a high-degree one
    deg_u = degrees[u] if degrees is not None else _degree(G, u)
    deg_v = degrees[v] if degrees is not None else _degree(G, v)
    if min(deg_u, deg_v) <= 2 and max(deg_u, deg_v) >= 5:
        score += 1
        peripheral = node_attributes(G, u).get("label", u) if deg_u <= 2 else node_attributes(G, v).get("label", v)
        hub = node_attributes(G, v).get("label", v) if deg_u <= 2 else node_attributes(G, u).get("label", u)
        reasons.append(f"peripheral node `{peripheral}` unexpectedly reaches hub `{hub}`")

    return score, reasons


def _cross_file_surprises(G: Any, communities: dict[int, list[str]], top_n: int) -> list[dict]:
    """
    Cross-file edges between real code/doc entities, ranked by a composite
    surprise score rather than confidence alone.

    Surprise score accounts for:
    - Confidence (AMBIGUOUS > INFERRED > EXTRACTED)
    - Cross file-type (code↔paper is more surprising than code↔code)
    - Cross-repo (different top-level directory)
    - Cross-community (Leiden says structurally distant)
    - Peripheral→hub (low-degree node reaching a god node)

    Each result includes a 'why' field explaining what makes it non-obvious.
    """
    node_community = _node_community_map(communities)
    degrees = degree_map(G)
    candidates = []

    for u, v, data, _ in _edges(G):
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        if _is_concept_node(G, u) or _is_concept_node(G, v):
            continue
        if _is_file_node(G, u) or _is_file_node(G, v):
            continue

        u_source = node_attributes(G, u).get("source_file", "")
        v_source = node_attributes(G, v).get("source_file", "")

        if not u_source or not v_source or u_source == v_source:
            continue

        score, reasons = _surprise_score(G, u, v, data, node_community, u_source, v_source, degrees)
        src_id = data.get("_src", u)
        if not G.contains_node(src_id):
            src_id = u
        tgt_id = data.get("_tgt", v)
        if not G.contains_node(tgt_id):
            tgt_id = v
        candidates.append({
            "_score": score,
            "source": node_attributes(G, src_id).get("label", src_id),
            "target": node_attributes(G, tgt_id).get("label", tgt_id),
            "source_files": [
                node_attributes(G, src_id).get("source_file", ""),
                node_attributes(G, tgt_id).get("source_file", ""),
            ],
            "confidence": data.get("confidence", "EXTRACTED"),
            "relation": relation,
            "why": "; ".join(reasons) if reasons else "cross-file semantic connection",
        })

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    for c in candidates:
        c.pop("_score")

    if candidates:
        return candidates[:top_n]

    return _cross_community_surprises(G, communities, top_n)


def _cross_community_surprises(
    G: Any,
    communities: dict[int, list[str]],
    top_n: int,
) -> list[dict]:
    """
    For single-source corpora: find edges that bridge different communities.
    These are surprising because Leiden grouped everything else tightly -
    these edges cut across the natural structure.

    Falls back to high-betweenness edges if no community info is provided.
    """
    if not communities:
        # No community info - use edge betweenness centrality
        if G.edge_count == 0:
            return []
        if G.node_count > 5000:
            return []
        top_edges = sorted(
            G.edge_betweenness_centrality(_graphify_betweenness_options()),
            key=lambda row: row.score,
            reverse=True,
        )[:top_n]
        result = []
        for row in top_edges:
            edge = G.edge(row.edge_id)
            if edge is None:
                continue
            u, v, score = edge.source, edge.target, row.score
            data = edge_data(G, u, v)
            result.append({
                "source": node_attributes(G, u).get("label", u),
                "target": node_attributes(G, v).get("label", v),
                "source_files": [
                    node_attributes(G, u).get("source_file", ""),
                    node_attributes(G, v).get("source_file", ""),
                ],
                "confidence": data.get("confidence", "EXTRACTED"),
                "relation": data.get("relation", ""),
                "note": f"Bridges graph structure (betweenness={score:.3f})",
            })
        return result

    # Build node → community map
    node_community = _node_community_map(communities)

    surprises = []
    for u, v, data, _ in _edges(G):
        cid_u = node_community.get(u)
        cid_v = node_community.get(v)
        if cid_u is None or cid_v is None or cid_u == cid_v:
            continue
        # Skip file hub nodes and plain structural edges
        if _is_file_node(G, u) or _is_file_node(G, v):
            continue
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        # This edge crosses community boundaries - interesting
        confidence = data.get("confidence", "EXTRACTED")
        src_id = data.get("_src", u)
        if not G.contains_node(src_id):
            src_id = u
        tgt_id = data.get("_tgt", v)
        if not G.contains_node(tgt_id):
            tgt_id = v
        surprises.append({
            "source": node_attributes(G, src_id).get("label", src_id),
            "target": node_attributes(G, tgt_id).get("label", tgt_id),
            "source_files": [
                node_attributes(G, src_id).get("source_file", ""),
                node_attributes(G, tgt_id).get("source_file", ""),
            ],
            "confidence": confidence,
            "relation": relation,
            "note": f"Bridges community {cid_u} → community {cid_v}",
            "_pair": tuple(sorted([cid_u, cid_v])),
        })

    # Sort: AMBIGUOUS first, then INFERRED, then EXTRACTED
    order = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2}
    surprises.sort(key=lambda x: order.get(x["confidence"], 3))

    # Deduplicate by community pair - one representative edge per (A→B) boundary.
    # Without this, a single high-betweenness god node dominates all results.
    seen_pairs: set[tuple] = set()
    deduped = []
    for s in surprises:
        pair = s.pop("_pair")
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            deduped.append(s)
    return deduped[:top_n]


def suggest_questions(
    G: Any,
    communities: dict[int, list[str]],
    community_labels: dict[int, str],
    top_n: int = 7,
) -> list[dict]:
    """
    Generate questions the graph is uniquely positioned to answer.
    Based on: AMBIGUOUS edges, bridge nodes, underexplored god nodes, isolated nodes.
    Each question has a 'type', 'question', and 'why' field.
    """
    if community_labels:
        community_labels = {int(k) if isinstance(k, str) else k: v for k, v in community_labels.items()}

    questions = []
    node_community = _node_community_map(communities)

    # 1. AMBIGUOUS edges → unresolved relationship questions
    for u, v, data, _ in _edges(G):
        if data.get("confidence") == "AMBIGUOUS":
            ul = node_attributes(G, u).get("label", u)
            vl = node_attributes(G, v).get("label", v)
            relation = data.get("relation", "related to")
            questions.append({
                "type": "ambiguous_edge",
                "question": f"What is the exact relationship between `{ul}` and `{vl}`?",
                "why": f"Edge tagged AMBIGUOUS (relation: {relation}) - confidence is low.",
            })

    # 2. Bridge nodes (high betweenness) → cross-cutting concern questions
    if G.edge_count > 0:
        betweenness = {
            row.node_id: row.score
            for row in G.betweenness_centrality(_graphify_betweenness_options())
        }
        # Top bridge nodes that are NOT file-level hubs
        bridges = sorted(
            [(n, s) for n, s in betweenness.items()
             if not _is_file_node(G, n) and not _is_concept_node(G, n) and s > 0],
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        for node_id, score in bridges:
            label = node_attributes(G, node_id).get("label", node_id)
            cid = node_community.get(node_id)
            comm_label = community_labels.get(cid, f"Community {cid}") if cid is not None else "unknown"
            neighbors = list(G.neighbors(node_id))
            neighbor_comms = {
                neighbor_cid
                for n in neighbors
                if (neighbor_cid := node_community.get(n)) is not None and neighbor_cid != cid
            }
            if neighbor_comms:
                other_labels = [community_labels.get(c, f"Community {c}") for c in neighbor_comms]
                questions.append({
                    "type": "bridge_node",
                    "question": f"Why does `{label}` connect `{comm_label}` to {', '.join(f'`{l}`' for l in other_labels)}?",
                    "why": f"High betweenness centrality ({score:.3f}) - this node is a cross-community bridge.",
                })

    # 3. God nodes with many INFERRED edges → verification questions
    degree = {row.node_id: int(row.degree) for row in G.degrees()}
    top_nodes = sorted(
        [(n, d) for n, d in degree.items() if not _is_file_node(G, n)],
        key=lambda x: x[1],
        reverse=True,
    )[:5]
    for node_id, _ in top_nodes:
        inferred = [
            (u, v, d) for u, v, d, _ in _edges(G, node_id)
            if d.get("confidence") == "INFERRED"
        ]
        if len(inferred) >= 2:
            label = node_attributes(G, node_id).get("label", node_id)
            # Use _src/_tgt to get the correct direction; fall back to v (the other node)
            others = []
            for u, v, d in inferred[:2]:
                src_id = d.get("_src", u)
                if not G.contains_node(src_id):
                    src_id = u
                tgt_id = d.get("_tgt", v)
                if not G.contains_node(tgt_id):
                    tgt_id = v
                other_id = tgt_id if src_id == node_id else src_id
                others.append(node_attributes(G, other_id).get("label", other_id))
            questions.append({
                "type": "verify_inferred",
                "question": f"Are the {len(inferred)} inferred relationships involving `{label}` (e.g. with `{others[0]}` and `{others[1]}`) actually correct?",
                "why": f"`{label}` has {len(inferred)} INFERRED edges - model-reasoned connections that need verification.",
            })

    # 4. Isolated or weakly-connected nodes → exploration questions
    isolated = [
        n for n in node_ids(G)
        if _degree(G, n) <= 1
        and not _is_file_node(G, n)
        and not _is_concept_node(G, n)
        and node_attributes(G, n).get("file_type") != "rationale"
    ]
    if isolated:
        labels = [node_attributes(G, n).get("label", n) for n in isolated[:3]]
        questions.append({
            "type": "isolated_nodes",
            "question": f"What connects {', '.join(f'`{l}`' for l in labels)} to the rest of the system?",
            "why": f"{len(isolated)} weakly-connected nodes found - possible documentation gaps or missing edges.",
        })

    # 5. Low-cohesion communities → structural questions
    from .cluster import cohesion_score
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        if score < 0.15 and len(nodes) >= 5:
            label = community_labels.get(cid, f"Community {cid}")
            questions.append({
                "type": "low_cohesion",
                "question": f"Should `{label}` be split into smaller, more focused modules?",
                "why": f"Cohesion score {score} - nodes in this community are weakly interconnected.",
            })

    if not questions:
        return [{
            "type": "no_signal",
            "question": None,
            "why": (
                "Not enough signal to generate questions. "
                "This usually means the corpus has no AMBIGUOUS edges, no bridge nodes, "
                "no INFERRED relationships, and all communities are tightly cohesive. "
                "Add more files or run with --mode deep to extract richer edges."
            ),
        }]

    return questions[:top_n]


def graph_diff(G_old: Any, G_new: Any) -> dict:
    """Compare two graph snapshots and return what changed.

    Returns:
        {
          "new_nodes": [{"id": ..., "label": ...}],
          "removed_nodes": [{"id": ..., "label": ...}],
          "new_edges": [{"source": ..., "target": ..., "relation": ..., "confidence": ...}],
          "removed_edges": [...],
          "summary": "3 new nodes, 5 new edges, 1 node removed"
        }
    """
    old_nodes = {node.id for node in G_old.nodes()}
    new_nodes = {node.id for node in G_new.nodes()}

    added_node_ids = new_nodes - old_nodes
    removed_node_ids = old_nodes - new_nodes

    new_nodes_list = [
        {"id": n, "label": node_attributes(G_new, n).get("label", n)}
        for n in added_node_ids
    ]
    removed_nodes_list = [
        {"id": n, "label": node_attributes(G_old, n).get("label", n)}
        for n in removed_node_ids
    ]

    def edge_key(G: Any, u: str, v: str, data: dict) -> tuple:
        if G.directed:
            return (u, v, data.get("relation", ""))
        return (min(u, v), max(u, v), data.get("relation", ""))

    old_edge_keys = {
        edge_key(G_old, u, v, d)
        for u, v, d, _ in _edges(G_old)
    }
    new_edge_keys = {
        edge_key(G_new, u, v, d)
        for u, v, d, _ in _edges(G_new)
    }

    added_edge_keys = new_edge_keys - old_edge_keys
    removed_edge_keys = old_edge_keys - new_edge_keys

    new_edges_list = []
    for u, v, d, _ in _edges(G_new):
        if edge_key(G_new, u, v, d) in added_edge_keys:
            new_edges_list.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", ""),
            })

    removed_edges_list = []
    for u, v, d, _ in _edges(G_old):
        if edge_key(G_old, u, v, d) in removed_edge_keys:
            removed_edges_list.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "confidence": d.get("confidence", ""),
            })

    parts = []
    if new_nodes_list:
        parts.append(f"{len(new_nodes_list)} new node{'s' if len(new_nodes_list) != 1 else ''}")
    if new_edges_list:
        parts.append(f"{len(new_edges_list)} new edge{'s' if len(new_edges_list) != 1 else ''}")
    if removed_nodes_list:
        parts.append(f"{len(removed_nodes_list)} node{'s' if len(removed_nodes_list) != 1 else ''} removed")
    if removed_edges_list:
        parts.append(f"{len(removed_edges_list)} edge{'s' if len(removed_edges_list) != 1 else ''} removed")
    summary = ", ".join(parts) if parts else "no changes"

    return {
        "new_nodes": new_nodes_list,
        "removed_nodes": removed_nodes_list,
        "new_edges": new_edges_list,
        "removed_edges": removed_edges_list,
        "summary": summary,
    }


def find_import_cycles(
    G: Any,
    max_cycle_length: int = 5,
    top_n: int = 20,
) -> list[dict]:
    """Detect circular import dependencies at the file level.

    Collapses symbol-level nodes to their parent file (using source_file attr
    or 'contains' edges), builds a directed file-level graph from imports_from
    edges, then finds simple cycles.

    Args:
        G: The full knowledge graph (may be undirected or directed).
        max_cycle_length: Only report cycles with at most this many files.
        top_n: Maximum number of cycles to return (shortest first).

    Returns:
        List of cycle records with stable structure:
        {
          "cycle": ["a.ts", "b.ts"],
          "length": 2,
          "why": "circular dependency"
        }
    """
    def _endpoint_source_file(node_id: str) -> str:
        if not G.contains_node(node_id):
            return ""
        attrs = node_attributes(G, node_id)
        src_file = attrs.get("source_file", "")
        return src_file if isinstance(src_file, str) else ""

    # Step 1: Build a directed file-level graph from import/re-export edges.
    # IMPORTANT: resolve endpoints using source_file only; never infer from label/id.
    adjacency: dict[str, set[str]] = {}

    for u, v, data, _ in _edges(G):
        rel = data.get("relation", "")
        if rel not in ("imports_from", "re_exports"):
            continue

        # Deferred `import(...)` edges are real dependencies but do not form a
        # hard file-level cycle, so they are excluded from cycle detection (#1241).
        if data.get("deferred"):
            continue

        src_file_attr = data.get("source_file", "")
        if not isinstance(src_file_attr, str) or not src_file_attr:
            continue

        u_file = _endpoint_source_file(u)
        v_file = _endpoint_source_file(v)

        # Works for both DiGraph and Graph inputs:
        # orient edge from edge.source_file endpoint to the opposite endpoint.
        if u_file == src_file_attr:
            tgt_file = v_file
        elif v_file == src_file_attr:
            tgt_file = u_file
        else:
            # Fallback: if source endpoint cannot be matched exactly,
            # still treat edge.source_file as source and pick the opposite endpoint
            # only if one endpoint has a real source_file.
            tgt_file = v_file if v_file and v_file != src_file_attr else u_file

        if not tgt_file:
            continue

        adjacency.setdefault(src_file_attr, set()).add(tgt_file)

    if not adjacency:
        return []

    # Step 2: Find simple cycles, bounded by length.
    # Bound enumeration to avoid exponential blowup on dense graphs.
    cycles: list[list[str]] = []

    def walk(start: str, current: str, path: list[str], seen: set[str]) -> None:
        if len(cycles) >= top_n * 10 or len(path) > max_cycle_length:
            return
        for target in sorted(adjacency.get(current, ())):
            if target == start:
                cycles.append(path.copy())
            elif target not in seen and len(path) < max_cycle_length:
                walk(start, target, [*path, target], {*seen, target})

    for start in sorted(adjacency):
        walk(start, start, [start], {start})
        if len(cycles) >= top_n * 10:
            break

    # Step 3: Sort by length (shortest = tightest coupling), then deduplicate.
    cycles.sort(key=len)

    # Deduplicate rotations: normalize each cycle by starting from the
    # lexicographically smallest element.
    seen: set[tuple[str, ...]] = set()
    unique_cycles: list[list[str]] = []
    for cycle in cycles:
        core = list(cycle)
        if not core:
            continue
        min_idx = core.index(min(core))
        normalized = tuple(core[min_idx:] + core[:min_idx])
        if normalized not in seen:
            seen.add(normalized)
            unique_cycles.append(list(normalized))
            if len(unique_cycles) >= top_n:
                break

    result: list[dict] = []
    for cycle in unique_cycles:
        result.append({
            "cycle": cycle,
            "length": len(cycle),
            "why": "circular dependency",
        })

    return result
