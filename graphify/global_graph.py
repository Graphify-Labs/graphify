from __future__ import annotations
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph as _jg

_GLOBAL_DIR = Path.home() / ".graphify"
_GLOBAL_GRAPH = _GLOBAL_DIR / "global-graph.json"
_GLOBAL_MANIFEST = _GLOBAL_DIR / "global-manifest.json"


def _load_manifest() -> dict:
    if _GLOBAL_MANIFEST.exists():
        try:
            return json.loads(_GLOBAL_MANIFEST.read_text(encoding="utf-8"))
        except Exception as exc:
            # Don't silently wipe the user's manifest on a parse error: that
            # deletes every tracked repo. Back the bad file up and surface the
            # error so the user can recover or report it.
            backup = _GLOBAL_MANIFEST.with_suffix(
                _GLOBAL_MANIFEST.suffix + f".corrupt.{int(datetime.now(timezone.utc).timestamp())}"
            )
            try:
                _GLOBAL_MANIFEST.rename(backup)
                print(
                    f"[graphify global] manifest at {_GLOBAL_MANIFEST} failed to parse ({exc}); "
                    f"moved to {backup} and starting fresh. Restore from the backup if this was "
                    f"unexpected.",
                    file=sys.stderr,
                )
            except Exception as rename_exc:
                print(
                    f"[graphify global] manifest at {_GLOBAL_MANIFEST} failed to parse ({exc}) "
                    f"and could not be backed up ({rename_exc}). Starting fresh.",
                    file=sys.stderr,
                )
    return {"version": 1, "repos": {}}


def _save_manifest(manifest: dict) -> None:
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    from graphify.paths import write_json_atomic
    write_json_atomic(_GLOBAL_MANIFEST, manifest, indent=2)


def _load_global_graph() -> nx.Graph:
    if _GLOBAL_GRAPH.exists():
        from graphify.security import check_graph_file_size_cap
        check_graph_file_size_cap(_GLOBAL_GRAPH)
        data = json.loads(_GLOBAL_GRAPH.read_text(encoding="utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        try:
            return _jg.node_link_graph(data, edges="links")
        except TypeError:
            return _jg.node_link_graph(data)
    return nx.Graph()


def _save_global_graph(G: nx.Graph) -> None:
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = _jg.node_link_data(G, edges="links")
    except TypeError:
        data = _jg.node_link_data(G)
    from graphify.paths import write_json_atomic
    write_json_atomic(_GLOBAL_GRAPH, data, indent=2)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def global_add(source_path: Path, repo_tag: str, *, multigraph: bool = False) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped.
    Skipped=True means the source graph hasn't changed since last add.
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph

    if not source_path.exists():
        raise FileNotFoundError(f"graph not found: {source_path}")

    manifest = _load_manifest()
    src_hash = _file_hash(source_path)

    existing = manifest["repos"].get(repo_tag, {})
    existing_path = existing.get("source_path", "")
    if existing_path and existing_path != str(source_path.resolve()):
        print(
            f"[graphify global] warning: repo tag '{repo_tag}' previously pointed to "
            f"{existing_path!r}, now updating to {str(source_path.resolve())!r}. "
            f"Use --as <tag> to give it a different name.",
            file=sys.stderr,
        )
    if existing.get("source_hash") == src_hash:
        return {"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0, "skipped": True}

    # Load source graph
    from graphify.security import check_graph_file_size_cap
    check_graph_file_size_cap(source_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        src_G = _jg.node_link_graph(data, edges="links")
    except TypeError:
        src_G = _jg.node_link_graph(data)
    if src_G.is_multigraph() and not multigraph:
        raise ValueError(
            "source graph is a multigraph; pass --multigraph to preserve "
            "parallel relations in the global graph"
        )

    # Prefix IDs for cross-project isolation
    prefixed = prefix_graph_for_global(src_G, repo_tag)

    # Load global graph and prune stale nodes for this repo
    G = _load_global_graph()
    if multigraph and not isinstance(G, nx.MultiDiGraph):
        from graphify.build import canonical_edge_key

        upgraded = nx.MultiDiGraph()
        upgraded.add_nodes_from(G.nodes(data=True))
        for source, target, attrs in G.edges(data=True):
            copied = dict(attrs)
            true_source = copied.get("_src", source)
            true_target = copied.get("_tgt", target)
            upgraded.add_edge(
                true_source,
                true_target,
                key=canonical_edge_key(str(true_source), str(true_target), copied),
                **copied,
            )
        G = upgraded
    removed = prune_repo_from_graph(G, repo_tag)

    # Merge external-library nodes (no source_file) by label to avoid duplication
    external_labels = {
        d.get("label", ""): n
        for n, d in G.nodes(data=True)
        if not d.get("source_file") and d.get("label")
    }
    # Map each deduplicated external onto the existing global node so that
    # edges incident to it can be rewired instead of dropped.
    remap = {}
    for node, data in prefixed.nodes(data=True):
        if not data.get("source_file") and data.get("label") in external_labels:
            remap[node] = external_labels[data["label"]]

    # Compose: add prefixed nodes (except deduplicated externals) into global graph
    for node, data in prefixed.nodes(data=True):
        if node not in remap:
            G.add_node(node, **data)
    if G.is_multigraph():
        if prefixed.is_multigraph():
            rows = prefixed.edges(keys=True, data=True)
        else:
            from graphify.build import canonical_edge_key

            rows = (
                (u, v, canonical_edge_key(str(u), str(v), attrs), attrs)
                for u, v, attrs in prefixed.edges(data=True)
            )
        for u, v, key, data in rows:
            u = remap.get(u, u)
            v = remap.get(v, v)
            if u != v:
                G.add_edge(u, v, key=key, **data)
    else:
        for u, v, data in prefixed.edges(data=True):
            u = remap.get(u, u)
            v = remap.get(v, v)
            if u != v:  # don't introduce self-loops via remapping
                G.add_edge(u, v, **data)

    added = prefixed.number_of_nodes() - len(remap)
    _save_global_graph(G)

    manifest["repos"][repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path.resolve()),
        "node_count": added,
        "edge_count": prefixed.number_of_edges(),
        "source_hash": src_hash,
    }
    _save_manifest(manifest)

    return {"repo_tag": repo_tag, "nodes_added": added, "nodes_removed": removed, "skipped": False}


def global_remove(repo_tag: str) -> int:
    """Remove all nodes for repo_tag from the global graph. Returns count removed."""
    from graphify.build import prune_repo_from_graph

    manifest = _load_manifest()
    if repo_tag not in manifest["repos"]:
        raise KeyError(f"repo '{repo_tag}' not in global graph")

    G = _load_global_graph()
    removed = prune_repo_from_graph(G, repo_tag)
    _save_global_graph(G)

    del manifest["repos"][repo_tag]
    _save_manifest(manifest)
    return removed


def global_list() -> dict:
    """Return the manifest repos dict."""
    return _load_manifest().get("repos", {})


def global_path() -> Path:
    return _GLOBAL_GRAPH
