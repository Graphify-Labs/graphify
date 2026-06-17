from __future__ import annotations
import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from .store import GraphStore, DEFAULT_URI, open_store

_GLOBAL_DIR = Path.home() / ".graphify"
_GLOBAL_MANIFEST = _GLOBAL_DIR / "global-manifest.json"
_GLOBAL_NAME = "graphify_global"


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


def _load_global_graph(uri: str = DEFAULT_URI) -> GraphStore:
    """The global graph is a dedicated named FalkorDB graph."""
    return GraphStore(graph_name=_GLOBAL_NAME, uri=uri)


def _store_content_hash(G) -> str:
    """Stable content hash of a store's nodes + edges (replaces file hashing)."""
    h = hashlib.sha256()
    for nid, attrs in G.nodes(data=True):
        h.update(json.dumps([nid, attrs], sort_keys=True, default=str).encode("utf-8"))
    for u, v, attrs in G.edges(data=True):
        h.update(json.dumps([u, v, attrs], sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:16]


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped.
    Skipped=True means the source graph hasn't changed since last add.
    """
    from graphify.build import prune_repo_from_graph

    # Load source graph from its FalkorDB store (source_path is the legacy
    # graph.json location; its parent dir holds the FalkorDB pointer).
    out_dir = source_path.parent if source_path.suffix else source_path
    src_G = open_store(out_dir, create=False)
    if src_G.number_of_nodes() == 0:
        raise FileNotFoundError(f"graph not found for: {source_path}")

    manifest = _load_manifest()
    src_hash = _store_content_hash(src_G)

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

    # Load global graph and prune stale nodes for this repo
    G = _load_global_graph()
    removed = prune_repo_from_graph(G, repo_tag)

    # Merge external-library nodes (no source_file) by label to avoid duplication
    external_labels = {
        d.get("label", ""): n
        for n, d in G.nodes(data=True)
        if not d.get("source_file") and d.get("label")
    }
    # Prefix source IDs for cross-project isolation. External-library nodes
    # (no source_file) that already exist in the global graph by label are
    # remapped onto the existing global node so incident edges are rewired
    # instead of dropped — preserves cross-repo connectivity.
    remap: dict[str, str] = {}
    prefixed_nodes = []
    for nid, data in src_G.nodes(data=True):
        pid = f"{repo_tag}::{nid}"
        if not data.get("source_file") and data.get("label") in external_labels:
            remap[pid] = external_labels[data["label"]]
            continue
        attrs = dict(data)
        attrs["repo"] = repo_tag
        attrs.setdefault("local_id", nid)
        prefixed_nodes.append((pid, attrs))
    prefixed_edges = []
    n_src_edges = 0
    for u, v, data in src_G.edges(data=True):
        n_src_edges += 1
        pu = remap.get(f"{repo_tag}::{u}", f"{repo_tag}::{u}")
        pv = remap.get(f"{repo_tag}::{v}", f"{repo_tag}::{v}")
        if pu == pv:  # don't introduce self-loops via remapping
            continue
        prefixed_edges.append((pu, pv, dict(data)))

    G.add_nodes_from(prefixed_nodes)
    G.add_edges_from(prefixed_edges)

    added = len(prefixed_nodes)
    manifest["repos"][repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path.resolve()),
        "node_count": added,
        "edge_count": n_src_edges,
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

    del manifest["repos"][repo_tag]
    _save_manifest(manifest)
    return removed


def global_list() -> dict:
    """Return the manifest repos dict."""
    return _load_manifest().get("repos", {})


def global_path() -> str:
    """Name of the global FalkorDB graph (replaces the old global-graph.json path)."""
    return _GLOBAL_NAME
