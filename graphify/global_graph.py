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


def _read_source_graph(source_path: Path) -> nx.Graph:
    """Load a project graph.json from disk, size-capped."""
    from graphify.security import check_graph_file_size_cap

    check_graph_file_size_cap(source_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    try:
        return _jg.node_link_graph(data, edges="links")
    except TypeError:
        return _jg.node_link_graph(data)


def _scan_graph(G: nx.Graph) -> tuple[dict, set]:
    """One pass over G returning (external label index, tags with nodes present).

    Both are needed per batch and both are whole-graph scans, so they share a pass:
    the point of the batch API is that a whole-graph cost is paid once, and adding
    a second scan to support rollback would chip away at exactly that.
    """
    external_labels: dict = {}
    repo_tags: set = set()
    for node, data in G.nodes(data=True):
        if not data.get("source_file") and data.get("label"):
            external_labels.setdefault(data["label"], node)
        repo = data.get("repo")
        if repo:
            repo_tags.add(repo)
    return external_labels, repo_tags


def _external_label_index(G: nx.Graph) -> dict:
    """Map label -> node id for every external (source_file-less) node in G.

    External library nodes are deduplicated by label so that `requests` imported
    by five repos is one node, not five. Built once per batch and kept current as
    each repo merges, so a repo can dedup against an external contributed by an
    earlier repo in the same batch exactly as it would if that repo had been
    added by its own `global add` call.
    """
    return {
        d.get("label", ""): n
        for n, d in G.nodes(data=True)
        if not d.get("source_file") and d.get("label")
    }


def _snapshot_repo(G: nx.Graph, repo_tag: str) -> tuple[list, list]:
    """Capture repo_tag's nodes and their incident edges, for rollback.

    Attribute dicts are copied: the originals are handed to `add_node`/`add_edge`
    on restore and would otherwise stay shared with the live graph.
    """
    nodes = [(n, dict(d)) for n, d in G.nodes(data=True) if d.get("repo") == repo_tag]
    if not nodes:
        return [], []
    ids = [n for n, _ in nodes]
    edges = [(u, v, dict(d)) for u, v, d in G.edges(ids, data=True)]
    return nodes, edges


def _restore_repo(G: nx.Graph, repo_tag: str, snapshot: tuple[list, list]) -> None:
    """Put repo_tag back as it was at `snapshot`, dropping whatever replaced it."""
    nodes, edges = snapshot
    G.remove_nodes_from(
        [n for n, d in G.nodes(data=True) if d.get("repo") == repo_tag]
    )
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)


