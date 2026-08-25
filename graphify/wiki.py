# Wiki export - Wikipedia-style markdown articles from the knowledge graph
# Generates an agent-crawlable wiki: index.md + one article per community + god node articles
from __future__ import annotations
from collections import Counter
from pathlib import Path
import networkx as nx


def _safe_filename(name: str) -> str:
    return name.replace("/", "-").replace(" ", "_").replace(":", "-")


def _cross_community_links(G: nx.Graph, nodes: list[str], own_cid: int, labels: dict[int, str]) -> list[tuple[str, int]]:
    """Return (community_label, edge_count) pairs for cross-community connections, sorted descending."""
    counts: dict[str, int] = Counter()
    for nid in nodes:
        for neighbor in G.neighbors(nid):
            nd = G.nodes[neighbor]
            ncid = nd.get("community")
            if ncid is not None and ncid != own_cid:
                counts[labels.get(ncid, f"Community {ncid}")] += 1
    return sorted(counts.items(), key=lambda x: -x[1])


def _community_article(
    G: nx.Graph,
    cid: int,
    nodes: list[str],
    label: str,
    labels: dict[int, str],
    cohesion: float | None,
) -> str:
    top_nodes = sorted(nodes, key=lambda n: G.degree(n), reverse=True)[:25]
    cross = _cross_community_links(G, nodes, cid, labels)

    # Edge confidence breakdown
    conf_counts: Counter = Counter()
    for nid in nodes:
        for neighbor in G.neighbors(nid):
            ed = G.edges[nid, neighbor]
            conf_counts[ed.get("confidence", "EXTRACTED")] += 1
    total_edges = sum(conf_counts.values()) or 1

    sources = sorted({G.nodes[n].get("source_file", "") for n in nodes} - {""})

    lines: list[str] = []
    lines += [f"# {label}", ""]

    meta_parts = [f"{len(nodes)} nodes"]
    if cohesion is not None:
        meta_parts.append(f"cohesion {cohesion:.2f}")
    lines += [f"> {' · '.join(meta_parts)}", ""]

    lines += ["## Key Concepts", ""]
    for nid in top_nodes:
        d = G.nodes[nid]
        node_label = d.get("label", nid)
        src = d.get("source_file", "")
        degree = G.degree(nid)
        src_str = f" — `{src}`" if src else ""
        lines.append(f"- **{node_label}** ({degree} connections){src_str}")
    remaining = len(nodes) - len(top_nodes)
    if remaining > 0:
        lines.append(f"- *... and {remaining} more nodes in this community*")
    lines.append("")

    lines += ["## Relationships", ""]
    if cross:
        for other_label, count in cross[:12]:
            lines.append(f"- [[{other_label}]] ({count} shared connections)")
    else:
        lines.append("- No strong cross-community connections detected")
    lines.append("")

    if sources:
        lines += ["## Source Files", ""]
        for src in sources[:20]:
            lines.append(f"- `{src}`")
        lines.append("")

    lines += ["## Audit Trail", ""]
    for conf in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
        n = conf_counts.get(conf, 0)
        pct = round(n / total_edges * 100)
        lines.append(f"- {conf}: {n} ({pct}%)")
    lines.append("")

    lines += ["---", "", "*Part of the graphify knowledge wiki. See [[index]] to navigate.*"]
    return "\n".join(lines)


def _god_node_article(G: nx.Graph, nid: str, labels: dict[int, str]) -> str:
    d = G.nodes[nid]
    node_label = d.get("label", nid)
    src = d.get("source_file", "")
    cid = d.get("community")
    community_name = labels.get(cid, f"Community {cid}") if cid is not None else None

    lines: list[str] = []
    lines += [f"# {node_label}", ""]
    lines += [f"> God node · {G.degree(nid)} connections · `{src}`", ""]

    if community_name:
        lines += [f"**Community:** [[{community_name}]]", ""]

    # Group neighbors by relation type
    by_relation: dict[str, list[str]] = {}
    for neighbor in sorted(G.neighbors(nid), key=lambda n: G.degree(n), reverse=True):
        nd = G.nodes[neighbor]
        ed = G.edges[nid, neighbor]
        rel = ed.get("relation", "related")
        neighbor_label = nd.get("label", neighbor)
        conf = ed.get("confidence", "")
        conf_str = f" `{conf}`" if conf else ""
        by_relation.setdefault(rel, []).append(f"[[{neighbor_label}]]{conf_str}")

    lines += ["## Connections by Relation", ""]
    for rel, targets in sorted(by_relation.items()):
        lines.append(f"### {rel}")
        for t in targets[:20]:
            lines.append(f"- {t}")
        lines.append("")

    lines += ["---", "", "*Part of the graphify knowledge wiki. See [[index]] to navigate.*"]
    return "\n".join(lines)


