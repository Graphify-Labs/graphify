from __future__ import annotations
import json
import hashlib
import subprocess
import sys
import time
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
    write_json_atomic(_GLOBAL_GRAPH, data, compact=True)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _resolve_repo_root(source_path: Path) -> Path:
    """Resolve the repository root corresponding to a graph.json path.

    Prefers the explicit `.graphify_root` marker written alongside `graph.json`
    (which preserves the scan root even under a custom `--out`), falling back to
    the parent of `graphify-out/` or the file's immediate parent directory.
    """
    resolved = source_path.resolve()
    root_marker = resolved.parent / ".graphify_root"
    if root_marker.exists():
        try:
            candidate = Path(root_marker.read_text(encoding="utf-8").strip())
            if candidate.is_dir():
                return candidate.resolve()
        except OSError:
            pass
    if resolved.parent.name == "graphify-out":
        return resolved.parent.parent
    return resolved.parent


def _extract_built_at_commit(data: dict) -> str | None:
    """Extract a non-empty built_at_commit stamp from loaded graph JSON data."""
    raw = data.get("built_at_commit")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    graph_meta = data.get("graph")
    if isinstance(graph_meta, dict):
        nested = graph_meta.get("built_at_commit")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def _commits_between(
    repo_root: Path,
    base_commit: str | None,
    head_commit: str | None,
) -> int | None:
    """Return the number of commits in `base_commit..head_commit`, or None if unavailable."""
    if not base_commit or not head_commit:
        return None
    if base_commit == head_commit or head_commit.startswith(base_commit) or base_commit.startswith(head_commit):
        return 0
    try:
        res = subprocess.run(
            ["git", "rev-list", "--count", f"{base_commit}..{head_commit}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return int(res.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def settled(
    source_path: Path,
    budget_s: float,
    *,
    quiet_s: float = 2.0,
    poll_interval_s: float = 0.4,
) -> bool:
    """Return True once `source_path` is not actively being written, or False on timeout.

    Background `post-commit` / `post-checkout` hooks rebuild `graph.json`
    asynchronously. Merging while a rebuild is mid-write can either fail JSON
    parsing or stamp current git HEAD over older graph content.

    When `budget_s <= 0` or the file has been untouched for longer than `quiet_s`,
    this returns immediately without sleeping. Otherwise it polls `(st_size, st_mtime_ns)`
    until two consecutive samples match or `budget_s` expires.
    """
    if budget_s <= 0 or not source_path.exists():
        return True
    try:
        st = source_path.stat()
    except OSError:
        return False
    if (time.time() - st.st_mtime) > quiet_s:
        return True

    waited = 0.0
    last = (st.st_size, st.st_mtime_ns)
    while waited < budget_s:
        step = min(poll_interval_s, max(0.01, budget_s - waited))
        time.sleep(step)
        waited += step
        try:
            st = source_path.stat()
        except OSError:
            return False
        stamp = (st.st_size, st.st_mtime_ns)
        if stamp == last:
            return True
        last = stamp
    return False


def global_add(source_path: Path, repo_tag: str, *, settle_s: float = 0.0) -> dict:
    """Add or update a project graph in the global graph.

    Returns a summary dict with keys: repo_tag, nodes_added, nodes_removed, skipped,
    unsettled, cross_repo_calls.
    Skipped=True means the source graph hasn't changed since last add (or was
    still being written when `unsettled=True`).
    """
    from graphify.build import prefix_graph_for_global, prune_repo_from_graph

    if not source_path.exists():
        raise FileNotFoundError(f"graph not found: {source_path}")

    if settle_s > 0 and not settled(source_path, settle_s):
        return {
            "repo_tag": repo_tag,
            "nodes_added": 0,
            "nodes_removed": 0,
            "skipped": True,
            "unsettled": True,
            "cross_repo_calls": 0,
        }

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
        return {
            "repo_tag": repo_tag,
            "nodes_added": 0,
            "nodes_removed": 0,
            "skipped": True,
            "unsettled": False,
            "cross_repo_calls": 0,
        }

    # Load source graph
    from graphify.security import check_graph_file_size_cap
    check_graph_file_size_cap(source_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    built_at_commit = _extract_built_at_commit(data)
    if "links" not in data and "edges" in data:
        data = dict(data, links=data["edges"])
    from graphify.paths import restore_arc_direction
    data = restore_arc_direction(data)
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
    for node, node_data in prefixed.nodes(data=True):
        if not node_data.get("source_file") and node_data.get("label") in external_labels:
            remap[node] = external_labels[node_data["label"]]

    # Compose: add prefixed nodes (except deduplicated externals) into global graph
    for node, node_data in prefixed.nodes(data=True):
        if node not in remap:
            G.add_node(node, **node_data)
    for u, v, edge_data in prefixed.edges(data=True):
        u = remap.get(u, u)
        v = remap.get(v, v)
        # The direction markers name endpoints too; rewire them with u/v so
        # they never point at a deduplicated (absent) external node.
        for key in ("_src", "_tgt"):
            if edge_data.get(key) in remap:
                edge_data = {**edge_data, key: remap[edge_data[key]]}
        if u != v:  # don't introduce self-loops via remapping
            G.add_edge(u, v, **edge_data)

    added = prefixed.number_of_nodes() - len(remap)
    # A member call parked on a caller node (#3152) may be answered by a repo
    # already in the global graph, or by this one for a repo added earlier. The
    # pass recomputes its own output, so adding repos one at a time lands where a
    # single merge-graphs of the same inputs would.
    from graphify.cross_repo_calls import link_cross_repo_member_calls

    cross_repo_calls = link_cross_repo_member_calls(G)
    _save_global_graph(G)

    from graphify.watch import _git_head
    repo_root = _resolve_repo_root(source_path)
    head_at_merge = _git_head(cwd=repo_root)
    commit_basis: str | None = (
        "built_at_commit"
        if built_at_commit
        else ("head_at_merge" if head_at_merge else None)
    )

    manifest["repos"][repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path.resolve()),
        "node_count": added,
        "edge_count": prefixed.number_of_edges(),
        "source_hash": src_hash,
        "built_at_commit": built_at_commit,
        "head_at_merge": head_at_merge,
        "commit_basis": commit_basis,
    }
    _save_manifest(manifest)

    return {
        "repo_tag": repo_tag,
        "nodes_added": added,
        "nodes_removed": removed,
        "skipped": False,
        "unsettled": False,
        "cross_repo_calls": cross_repo_calls,
    }


def global_status(*, only: str | None = None) -> dict:
    """Inspect staleness and union sync status for all registered repositories.

    Compares each registered repo's manifest entry against its on-disk
    `source_path` hash and its git repository `HEAD`, keeping extracted commit
    provenance (`built_at_commit`) visibly separate from fallback git `HEAD`
    (`head_at_merge`).
    """
    from graphify.watch import _git_head

    repos = _load_manifest().get("repos", {})
    if only:
        targets = {t: info for t, info in repos.items() if only in t}
        if repos and not targets:
            raise ValueError(
                f"--only {only!r} matched no registered repo of {sorted(repos)}"
            )
    else:
        targets = dict(repos)

    report_repos: dict[str, dict] = {}
    for tag, info in targets.items():
        src_str = info.get("source_path", "")
        src_path = Path(src_str) if src_str else Path()
        exists = bool(src_str) and src_path.is_file()

        current_hash: str | None = None
        hash_in_sync = False
        source_built_at_commit: str | None = None
        current_head: str | None = None
        commits_behind: int | None = None

        if exists:
            try:
                current_hash = _file_hash(src_path)
                hash_in_sync = current_hash == info.get("source_hash")
            except OSError:
                hash_in_sync = False

            try:
                raw_data = json.loads(src_path.read_text(encoding="utf-8"))
                if isinstance(raw_data, dict):
                    source_built_at_commit = _extract_built_at_commit(raw_data)
            except (OSError, json.JSONDecodeError, ValueError):
                source_built_at_commit = None

            repo_root = _resolve_repo_root(src_path)
            current_head = _git_head(cwd=repo_root)
            merged_commit = (
                info.get("built_at_commit")
                or info.get("head_at_merge")
                or source_built_at_commit
            )
            commits_behind = _commits_between(repo_root, merged_commit, current_head)

        stale = (
            (not exists)
            or (not hash_in_sync)
            or (commits_behind is not None and commits_behind > 0)
        )
        report_repos[tag] = {
            "source_path": src_str,
            "source_exists": exists,
            "node_count": info.get("node_count", 0),
            "edge_count": info.get("edge_count", 0),
            "added_at": info.get("added_at"),
            "manifest_hash": info.get("source_hash"),
            "current_hash": current_hash,
            "hash_in_sync": hash_in_sync,
            "built_at_commit": info.get("built_at_commit"),
            "head_at_merge": info.get("head_at_merge"),
            "commit_basis": info.get("commit_basis"),
            "source_built_at_commit": source_built_at_commit,
            "current_head": current_head,
            "commits_behind": commits_behind,
            "stale": stale,
        }

    all_in_sync = bool(report_repos) and not any(
        r["stale"] for r in report_repos.values()
    ) if report_repos else True
    return {
        "global_path": str(_GLOBAL_GRAPH),
        "repos": report_repos,
        "all_in_sync": all_in_sync,
    }


def global_sync(*, only: str | None = None, settle_s: float = 0.0) -> dict:
    """Re-merge all repositories already registered in global-manifest.json.

    Returns a summary dict with `updated`, `skipped`, `unsettled`, `missing`,
    and per-repo `results`.
    """
    repos = _load_manifest().get("repos", {})
    if only:
        targets = {t: info for t, info in repos.items() if only in t}
        if repos and not targets:
            raise ValueError(
                f"--only {only!r} matched no registered repo of {sorted(repos)}"
            )
    else:
        targets = dict(repos)

    updated: list[str] = []
    skipped: list[str] = []
    unsettled: list[str] = []
    missing: list[str] = []
    results: dict[str, dict] = {}

    for tag, info in targets.items():
        src_str = info.get("source_path", "")
        src_path = Path(src_str) if src_str else Path()
        if not src_str or not src_path.is_file():
            missing.append(tag)
            continue
        res = global_add(src_path, tag, settle_s=settle_s)
        results[tag] = res
        if res.get("unsettled"):
            unsettled.append(tag)
        elif res.get("skipped"):
            skipped.append(tag)
        else:
            updated.append(tag)

    return {
        "updated": updated,
        "skipped": skipped,
        "unsettled": unsettled,
        "missing": missing,
        "results": results,
    }


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
