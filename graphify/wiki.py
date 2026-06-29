# Wiki export - Wikipedia-style markdown articles from the knowledge graph
# Generates an agent-crawlable wiki: index.md + one article per community + god node articles
from __future__ import annotations
from collections import Counter
from pathlib import Path
from urllib.parse import quote
import networkx as nx

from graphify.build import edge_data


def _safe_filename(name: str) -> str:
    """Make a label safe for use as a filename across platforms.

    Substitutes characters that Windows reserves in filenames
    (< > : " / \\ | ? *) and strips trailing dots/spaces, also reserved.
    Falls back to 'unnamed' for empty results and caps length at 200
    chars to stay well under common filesystem limits.
    """
    import re
    s = name.replace("/", "-").replace(" ", "_").replace(":", "-")
    s = re.sub(r'[<>:"/\\|?*]', '_', s)
    s = s.strip('. ')
    return s[:200] if s else 'unnamed'


def _md_link(label: str, resolver: dict[str, str]) -> str:
    """Render a link to another wiki article as a portable relative markdown link.

    ``resolver`` maps an article's display label to the slug (filename stem) it
    was written under. When the label has an article, emit a standard
    ``[label](slug.md)`` link, URL-encoding the target so any spaces, parens, &
    or # in the slug survive every CommonMark renderer (GitHub, GitLab, VS Code
    preview, a plain browser) and Obsidian alike. The old ``[[label]]`` form
    only resolved inside Obsidian, because the on-disk filename differs from the
    label — _safe_filename turns spaces into underscores and substitutes
    reserved characters — so e.g. ``[[Domain Data Models]]`` pointed at a
    non-existent ``Domain Data Models.md`` everywhere else.

    Labels with no article — most node-level links, since only communities and
    god nodes get article files — render as plain text instead of a dead link
    that points nowhere even inside Obsidian.
    """
    text = label.replace("[", r"\[").replace("]", r"\]")
    slug = resolver.get(label)
    if slug is None:
        return text
    return f"[{text}]({quote(f'{slug}.md')})"


def _cross_community_links(G: nx.Graph, nodes: list[str], own_cid: int, labels: dict[int, str], node_community: dict[str, int]) -> list[tuple[str, int]]:
    """Return (community_label, edge_count) pairs for cross-community connections, sorted descending."""
    counts: dict[str, int] = Counter()
    for nid in nodes:
        for neighbor in G.neighbors(nid):
            ncid = node_community.get(neighbor)
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
    node_community: dict[str, int] | None = None,
    resolver: dict[str, str] | None = None,
) -> str:
    resolver = resolver or {}
    top_nodes = sorted(nodes, key=lambda n: G.degree(n), reverse=True)[:25]
    cross = _cross_community_links(G, nodes, cid, labels, node_community or {})

    # Edge confidence breakdown
    conf_counts: Counter = Counter()
    for nid in nodes:
        for neighbor in G.neighbors(nid):
            ed = edge_data(G, nid, neighbor)
            conf_counts[ed.get("confidence", "EXTRACTED")] += 1
    total_edges = sum(conf_counts.values()) or 1

    sources = sorted({G.nodes[n].get("source_file") or "" for n in nodes} - {""})

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
            lines.append(f"- {_md_link(other_label, resolver)} ({count} shared connections)")
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

    lines += ["---", "", f"*Part of the graphify knowledge wiki. See {_md_link('index', resolver)} to navigate.*"]
    return "\n".join(lines)


def _god_node_article(G: nx.Graph, nid: str, labels: dict[int, str], node_community: dict[str, int] | None = None, resolver: dict[str, str] | None = None) -> str:
    resolver = resolver or {}
    d = G.nodes[nid]
    node_label = d.get("label", nid)
    src = d.get("source_file", "")
    cid = (node_community or {}).get(nid)
    community_name = labels.get(cid, f"Community {cid}") if cid is not None else None

    lines: list[str] = []
    lines += [f"# {node_label}", ""]
    lines += [f"> God node · {G.degree(nid)} connections · `{src}`", ""]

    if community_name:
        lines += [f"**Community:** {_md_link(community_name, resolver)}", ""]

    # Group neighbors by relation type
    by_relation: dict[str, list[str]] = {}
    for neighbor in sorted(G.neighbors(nid), key=lambda n: G.degree(n), reverse=True):
        nd = G.nodes[neighbor]
        ed = edge_data(G, nid, neighbor)
        rel = ed.get("relation", "related")
        neighbor_label = nd.get("label", neighbor)
        conf = ed.get("confidence", "")
        conf_str = f" `{conf}`" if conf else ""
        by_relation.setdefault(rel, []).append(f"{_md_link(neighbor_label, resolver)}{conf_str}")

    lines += ["## Connections by Relation", ""]
    for rel, targets in sorted(by_relation.items()):
        lines.append(f"### {rel}")
        for t in targets[:20]:
            lines.append(f"- {t}")
        lines.append("")

    lines += ["---", "", f"*Part of the graphify knowledge wiki. See {_md_link('index', resolver)} to navigate.*"]
    return "\n".join(lines)