def _unique_filename(base: str, used: set[str]) -> str:
    name = base
    idx = 2
    while name in used:
        name = f"{base}_{idx}"
        idx += 1
    used.add(name)
    return name


def _index_md(
    communities: dict[int, list[str]],
    labels: dict[int, str],
    god_nodes_data: list[dict],
    total_nodes: int,
    total_edges: int,
    community_slugs: dict[int, str] | None = None,
    god_slugs: list[tuple[dict, str]] | None = None,
) -> str:
    lines: list[str] = [
        "# Knowledge Graph Index",
        "",
        "> Auto-generated by graphify. Start here — read community articles for context, then drill into god nodes for detail.",
        "",
        f"**{total_nodes} nodes · {total_edges} edges · {len(communities)} communities**",
        "",
        "---",
        "",
        "## Communities",
        "(sorted by size, largest first)",
        "",
    ]

    for cid, nodes in sorted(communities.items(), key=lambda x: -len(x[1])):
        label = labels.get(cid, f"Community {cid}")
        slug = community_slugs.get(cid) if community_slugs else None
        link_target = slug if slug and slug != _safe_filename(label) else label
        lines.append(f"- [[{link_target}]] — {len(nodes)} nodes")
    lines.append("")

    if god_slugs:
        lines += ["## God Nodes", "(most connected concepts — the load-bearing abstractions)", ""]
        for node, slug in god_slugs:
            edges = node.get("edges") or node.get("degree") or 0
            label = node.get("label", slug)
            link_target = slug if slug != _safe_filename(label) else label
            lines.append(f"- [[{link_target}]] — {edges} connections")
        lines.append("")
    elif god_nodes_data:
        lines += ["## God Nodes", "(most connected concepts — the load-bearing abstractions)", ""]
        for node in god_nodes_data:
            edges = node.get("edges") or node.get("degree") or 0
            lines.append(f"- [[{node['label']}]] — {edges} connections")
        lines.append("")

    lines += [
        "---",
        "",
        "*Generated by [graphify](https://github.com/safishamsi/graphify)*",
    ]
    return "\n".join(lines)


def to_wiki(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_dir: str | Path,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
    god_nodes_data: list[dict] | None = None,
) -> int:
    """Generate a Wikipedia-style wiki from the graph.

    Writes:
      - index.md            — agent entry point, catalog of all articles
      - <CommunityName>.md  — one article per community
      - <GodNodeLabel>.md   — one article per god node

    Returns the number of articles written (excluding index.md).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    labels = community_labels or {cid: f"Community {cid}" for cid in communities}
    cohesion = cohesion or {}
    god_nodes_data = god_nodes_data or []

    count = 0
    used_slugs: set[str] = set()

    # Community articles
    community_slugs: dict[int, str] = {}
    for cid, nodes in communities.items():
        label = labels.get(cid, f"Community {cid}")
        slug = _unique_filename(_safe_filename(label), used_slugs)
        community_slugs[cid] = slug
        article = _community_article(G, cid, nodes, label, labels, cohesion.get(cid))
        (out / f"{slug}.md").write_text(article)
        count += 1

    # God node articles
    god_slugs: list[tuple[dict, str]] = []
    for node_data in god_nodes_data:
        nid = node_data.get("id")
        if nid and nid in G:
            label = node_data.get("label", nid)
            slug = _unique_filename(_safe_filename(label), used_slugs)
            god_slugs.append((node_data, slug))
            article = _god_node_article(G, nid, labels)
            (out / f"{slug}.md").write_text(article)
            count += 1

    # Index
    (out / "index.md").write_text(
        _index_md(
            communities,
            labels,
            god_nodes_data,
            G.number_of_nodes(),
            G.number_of_edges(),
            community_slugs=community_slugs,
            god_slugs=god_slugs,
        )
    )

    return count
