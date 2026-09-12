from __future__ import annotations
import json
import hashlib
import sys
from collections.abc import Sequence
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


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped,
    cross_repo_calls.
    Skipped=True means the source graph hasn't changed since last add.
    """
    batch = global_add_many([(source_path, repo_tag)])
    result = dict(batch["results"][0])
    result["cross_repo_calls"] = batch["cross_repo_calls"]
    return result


def global_add_many(sources: Sequence[tuple[Path, str]]) -> dict:
    """Add or update several project graphs in one pass over the global graph.

    ``sources`` is an ordered sequence of ``(source_path, repo_tag)`` composed in the given
    order, so a later unit's external-node dedup sees what earlier ones added -- the graph
    the same sequence of ``global_add`` calls produces.

    Returns ``{"results": [...], "cross_repo_calls": int}``, one result dict per input in
    input order with keys repo_tag / nodes_added / nodes_removed / skipped.
    ``cross_repo_calls`` counts the whole batch: the pass reads the finished graph, so the
    number does not divide over the units that made it.

    The global store is a process-shared read-modify-write resource. Callers that may
    update the same store concurrently must serialize those operations externally.
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph
    from graphify.security import check_graph_file_size_cap

    # Whatever cannot finish should fail before the first unit is composed, since a batch
    # that raises halfway leaves the units before it unwritten and their work wasted.
    tag_sources: dict[str, Path] = {}
    for source_path, repo_tag in sources:
        if not source_path.exists():
            raise FileNotFoundError(f"graph not found: {source_path}")
        if repo_tag in tag_sources:
            raise ValueError(
                f"repo tag '{repo_tag}' names two sources in one batch "
                f"({tag_sources[repo_tag]} and {source_path}); the second prunes the first. "
                f"Give one of them a different tag."
            )
        tag_sources[repo_tag] = source_path

    manifest = _load_manifest()
    results: list[dict] = []
    pending: list[tuple[int, Path, str, str]] = []
    for source_path, repo_tag in sources:
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
        skipped = existing.get("source_hash") == src_hash
        results.append({"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0,
                        "skipped": skipped})
        if not skipped:
            check_graph_file_size_cap(source_path)
            pending.append((len(results) - 1, source_path, repo_tag, src_hash))

    # Nothing changed: the global graph is never read or rewritten, which keeps a re-run over
    # an unchanged corpus as cheap as it is for a single unchanged unit.
    if not pending:
        return {"results": results, "cross_repo_calls": 0}

    G = _load_global_graph()
    for index, source_path, repo_tag, src_hash in pending:
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        try:
            src_G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            src_G = _jg.node_link_graph(data)

        # Prefix IDs for cross-project isolation, then drop this repo's stale nodes
        prefixed = prefix_graph_for_global(src_G, repo_tag)
        removed = prune_repo_from_graph(G, repo_tag)

        # Each unit keeps its own external-library stubs (no source_file). Merging
        # them by label makes stub ownership a function of merge order: the survivor
        # carries the first-merged repo's tag, fabricating cross-repo edges and
        # letting prune_repo_from_graph delete other repos' real edges with it.
        for node, node_data in prefixed.nodes(data=True):
            G.add_node(node, **node_data)
        for u, v, edge_data in prefixed.edges(data=True):
            G.add_edge(u, v, **edge_data)

        added = prefixed.number_of_nodes()
        results[index]["nodes_added"] = added
        results[index]["nodes_removed"] = removed
        manifest["repos"][repo_tag] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source_path.resolve()),
            "node_count": added,
            "edge_count": prefixed.number_of_edges(),
            "source_hash": src_hash,
        }
    # A member call parked on a caller node (#3152) may be answered by a repo
    # already in the global graph, or by this one for a repo added earlier. The
    # pass recomputes its own output, so one run over the composed batch lands
    # where a run per unit -- or a single merge-graphs of the same inputs -- would.
    from graphify.cross_repo_calls import link_cross_repo_member_calls

    cross_repo_calls = link_cross_repo_member_calls(G)
    _save_global_graph(G)
    _save_manifest(manifest)

    return {"results": results, "cross_repo_calls": cross_repo_calls}


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
