from __future__ import annotations
import collections
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
    _GLOBAL_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
    _GLOBAL_GRAPH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _stitch_federation(G: nx.Graph) -> int:
    """Link Apollo Federation entities across repos in the global graph.

    The SDL extractor tags entity types with ``federation='entity'`` (the service
    that owns ``type X @key``) or ``federation='extends'`` (a service that
    ``extend type X @key`` references it). Same entity name in two repos = the
    same federated entity, so each reference gets a ``federation_key`` edge to the
    owner. Idempotent: prior ``federation_key`` edges are dropped first, so it is
    safe to re-run after every ``global_add``.
    """
    stale = [(u, v) for u, v, d in G.edges(data=True)
             if d.get("relation") == "federation_key"]
    G.remove_edges_from(stale)

    origins: dict[str, list[str]] = collections.defaultdict(list)
    refs: dict[str, list[str]] = collections.defaultdict(list)
    for nid, d in G.nodes(data=True):
        if d.get("type") != "gql_entity":
            continue
        name = str(d.get("label", "")).split(" ", 1)[0]
        if not name:
            continue
        if d.get("federation") == "entity":
            origins[name].append(nid)
        elif d.get("federation") == "extends":
            refs[name].append(nid)

    added = 0
    for name, ref_ids in refs.items():
        for ref in ref_ids:
            ref_repo = G.nodes[ref].get("repo")
            for origin in origins.get(name, []):
                if G.nodes[origin].get("repo") == ref_repo:
                    continue
                G.add_edge(ref, origin, relation="federation_key", confidence="EXTRACTED",
                           confidence_score=1.0, source_file="<federation:@key>", weight=1.0)
                added += 1
    return added


def _stitch_gql_calls(G: nx.Graph) -> int:
    """Link GraphQL operation *call sites* to the operations they invoke, across
    repos, in the global graph.

    The call-site extractor tags each ``gql`...` `` / ``graphql:"..."`` usage as a
    ``gql_call`` node carrying ``op_name``; the SDL extractor owns the matching
    ``gql_operation`` in whatever service defines the schema. A frontend calling
    a backend mutation is the common cross-repo case, so each ``gql_call`` gets a
    ``calls`` edge to the operation node of the same name. With this edge,
    ``graphify affected "<operation>"`` reverse-traverses to every consumer a
    backend change would affect. Idempotent: prior ``calls`` edges are dropped
    first, so it is safe to re-run after every ``global_add``.
    """
    stale = [(u, v) for u, v, d in G.edges(data=True)
             if d.get("relation") == "calls"]
    G.remove_edges_from(stale)

    ops_by_name: dict[str, list[str]] = collections.defaultdict(list)
    calls_by_name: dict[str, list[str]] = collections.defaultdict(list)
    for nid, d in G.nodes(data=True):
        t = d.get("type")
        if t == "gql_operation":
            name = str(d.get("label", "")).split(" ", 1)[0]
            if name:
                ops_by_name[name].append(nid)
        elif t == "gql_call":
            name = str(d.get("op_name") or d.get("label", ""))
            if name:
                calls_by_name[name].append(nid)

    added = 0
    for name, call_ids in calls_by_name.items():
        targets = ops_by_name.get(name)
        if not targets:
            continue
        for call in call_ids:
            for op in targets:
                if call == op:
                    continue
                G.add_edge(call, op, relation="calls", confidence="INFERRED",
                           confidence_score=0.8, source_file="<gql:call-site>", weight=1.0)
                added += 1
    return added


def global_add(source_path: Path, repo_tag: str) -> dict:
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

    # Prefix IDs for cross-project isolation
    prefixed = prefix_graph_for_global(src_G, repo_tag)

    # Load global graph and prune stale nodes for this repo
    G = _load_global_graph()
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
    for u, v, data in prefixed.edges(data=True):
        u = remap.get(u, u)
        v = remap.get(v, v)
        if u != v:  # don't introduce self-loops via remapping
            G.add_edge(u, v, **data)

    added = prefixed.number_of_nodes() - len(remap)

    # Re-stitch cross-repo federation @key links now that this repo's entities
    # are present (idempotent — recomputed over the whole graph each add).
    _stitch_federation(G)
    # Link GraphQL call sites to the operations they invoke across repos
    # (frontend -> backend mutation); idempotent, same rationale.
    _stitch_gql_calls(G)

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
