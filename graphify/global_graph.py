"""Cross-project aggregation backed exclusively by embedded Helix."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .build import prefix_graph_for_global, prune_repo_from_graph
from .helix.model import EdgeData, GraphBuildData, NodeData
from .helix.persistence import DEFAULT_GLOBAL_STORE, HelixEmbeddedStore
from .helix.state import new_state


def _project_store(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.name == "graph.helix":
        store = candidate
    elif (candidate / "graph.helix").is_dir():
        store = candidate / "graph.helix"
    else:
        store = candidate / "graphify-out" / "graph.helix"
    if not store.is_dir():
        if candidate.suffix.lower() == ".json" or candidate.is_file():
            raise ValueError(
                "legacy JSON graphs are obsolete; rebuild the project and pass its graph.helix store"
            )
        raise FileNotFoundError(f"Helix store not found: {store}")
    return store


def _load_global() -> tuple[GraphBuildData, dict]:
    if not DEFAULT_GLOBAL_STORE.is_dir():
        return GraphBuildData(), new_state(build={"kind": "global-aggregate"})
    with HelixEmbeddedStore(DEFAULT_GLOBAL_STORE, read_only=True) as store:
        loaded = store.load()
    return GraphBuildData.from_native(loaded.graph), copy.deepcopy(dict(loaded.state))


def _save_global(graph: GraphBuildData, state: dict) -> None:
    with HelixEmbeddedStore(DEFAULT_GLOBAL_STORE) as store:
        store.save_generation(graph, state)
        store.verify()


def _repos(state: dict) -> dict:
    global_state = state.setdefault("global", {})
    return global_state.setdefault("repos", {})


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or replace one project's active Helix generation."""
    source = _project_store(source_path)
    with HelixEmbeddedStore(source, read_only=True) as store:
        loaded = store.load()
    source_generation = loaded.generation
    graph, state = _load_global()
    repos = _repos(state)
    existing = repos.get(repo_tag, {})
    if (
        existing.get("source_path") == str(source)
        and existing.get("source_generation") == source_generation
    ):
        return {
            "repo_tag": repo_tag,
            "nodes_added": 0,
            "nodes_removed": 0,
            "skipped": True,
        }

    removed = prune_repo_from_graph(graph, repo_tag)
    prefixed = prefix_graph_for_global(GraphBuildData.from_native(loaded.graph), repo_tag)

    external_labels = {
        node.attributes.get("label"): node.id
        for node in graph.nodes
        if not node.attributes.get("source_file") and node.attributes.get("label")
    }
    remap = {
        node.id: external_labels[node.attributes.get("label")]
        for node in prefixed.nodes
        if not node.attributes.get("source_file")
        and node.attributes.get("label") in external_labels
    }
    graph.nodes.extend(
        NodeData(node.id, dict(node.attributes))
        for node in prefixed.nodes
        if node.id not in remap
    )
    graph.edges.extend(
        EdgeData(
            remap.get(edge.source, edge.source),
            remap.get(edge.target, edge.target),
            dict(edge.attributes),
            edge.key,
        )
        for edge in prefixed.edges
        if remap.get(edge.source, edge.source) != remap.get(edge.target, edge.target)
    )
    added = prefixed.node_count - len(remap)
    repos[repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source),
        "source_generation": source_generation,
        "node_count": added,
        "edge_count": prefixed.edge_count,
    }
    _save_global(graph, state)
    return {
        "repo_tag": repo_tag,
        "nodes_added": added,
        "nodes_removed": removed,
        "skipped": False,
    }


def global_remove(repo_tag: str) -> int:
    graph, state = _load_global()
    repos = _repos(state)
    if repo_tag not in repos:
        raise KeyError(f"repo '{repo_tag}' not in global graph")
    removed = prune_repo_from_graph(graph, repo_tag)
    del repos[repo_tag]
    _save_global(graph, state)
    return removed


def global_list() -> dict:
    _, state = _load_global()
    return dict(_repos(state))


def global_path() -> Path:
    """Return the configured native global-store directory."""
    return DEFAULT_GLOBAL_STORE


def aggregate(
    project_stores: Iterable[str | Path],
    output: str | Path = DEFAULT_GLOBAL_STORE,
) -> Path:
    """Create an aggregate in one atomic generation."""
    combined = GraphBuildData()
    sources: list[dict] = []
    tags: dict[str, int] = {}
    for raw_path in project_stores:
        path = _project_store(raw_path)
        with HelixEmbeddedStore(path, read_only=True) as store:
            loaded = store.load()
        base = path.parent.parent.name or "project"
        tags[base] = tags.get(base, 0) + 1
        repo = base if tags[base] == 1 else f"{base}-{tags[base]}"
        prefixed = prefix_graph_for_global(GraphBuildData.from_native(loaded.graph), repo)
        combined.nodes.extend(prefixed.nodes)
        combined.edges.extend(prefixed.edges)
        sources.append({
            "repository": repo,
            "store": str(path),
            "generation": loaded.generation,
        })
    destination = Path(output).expanduser().resolve()
    with HelixEmbeddedStore(destination) as store:
        store.save_generation(
            combined,
            new_state(build={"kind": "global-aggregate", "sources": sources}),
        )
        store.verify()
    return destination


__all__ = ["aggregate", "global_add", "global_list", "global_path", "global_remove"]
