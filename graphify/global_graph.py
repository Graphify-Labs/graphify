from __future__ import annotations
import contextlib
import json
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph as _jg

_GLOBAL_DIR = Path.home() / ".graphify"
_GLOBAL_GRAPH = _GLOBAL_DIR / "global-graph.json"
_GLOBAL_MANIFEST = _GLOBAL_DIR / "global-manifest.json"
_GLOBAL_LOCK = _GLOBAL_DIR / ".global.lock"


@contextlib.contextmanager
def _global_lock():
    """Exclusive advisory lock around a global-graph read-modify-write.

    ``global_add`` / ``global_remove`` load the whole global graph, mutate it
    and write it back. Without a lock, two concurrent callers (e.g. post-commit
    hooks firing in two repos at once) both read the same base, and the second
    writer silently discards the first one's repo: the write is atomic, so
    nothing is *corrupted* — the update is simply lost, with no error anywhere.
    Serializing the whole read-modify-write is what makes concurrent syncing
    safe.

    Blocking by design: a caller that cannot get the lock must wait, never skip.
    Uses fcntl.flock so the lock is released if the process is killed. Falls
    back to a no-op on platforms without fcntl (Windows).

    The lock file is deliberately never unlinked: removing it while other
    processes hold descriptors to it lets a newcomer create a fresh inode and
    take the "same" lock concurrently.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return

    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(_GLOBAL_LOCK, "a+", encoding="utf-8")
    acquired = False
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        acquired = True
        # Record the holder's PID so external tooling can see who is syncing.
        with contextlib.suppress(OSError):
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        yield
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _repo_head_timestamp(source_path: Path) -> float | None:
    """Unix timestamp of the last commit of the repo owning ``source_path``.

    Returns None when the file is not inside a git work tree, or git is
    unavailable/slow. Used only to warn about stale graphs, never to block.
    """
    import subprocess

    start = source_path.resolve().parent
    for candidate in [start, *start.parents]:
        if not (candidate / ".git").exists():
            continue
        try:
            r = subprocess.run(
                ["git", "-C", str(candidate), "log", "-1", "--format=%ct"],
                capture_output=True, text=True, timeout=3,
            )
        except Exception:
            return None
        out = r.stdout.strip()
        if r.returncode == 0 and out:
            try:
                return float(out)
            except ValueError:
                return None
        return None
    return None


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

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed,
    skipped, source_mtime, stale. Skipped=True means the source graph hasn't
    changed since last add. Stale=True means the source graph predates the last
    commit of its own repo, i.e. what gets synced is older than the code.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"graph not found: {source_path}")

    with _global_lock():
        return _global_add_locked(source_path, repo_tag)


def _global_add_locked(source_path: Path, repo_tag: str) -> dict:
    """Body of :func:`global_add`. Caller must hold :func:`_global_lock`."""
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph

    manifest = _load_manifest()
    src_hash = _file_hash(source_path)
    src_mtime = source_path.stat().st_mtime
    src_mtime_iso = datetime.fromtimestamp(src_mtime, timezone.utc).isoformat()
    head_ts = _repo_head_timestamp(source_path)
    stale = bool(head_ts is not None and src_mtime < head_ts)

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
        return {
            "repo_tag": repo_tag, "nodes_added": 0, "nodes_removed": 0,
            "skipped": True, "source_mtime": src_mtime_iso, "stale": stale,
        }

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
    _save_global_graph(G)

    manifest["repos"][repo_tag] = {
        # When this sync ran. NOT how fresh the content is — see source_mtime.
        "added_at": datetime.now(timezone.utc).isoformat(),
        # When the source graph was last built. This is the age of what the
        # global graph actually holds for this repo.
        "source_mtime": src_mtime_iso,
        "source_path": str(source_path.resolve()),
        "node_count": added,
        "edge_count": prefixed.number_of_edges(),
        "source_hash": src_hash,
    }
    _save_manifest(manifest)

    return {
        "repo_tag": repo_tag, "nodes_added": added, "nodes_removed": removed,
        "skipped": False, "source_mtime": src_mtime_iso, "stale": stale,
    }


def global_remove(repo_tag: str) -> int:
    """Remove all nodes for repo_tag from the global graph. Returns count removed."""
    with _global_lock():
        return _global_remove_locked(repo_tag)


def _global_remove_locked(repo_tag: str) -> int:
    """Body of :func:`global_remove`. Caller must hold :func:`_global_lock`."""
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
