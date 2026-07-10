"""Chronicle — diff two graph snapshots to see how a codebase's structure moved.

`prs.py` answers "what does *this* PR touch?". Chronicle generalizes that across
time: given two ``graph.json`` snapshots (two files, or the same file at two git
revisions), it reports how the *structure* changed — nodes and edges added or
removed, which god-nodes (high-degree hubs) emerged or vanished, and how the
community structure shifted. That surfaces architectural drift a line diff never
shows: a hub forming, a module fragmenting, a subsystem appearing.

The git path is deliberately cheap and API-free: graphify users commit
``graphify-out/graph.json``, so a historical snapshot is just
``git show <rev>:graphify-out/graph.json`` — no re-extraction, no model calls.

Communities are compared by ``community_name`` rather than numeric id, because
ids are reassigned on every rebuild while the human label ("auth", "py") is
stable enough to track a subsystem growing or splitting across versions.
"""
from __future__ import annotations

import json
from collections import Counter

import networkx as nx
from networkx.readwrite import json_graph


def load_graph_from_text(text: str) -> nx.Graph:
    """Parse a graph.json payload (edges- or links-keyed) into a DiGraph."""
    data = json.loads(text)
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    data = {**data, "directed": True}
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


def _label(G: nx.Graph, nid: str) -> str:
    return str(G.nodes[nid].get("label", nid))


def _god_node_ids(G: nx.Graph, top_n: int) -> list[str]:
    """Top-N node ids by degree (graphify's god-node definition)."""
    ranked = sorted(G.nodes(), key=lambda n: (-G.degree(n), str(n)))
    return ranked[:top_n]


def _edge_key(G: nx.Graph, u: str, v: str, data: dict) -> tuple[str, str, str]:
    return (str(u), str(v), str(data.get("relation", "")))


def _edge_set(G: nx.Graph) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, data in G.edges(data=True):
            out.add(_edge_key(G, u, v, data))
    else:
        for u, v, data in G.edges(data=True):
            out.add(_edge_key(G, u, v, data))
    return out


def _community_sizes(G: nx.Graph) -> Counter:
    sizes: Counter = Counter()
    for _nid, data in G.nodes(data=True):
        name = data.get("community_name")
        if name is None and data.get("community") is not None:
            name = f"#{data.get('community')}"
        if name is not None:
            sizes[str(name)] += 1
    return sizes


def diff_graphs(old: nx.Graph, new: nx.Graph, *, top_god: int = 15) -> dict:
    """Structural diff between two snapshots. Returns a JSON-friendly dict."""
    old_ids, new_ids = set(old.nodes()), set(new.nodes())
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids

    old_edges, new_edges = _edge_set(old), _edge_set(new)
    added_edges = new_edges - old_edges
    removed_edges = old_edges - new_edges

    old_gods, new_gods = _god_node_ids(old, top_god), _god_node_ids(new, top_god)
    emerged = [n for n in new_gods if n not in set(old_gods)]
    vanished = [n for n in old_gods if n not in set(new_gods)]

    old_sizes, new_sizes = _community_sizes(old), _community_sizes(new)
    appeared = sorted(set(new_sizes) - set(old_sizes))
    disappeared = sorted(set(old_sizes) - set(new_sizes))
    resized = []
    for name in sorted(set(old_sizes) & set(new_sizes)):
        delta = new_sizes[name] - old_sizes[name]
        if delta:
            resized.append({"name": name, "old": old_sizes[name], "new": new_sizes[name], "delta": delta})
    resized.sort(key=lambda r: (-abs(r["delta"]), r["name"]))

    return {
        "nodes": {
            "old_count": len(old_ids),
            "new_count": len(new_ids),
            "delta": len(new_ids) - len(old_ids),
            "added": sorted(
                ({"id": n, "label": _label(new, n)} for n in added_ids),
                key=lambda d: d["label"],
            ),
            "removed": sorted(
                ({"id": n, "label": _label(old, n)} for n in removed_ids),
                key=lambda d: d["label"],
            ),
        },
        "edges": {
            "old_count": len(old_edges),
            "new_count": len(new_edges),
            "delta": len(new_edges) - len(old_edges),
            "added": sorted(f"{u} --{r}--> {v}" for (u, v, r) in added_edges),
            "removed": sorted(f"{u} --{r}--> {v}" for (u, v, r) in removed_edges),
        },
        "god_nodes": {
            "top_n": top_god,
            "emerged": [{"id": n, "label": _label(new, n), "degree": new.degree(n)} for n in emerged],
            "vanished": [{"id": n, "label": _label(old, n), "degree": old.degree(n)} for n in vanished],
        },
        "communities": {
            "old_count": len(old_sizes),
            "new_count": len(new_sizes),
            "appeared": appeared,
            "disappeared": disappeared,
            "resized": resized,
        },
    }


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def format_diff(diff: dict, *, limit: int = 15) -> str:
    n, e, g, c = diff["nodes"], diff["edges"], diff["god_nodes"], diff["communities"]
    lines: list[str] = []
    lines.append("graphify chronicle — structural diff")
    lines.append("=" * 48)
    lines.append(
        f"Nodes: {n['old_count']} -> {n['new_count']} ({n['delta']:+d})   "
        f"Edges: {e['old_count']} -> {e['new_count']} ({e['delta']:+d})"
    )
    lines.append(
        f"Communities: {c['old_count']} -> {c['new_count']} "
        f"({len(c['appeared'])} appeared, {len(c['disappeared'])} disappeared)"
    )
    lines.append("")

    if g["emerged"]:
        lines.append("God-nodes emerged (new structural hubs):")
        for d in g["emerged"][:limit]:
            lines.append(f"  + {d['label']}  (degree {d['degree']})")
    if g["vanished"]:
        lines.append("God-nodes vanished:")
        for d in g["vanished"][:limit]:
            lines.append(f"  - {d['label']}  (was degree {d['degree']})")
    if g["emerged"] or g["vanished"]:
        lines.append("")

    if c["appeared"]:
        lines.append("Communities appeared: " + ", ".join(c["appeared"][:limit]))
    if c["disappeared"]:
        lines.append("Communities disappeared: " + ", ".join(c["disappeared"][:limit]))
    if c["resized"]:
        lines.append("Largest community shifts:")
        for r in c["resized"][:limit]:
            lines.append(f"  {r['name']}: {r['old']} -> {r['new']} ({r['delta']:+d})")
        lines.append("")

    lines.append(
        f"Detail: {_plural(len(n['added']), 'node')} added, "
        f"{_plural(len(n['removed']), 'node')} removed, "
        f"{_plural(len(e['added']), 'edge')} added, "
        f"{_plural(len(e['removed']), 'edge')} removed."
    )
    if n["added"]:
        lines.append("  new nodes: " + ", ".join(d["label"] for d in n["added"][:limit]) + (" …" if len(n["added"]) > limit else ""))
    if n["removed"]:
        lines.append("  gone nodes: " + ", ".join(d["label"] for d in n["removed"][:limit]) + (" …" if len(n["removed"]) > limit else ""))
    return "\n".join(lines)