def _index_md(
    communities: dict[int, list[str]],
    labels: dict[int, str],
    god_nodes_data: list[dict],
    total_nodes: int,
    total_edges: int,
    resolver: dict[str, str] | None = None,
) -> str:
    resolver = resolver or {}
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
        lines.append(f"- {_md_link(label, resolver)} — {len(nodes)} nodes")
    lines.append("")

    if god_nodes_data:
        lines += ["## God Nodes", "(most connected concepts — the load-bearing abstractions)", ""]
        for node in god_nodes_data:
            lines.append(f"- {_md_link(node['label'], resolver)} — {node['degree']} connections")
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

    if not communities:
        raise ValueError(
            "communities dict is empty — refusing to clear wiki/. "
            "Run `graphify extract .` or `graphify cluster-only .` first."
        )

    # Filter stale node IDs that exist in communities but not in G.
    # Analysis JSON can drift from the graph after dedup / re-extract / update.
    # NetworkX 3.x returns DegreeView({}) for missing nodes instead of raising,
    # which crashes sorted() with TypeError; G.neighbors()/G.nodes[] also raise.
    import sys as _sys
    _g_nodes = set(G.nodes)
    _orig_total = sum(len(ns) for ns in communities.values())
    communities = {cid: [n for n in nodes if n in _g_nodes] for cid, nodes in communities.items()}
    communities = {cid: nodes for cid, nodes in communities.items() if nodes}
    _kept_total = sum(len(ns) for ns in communities.values())
    if _kept_total < _orig_total:
        print(
            f"wiki: dropped {_orig_total - _kept_total} stale node ID(s) not in graph "
            f"({len(communities)} communities remaining)",
            file=_sys.stderr,
        )

    if not communities:
        raise ValueError(
            "all community node IDs are stale — none exist in the graph. "
            "Re-run `graphify extract .` to regenerate .graphify_analysis.json."
        )

    # Clear stale .md files from previous runs to prevent orphan accumulation.
    # Community labels are LLM-generated (per skill.md Step 5) and non-deterministic
    # across runs — the same conceptual community may be named differently each time
    # (e.g. "AutoAgent Skills" → "AutoAgent Methodology"), leaving the previous file
    # as an orphan. Since to_wiki() owns wiki/ entirely (always writes the full set),
    # it can safely clear .md files at the start of each call.
    for old_article in out.glob("*.md"):
        old_article.unlink()

    labels = community_labels or {cid: f"Community {cid}" for cid in communities}
    cohesion = cohesion or {}
    god_nodes_data = god_nodes_data or []

    # Build node->community lookup once; node attrs never carry community (it lives in
    # the communities dict), so _cross_community_links and _god_node_article need this.
    node_community: dict[str, int] = {n: cid for cid, nodes in communities.items() for n in nodes}

    count = 0
    used_slugs: set[str] = set()

    def _unique_slug(base: str) -> str:
        # Fold case in the collision check: two labels differing only by case
        # (e.g. "Parser" vs "parser") resolve to one path on case-insensitive
        # filesystems (macOS/APFS, Windows/NTFS), so they must dedup against each
        # other while still emitting the original-case filename.
        slug = base
        n = 2
        while slug.lower() in used_slugs:
            slug = f"{base}_{n}"
            n += 1
        used_slugs.add(slug.lower())
        return slug

    # First pass: assign every article its slug before rendering any body, so the
    # bodies can link to one another. A link's target is the on-disk filename (the
    # slug), which differs from the label — _safe_filename turns spaces into
    # underscores and substitutes reserved chars, and a slug may pick up a numeric
    # suffix from collision dedup — so the final slug must be known up front.
    # resolver maps display label -> slug; labels with no article are absent, so
    # _md_link renders them as plain text. Communities are slugged before god nodes
    # (and setdefault keeps the first), preserving the filename-assignment order
    # the case-collision dedup relies on.
    resolver: dict[str, str] = {"index": "index"}

    community_slugs: dict[int, str] = {}
    for cid in communities:
        label = labels.get(cid, f"Community {cid}")
        slug = _unique_slug(_safe_filename(label))
        community_slugs[cid] = slug
        resolver.setdefault(label, slug)

    god_articles: list[tuple[str, str]] = []  # (node_id, slug)
    for node_data in god_nodes_data:
        nid = node_data.get("id")
        if nid and nid in G:
            slug = _unique_slug(_safe_filename(node_data['label']))
            god_articles.append((nid, slug))
            resolver.setdefault(node_data['label'], slug)

    # Second pass: render and write each article with the full resolver in hand.
    for cid, nodes in communities.items():
        label = labels.get(cid, f"Community {cid}")
        article = _community_article(G, cid, nodes, label, labels, cohesion.get(cid), node_community, resolver)
        (out / f"{community_slugs[cid]}.md").write_text(article, encoding="utf-8")
        count += 1

    for nid, slug in god_articles:
        article = _god_node_article(G, nid, labels, node_community, resolver)
        (out / f"{slug}.md").write_text(article, encoding="utf-8")
        count += 1

    # Index
    (out / "index.md").write_text(
        _index_md(communities, labels, god_nodes_data, G.number_of_nodes(), G.number_of_edges(), resolver),
        encoding="utf-8",
    )

    return count
