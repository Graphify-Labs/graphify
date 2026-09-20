from __future__ import annotations
import contextlib
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


@contextlib.contextmanager
def _global_store_lock():
    """Exclusive advisory lock around a read-modify-write cycle on the
    global graph store.

    global_add/global_remove each load the graph and manifest, mutate them
    in memory, then save both back. Two concurrent calls would both read
    the same pre-write snapshot, compute conflicting results from it, and
    the second save would silently discard the first's work entirely (not
    just a duplicated community id, which the narrower #3100 fix already
    closes). Blocks until acquired rather than failing, since a caller
    should wait its turn; released automatically if the process is killed
    (fcntl.flock), so no stale-lock cleanup is needed.

    No-op on platforms without fcntl (Windows) -- matching the same
    fallback already used by watch.py's per-repo rebuild lock, since a lost
    update there is a pre-existing risk this does not newly introduce.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return
    # Read _GLOBAL_DIR fresh rather than a module-level path computed from it
    # once at import time, so a caller (tests included) that points the
    # store elsewhere by rebinding _GLOBAL_DIR is honored here too.
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(_GLOBAL_DIR / ".global-graph.lock", "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


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


def _hash_file_streaming(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """SHA256 hash of path's content, read in bounded chunks.

    Unlike a single ``read_bytes()`` call, this never depends on the file's
    size for its own memory use, so it is safe to run even on a file that
    would fail the size cap for a full in-memory parse -- the cap protects
    against *parsing* an oversized payload, not against determining whether
    its content changed at all, which hashing alone never requires holding
    the whole file in memory to do.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