def _merge_one(G: nx.Graph, prefixed: nx.Graph, external_labels: dict) -> int:
    """Compose one prefixed repo graph into G. Returns nodes added.

    `external_labels` is read and updated in place: externals this repo
    introduces become dedup targets for repos merged after it, which is what
    keeps a batched merge identical to the same repos added one at a time.
    """
    # Map each deduplicated external onto the existing global node so that
    # edges incident to it can be rewired instead of dropped.
    remap = {}
    for node, data in prefixed.nodes(data=True):
        if not data.get("source_file") and data.get("label") in external_labels:
            remap[node] = external_labels[data["label"]]

    # Compose: add prefixed nodes (except deduplicated externals) into G
    for node, data in prefixed.nodes(data=True):
        if node not in remap:
            G.add_node(node, **data)
            if not data.get("source_file") and data.get("label"):
                external_labels.setdefault(data["label"], node)
    for u, v, data in prefixed.edges(data=True):
        u = remap.get(u, u)
        v = remap.get(v, v)
        if u != v:  # don't introduce self-loops via remapping
            G.add_edge(u, v, **data)

    return prefixed.number_of_nodes() - len(remap)


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped,
    cross_repo_calls.
    Skipped=True means the source graph hasn't changed since last add.

    A thin wrapper over :func:`global_add_many` so the one-repo and many-repo
    paths cannot drift apart: a change to the merge semantics cannot land in one
    and miss the other.
    """
    batch = global_add_many([(source_path, repo_tag)])
    result = dict(batch["results"][0])
    result["cross_repo_calls"] = batch["cross_repo_calls"]
    if result.get("error") is None:
        result.pop("error", None)
    return result


def global_add_many(sources, on_error: str = "abort") -> dict:
    """Add or update several project graphs in one pass over the global graph (#3438).

    ``sources`` is an ordered sequence of ``(source_path, repo_tag)``, composed in
    the order given.

    Returns ``{"results": [...], "cross_repo_calls": int, "saved": bool}``, with one
    result per input in input order carrying repo_tag / nodes_added / nodes_removed
    / skipped / error. ``error`` is None unless that unit failed under
    ``on_error="skip"``, in which case it is the failure as a string.

    Registering K repos one at a time costs O(K^2): every call re-reads,
    re-resolves and re-serializes a global graph that grows with each unit, so the
    K-th call pays for the K-1 already in it. Only composing a unit needs the graph
    in the state that unit arrives at -- the read, the cross-repo pass and the write
    depend on the batch as a whole, so a batch pays each of them once.

    The result is the graph the same sequence of :func:`global_add` calls produces.
    Two things make that true and are easy to break:

    * External stubs dedup by label against what is *already composed*, so a later
      unit must see the stubs earlier units in the same batch contributed. The
      index is threaded through the loop rather than rebuilt per unit -- rebuilding
      it is correct but rescans the whole graph K times, reintroducing a quadratic
      term in the very function that exists to remove one.
    * The cross-repo call pass recomputes its own output from scratch, so running
      it once over the finished batch lands where running it per unit would.

    ``on_error`` selects what a unit that fails to load does to the rest:

    ``"abort"`` (default)
        Nothing is written. The store is left exactly as it was, so a batch either
        applies whole or not at all.
    ``"skip"``
        The failing unit is recorded with an ``error`` and every other unit is
        committed -- the partial-success behaviour of running ``global add`` once
        per repo, which a batch otherwise silently gives up.
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph
    from graphify.security import check_graph_file_size_cap

    if on_error not in ("abort", "skip"):
        raise ValueError(f"on_error must be 'abort' or 'skip', got {on_error!r}")

    sources = [(Path(source_path), repo_tag) for source_path, repo_tag in sources]

    # Whatever can be rejected from the inputs alone is rejected before anything is
    # composed, so a doomed batch does not do half its work first.
    tag_sources: dict[str, Path] = {}
    for source_path, repo_tag in sources:
        if not source_path.exists():
            raise FileNotFoundError(f"graph not found: {source_path}")
        if repo_tag in tag_sources:
            # The second would prune the first, reporting nodes for a repo whose
            # graph is not the one in the store. Refuse rather than compose a lie.
            raise ValueError(
                f"repo tag '{repo_tag}' names two sources in one batch "
                f"({tag_sources[repo_tag]} and {source_path}); the second prunes the "
                f"first. Give one of them a different tag."
            )
        tag_sources[repo_tag] = source_path

    manifest = _load_manifest()

    results: list[dict] = []
    pending: list[tuple[int, Path, str, str]] = []
    for source_path, repo_tag in sources:
        # The cap is enforced before the file is read. _file_hash reads the whole
        # file, so hashing first would pull an oversized graph into memory to
        # compute a hash for a unit that is about to be rejected for its size --
        # defeating the point of having a cap (thanks @copilot).
        try:
            check_graph_file_size_cap(source_path)
        except Exception as exc:
            if on_error == "abort":
                raise
            results.append({"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0,
                            "skipped": False, "error": f"{type(exc).__name__}: {exc}"})
            continue
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
                        "skipped": skipped, "error": None})
        if not skipped:
            pending.append((len(results) - 1, source_path, repo_tag, src_hash))

    # Nothing changed: the global graph is never read or rewritten. Loading it only
    # to discover there is nothing to do costs a full deserialize and a full write
    # of identical bytes.
    if not pending:
        return {"results": results, "cross_repo_calls": 0, "saved": False}

    # Load once.
    G = _load_global_graph()
    external_labels, known_tags = _scan_graph(G)

    composed = 0
    for index, source_path, repo_tag, src_hash in pending:
        # The whole unit is guarded, not just the read. A unit prunes before it
        # merges, so a failure after that point leaves the repo removed but not
        # replaced -- and under "skip" the batch would go on to save that. The
        # unit is restored to its pre-prune state before the next one runs.
        # (Rollback approach from @ROHIT8759's work on the same issue.)
        snapshot: tuple[list, list] | None = None
        try:
            src_G = _read_source_graph(source_path)

            # Prefix IDs for cross-project isolation, then drop this repo's stale nodes
            prefixed = prefix_graph_for_global(src_G, repo_tag)
            # Only a repo already in the store can be half-pruned, and the manifest
            # says which those are -- so the common add-a-new-repo path pays no
            # scan at all, and the snapshot cost falls only on replacements.
            snapshot = _snapshot_repo(G, repo_tag) if repo_tag in known_tags else ([], [])
            removed = prune_repo_from_graph(G, repo_tag)
            if removed:
                # Pruning can delete external stubs the previous revision of this
                # repo owned, and a stale index would remap a later unit's edge
                # onto a node no longer in the graph. Only a prune that removed
                # something can invalidate it, so this is not paid on the common
                # add-new-repo path.
                external_labels = _external_label_index(G)

            results[index]["nodes_added"] = _merge_one(G, prefixed, external_labels)
            results[index]["nodes_removed"] = removed
        except Exception as exc:
            if snapshot is not None:
                # Undo this unit's prune/merge so the graph carries the repo's
                # previous revision rather than a half-applied one.
                _restore_repo(G, repo_tag, snapshot)
                external_labels = _external_label_index(G)
            if on_error == "abort":
                # Nothing is saved on this path, so the store is untouched
                # regardless -- the rollback keeps the in-memory graph honest for
                # any caller that catches this and carries on.
                raise
            results[index]["error"] = f"{type(exc).__name__}: {exc}"
            results[index]["nodes_added"] = 0
            results[index]["nodes_removed"] = 0
            continue

        composed += 1
        manifest["repos"][repo_tag] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source_path.resolve()),
            "node_count": results[index]["nodes_added"],
            "edge_count": prefixed.number_of_edges(),
            "source_hash": src_hash,
        }

    if not composed:
        # Every pending unit failed under on_error="skip". There is nothing to
        # write, and rewriting the store with an unchanged graph would only risk
        # turning a read failure into a write failure.
        return {"results": results, "cross_repo_calls": 0, "saved": False}

    # A member call parked on a caller node (#3152) may be answered by a repo
    # already in the global graph, or by one composed in this same batch. The pass
    # recomputes its own output, so one run over the composed batch lands where a
    # run per unit -- or a single merge-graphs of the same inputs -- would.
    from graphify.cross_repo_calls import link_cross_repo_member_calls

    cross_repo_calls = link_cross_repo_member_calls(G)

    # Save once. The graph goes first: a crash between the two writes then leaves
    # nodes the manifest does not list, which the next add heals by pruning the tag
    # and recomposing it. The reverse order strands a recorded hash whose nodes are
    # absent, and every later add skips the repo -- a silent permanent hole.
    _save_global_graph(G)
    _save_manifest(manifest)

    return {"results": results, "cross_repo_calls": cross_repo_calls, "saved": True}


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
