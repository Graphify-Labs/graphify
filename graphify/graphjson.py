"""Plain-dict helpers for the node-link graph.json export artifact.

FalkorDB is the source of truth, but graphify still emits a ``graph.json``
node-link snapshot (and the git merge-driver / ``merge-graphs`` commands operate
on those artifacts). These helpers union and prefix node-link dicts directly,
without NetworkX.

A node-link dict looks like::

    {"directed": true, "multigraph": false, "graph": {},
     "nodes": [{"id": ..., ...}, ...],
     "links": [{"source": ..., "target": ..., "relation": ...}, ...]}
"""
from __future__ import annotations

import json
from pathlib import Path


def load_node_link(path, *, max_bytes: int | None = None) -> dict:
    """Read a node-link graph.json, normalizing the edges key to ``links``."""
    p = Path(path)
    if max_bytes is not None:
        size = p.stat().st_size
        if size > max_bytes:
            raise RuntimeError(f"graph.json {p} is {size} bytes, exceeds {max_bytes}-byte cap")
    data = json.loads(p.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    data.setdefault("nodes", [])
    data.setdefault("links", [])
    return data


def _edge_key(e: dict):
    return (e.get("source"), e.get("target"), e.get("relation"))


def merge_node_link(graphs: list[dict], *, directed: bool | None = None) -> dict:
    """Union several node-link dicts. Later graphs win on node/edge attr conflicts.

    ``directed`` sets the merged graph's flag. None (the default) inherits the
    first input's, so merging two versions of the same graph round-trips. The
    cross-repo `merge-graphs` view passes False: per-repo graphs are written by
    different extract paths and may disagree on directedness, and the combined
    view is undirected — what the old nx.compose path produced by normalizing
    every input to a plain Graph (#1606).
    """
    nodes: dict = {}
    edges: dict = {}
    for g in graphs:
        for n in g.get("nodes", []):
            nid = n.get("id")
            if nid is None:
                continue
            nodes[nid] = {**nodes.get(nid, {}), **n}
        for e in g.get("links", []):
            edges[_edge_key(e)] = e
    if directed is None:
        directed = bool(graphs[0].get("directed", True)) if graphs else True
    return {
        "directed": directed,
        "multigraph": False,
        "graph": {},
        "nodes": list(nodes.values()),
        "links": list(edges.values()),
    }


def prefix_node_link(data: dict, repo_tag: str) -> dict:
    """Prefix every node id with ``repo_tag::`` and rewrite edge endpoints.

    Mirrors build.prefix_graph_for_global for the JSON artifact: sets ``repo`` and
    ``local_id`` on each node so the original id is recoverable.
    """
    def pfx(x):
        return f"{repo_tag}::{x}"

    nodes = []
    for n in data.get("nodes", []):
        nid = n.get("id")
        nn = dict(n)
        nn["id"] = pfx(nid)
        nn["repo"] = repo_tag
        nn.setdefault("local_id", nid)
        nodes.append(nn)
    links = []
    for e in data.get("links", []):
        ee = dict(e)
        ee["source"] = pfx(e.get("source"))
        ee["target"] = pfx(e.get("target"))
        links.append(ee)
    return {"directed": True, "multigraph": False, "graph": {}, "nodes": nodes, "links": links}


def to_node_link(G) -> dict:
    """Build a node-link dict from a GraphStore/MemGraph (drops internal `_` keys)."""
    nodes = []
    for nid, attrs in G.nodes(data=True):
        nd = {k: v for k, v in attrs.items() if not k.startswith("_")}
        nd["id"] = nid
        nodes.append(nd)
    links = []
    for u, v, attrs in G.edges(data=True):
        ld = {k: val for k, val in attrs.items() if not k.startswith("_")}
        ld["source"] = u
        ld["target"] = v
        links.append(ld)
    return {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": nodes,
        "links": links,
        "hyperedges": getattr(G, "graph", {}).get("hyperedges", []),
    }


def node_count(data: dict) -> int:
    return len(data.get("nodes", []))


def edge_count(data: dict) -> int:
    return len(data.get("links", []))