def global_add(source_path: Path, repo_tag: str) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped,
    cross_repo_calls.
    Skipped=True means the source graph hasn't changed since last add.
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph

    if not source_path.exists():
        raise FileNotFoundError(f"graph not found: {source_path}")

    with _global_store_lock():
        manifest = _load_manifest()
        existing = manifest["repos"].get(repo_tag, {})
        resolved_source_path = str(source_path.resolve())

        # A stat-only fast path, no read at all: if this SAME source path's
        # mtime and size exactly match what was recorded on the last
        # successful add, it is unchanged, full stop -- including when it is
        # (or has become) oversized, since an already-tracked, genuinely
        # untouched file must keep skipping rather than erroring on every
        # call once it or the configured cap crosses the threshold. The path
        # must match too: a repo_tag re-pointed at a genuinely different
        # file that happens to share the old file's mtime and size (a real
        # possibility with cp -p/rsync -a/checkout-preserved timestamps)
        # must never fast-skip on stat coincidence alone, or the store
        # silently keeps stale data with no warning at all. Anything else
        # (first add, the path/mtime/size differ, or an older manifest that
        # predates these fields) falls through to the cap check and a real
        # read below.
        st = source_path.stat()
        if (
            existing.get("source_path") == resolved_source_path
            and existing.get("source_mtime_ns") == st.st_mtime_ns
            and existing.get("source_size") == st.st_size
        ):
            return {"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0, "skipped": True,
                    "cross_repo_calls": 0, "shared_type_links": 0}

        # The cap is a stat-based check too (no read), and must run before
        # any FULL read of the file's bytes -- reading the whole thing first
        # (even just to hash it, as a single read_bytes() call would) defeats
        # the cap's purpose of failing fast before a multi-GiB file is
        # loaded into memory for parsing. But the fast path above cannot
        # catch every unchanged file: a manifest entry that predates the
        # mtime/size fields (every manifest written before this fix existed)
        # has no stat baseline to compare against, and would otherwise fall
        # straight through to the cap and error on an unchanged file that
        # merely became oversized, exactly the regression the fast path was
        # meant to close. So an oversized file gets one more chance: a
        # streaming hash (bounded memory regardless of size) against the
        # stored content hash, before finally raising the cap's own error
        # for a file that is both oversized and genuinely different.
        from graphify.security import check_graph_file_size_cap
        try:
            check_graph_file_size_cap(source_path)
        except ValueError as cap_error:
            if existing.get("source_hash") == _hash_file_streaming(source_path):
                return {"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0, "skipped": True,
                        "cross_repo_calls": 0, "shared_type_links": 0}
            raise cap_error

        # Hash and parse the SAME read of source_path, inside the lock.
        # Reading it twice at two different times (once to hash, once to
        # parse) would let a concurrent writer to source_path in between make
        # the recorded hash describe different bytes than what actually gets
        # imported below. Only reached once the cap has already passed, so
        # buffering the whole file here is safe.
        raw_bytes = source_path.read_bytes()
        src_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

        existing_path = existing.get("source_path", "")
        if existing_path and existing_path != resolved_source_path:
            print(
                f"[graphify global] warning: repo tag '{repo_tag}' previously pointed to "
                f"{existing_path!r}, now updating to {resolved_source_path!r}. "
                f"Use --as <tag> to give it a different name.",
                file=sys.stderr,
            )
        if existing.get("source_hash") == src_hash:
            # Content-hash fallback for a manifest entry that predates the
            # mtime/size fields above, or whose mtime changed without the
            # content actually changing.
            return {"repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0, "skipped": True,
                    "cross_repo_calls": 0, "shared_type_links": 0}

        data = json.loads(raw_bytes.decode("utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        try:
            src_G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            src_G = _jg.node_link_graph(data)

        # Load global graph and prune stale nodes for this repo, before prefixing
        # the incoming one: the offset below reads the store's community ids as
        # they stand once this repo's own stale entries are already gone, so
        # re-adding the same repo cannot inflate it forever.
        G = _load_global_graph()
        removed = prune_repo_from_graph(G, repo_tag)

        # Offset the incoming repo's community ids past every other repo's
        # already in the store (#3014, #3100): every graph.json numbers its own
        # communities from 0, and the CLI merge-graphs command already offsets
        # for exactly this reason, but the incremental add path here kept
        # prefixing each new repo's communities from 0 too, colliding with
        # whatever id another repo already occupied.
        community_offset = 0
        existing_cids = [
            d["community"] for _, d in G.nodes(data=True) if isinstance(d.get("community"), int)
        ]
        if existing_cids:
            community_offset = max(existing_cids) + 1

        # Prefix IDs for cross-project isolation
        prefixed = prefix_graph_for_global(src_G, repo_tag, community_offset=community_offset)

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
        # A member call parked on a caller node (#3152) may be answered by a repo
        # already in the global graph, or by this one for a repo added earlier. The
        # pass recomputes its own output, so adding repos one at a time lands where a
        # single merge-graphs of the same inputs would.
        from graphify.cross_repo_calls import link_cross_repo_member_calls

        cross_repo_calls = link_cross_repo_member_calls(G)

        # A type both this repo and an earlier one declare arrives as two
        # unconnected nodes, since every id is repo prefixed. The CLI batch
        # merge command already links them so a traversal can cross the repo
        # boundary (#3007); global_add never called this pass, so an
        # incrementally built store held zero same_type_as edges no matter how
        # many repos actually shared a type. Re-run over the whole store on
        # every add, same as the member call pass above: it only adds an edge
        # where none exists yet, so repeated calls across successive adds stay
        # cheap and cannot double an edge.
        from graphify.cross_repo_types import link_shared_type_declarations

        shared_type_links = link_shared_type_declarations(G)
        _save_global_graph(G)

        manifest["repos"][repo_tag] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "source_path": resolved_source_path,
            "node_count": added,
            "edge_count": prefixed.number_of_edges(),
            "source_hash": src_hash,
            "source_mtime_ns": st.st_mtime_ns,
            "source_size": st.st_size,
        }
        _save_manifest(manifest)

    return {"repo_tag": repo_tag, "nodes_added": added, "nodes_removed": removed,
            "skipped": False, "cross_repo_calls": cross_repo_calls,
            "shared_type_links": shared_type_links}


def global_remove(repo_tag: str) -> int:
    """Remove all nodes for repo_tag from the global graph. Returns count removed."""
    from graphify.build import prune_repo_from_graph

    with _global_store_lock():
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
