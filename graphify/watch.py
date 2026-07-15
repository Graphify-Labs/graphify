# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import contextlib
import json
import os
import posixpath
import re
import sys
import time
from pathlib import Path

# Single source of truth in graphify.paths (#1423); re-exported as _GRAPHIFY_OUT.
from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT
_PENDING_FILENAME = ".pending_changes"
_PENDING_DRAIN_MAX_PASSES = 20


def _queue_pending(out_dir: Path, changed_paths: list[Path]) -> None:
    """Append ``changed_paths`` to ``out_dir/.pending_changes`` (one per line).

    Used by a post-commit hook process that cannot acquire ``_rebuild_lock``
    so its change set is not silently dropped (#1059). The lock-holding
    process drains this file before and after its rebuild and merges the
    contents with its own change set.

    Opened in append mode so concurrent writers do not clobber each other on
    POSIX; each ``write()`` of a small payload is effectively atomic. A
    trailing newline is always written so partial-line corruption stays
    confined to the offending entry and is skipped on drain.
    """
    if not changed_paths:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    pending = out_dir / _PENDING_FILENAME
    payload = "".join(f"{os.fspath(p)}\n" for p in changed_paths)
    with open(pending, "a", encoding="utf-8") as fh:
        fh.write(payload)


def _drain_pending(out_dir: Path) -> list[Path]:
    """Read + unlink ``out_dir/.pending_changes`` and return deduplicated paths.

    Returns an empty list if the file does not exist. Empty/whitespace lines
    are silently skipped so a partial concurrent write that left only a
    fragment cannot poison the merge.
    """
    pending = out_dir / _PENDING_FILENAME
    if not pending.exists():
        return []
    try:
        raw = pending.read_text(encoding="utf-8")
    except OSError:
        return []
    # Unlink BEFORE returning so a crash between read and process retains the
    # data in the next caller's view via the lines we are about to return —
    # i.e. losing the file after reading is fine, losing it before would be a
    # bug. Use missing_ok to tolerate a racing drain on platforms where
    # rename/unlink may interleave.
    with contextlib.suppress(FileNotFoundError):
        pending.unlink()
    seen: set[str] = set()
    out: list[Path] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(Path(s))
    return out


# Build options that must survive into later rebuilds. The initial `extract`
# scan honours `--exclude`, but `update`/`watch`/hook rebuilds re-run detect()
# and would silently re-include excluded paths unless the patterns are persisted
# (#1886). We store them beside the graph so any rebuild driver can re-apply them.
_BUILD_CONFIG_FILENAME = ".graphify_build.json"


def _write_build_config(out_dir: Path, *, excludes: "list[str] | None") -> None:
    """Persist build options (currently ``--exclude`` patterns) under ``out_dir``.

    Best-effort and non-clobbering: with no excludes it leaves any existing file
    untouched, so a plain rebuild never erases patterns a prior extract recorded.
    """
    if not excludes:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / _BUILD_CONFIG_FILENAME).write_text(
            json.dumps({"excludes": list(excludes)}), encoding="utf-8"
        )
    except OSError:
        pass


def _read_build_excludes(out_dir: Path) -> list[str]:
    """Return the persisted ``--exclude`` patterns for this graph, or []."""
    try:
        path = out_dir / _BUILD_CONFIG_FILENAME
        if path.is_file():
            cfg = json.loads(path.read_text(encoding="utf-8"))
            ex = cfg.get("excludes") if isinstance(cfg, dict) else None
            if isinstance(ex, list):
                return [str(x) for x in ex if isinstance(x, str) and x]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _merge_changed_paths(*sources: "list[Path] | None") -> list[Path]:
    """Concatenate path lists, preserving order and dropping duplicates.

    Used to combine a hook process's own ``changed_paths`` with the drained
    contents of ``.pending_changes`` so the lock-holding rebuild covers
    every queued commit's worth of files (#1059).
    """
    seen: set[str] = set()
    out: list[Path] = []
    for src in sources:
        if not src:
            continue
        for p in src:
            key = os.fspath(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


@contextlib.contextmanager
def _rebuild_lock(out_dir: Path, *, blocking: bool = False):
    """Per-repo advisory lock around a rebuild.

    Yields True if acquired, False if another rebuild is already running and
    ``blocking`` is False. Uses fcntl.flock so the lock is released
    automatically if the process is killed (no stale-lock cleanup needed).

    While the lock is held, ``.rebuild.lock`` contains the owning PID followed
    by a newline so external pollers (publish scripts, etc.) can read it.
    On successful release the file is unlinked so downstream tooling that
    waits for the lock to clear by polling for its absence unblocks promptly.

    Falls back to a no-op yield(True) on platforms without fcntl (Windows).
    """
    try:
        import fcntl
    except ImportError:
        yield True
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / ".rebuild.lock"
    # "a+" creates the file if missing without truncating an existing holder's
    # PID payload — important because another process may have already written
    # its PID before we attempt the flock.
    fh = open(lock_path, "a+", encoding="utf-8")
    acquired = False
    try:
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(fh.fileno(), flags)
        except BlockingIOError:
            yield False
            return
        acquired = True
        # Replace any prior owner's PID with ours so external readers see a
        # single parseable line, not a digit-concatenation across rebuilds.
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        except OSError:
            pass
        yield True
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()
        # Signal "rebuild done" by removing the lock file. Only the holder
        # unlinks; a non-acquiring caller leaves the existing lock in place.
        if acquired:
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _apply_resource_limits() -> None:
    """Best-effort nice + memory cap. Called from inline hook scripts.

    GRAPHIFY_REBUILD_MEMORY_LIMIT_MB caps RSS-ish memory. Uses RLIMIT_DATA on
    macOS (RLIMIT_AS is unreliable under Apple's libmalloc) and RLIMIT_AS on
    Linux. Silently skips if the platform doesn't support it.
    """
    try:
        os.nice(10)
    except (OSError, AttributeError):
        pass
    mb = os.environ.get("GRAPHIFY_REBUILD_MEMORY_LIMIT_MB", "").strip()
    if not mb:
        return
    try:
        limit = int(mb) * 1024 * 1024
    except ValueError:
        return
    try:
        import resource
        which = resource.RLIMIT_DATA if sys.platform == "darwin" else resource.RLIMIT_AS
        soft, hard = resource.getrlimit(which)
        new_hard = hard if hard != resource.RLIM_INFINITY and hard < limit else limit
        resource.setrlimit(which, (limit, new_hard))
    except (ImportError, ValueError, OSError):
        pass


def _git_head() -> str | None:
    """Return current git HEAD commit hash, or None outside a repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


from graphify.detect import (
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    PAPER_EXTENSIONS,
    IMAGE_EXTENSIONS,
    _load_graphifyignore,
    _is_ignored,
)

_WATCHED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _report_root_label(watch_path: Path) -> str:
    if watch_path.is_absolute():
        return watch_path.name or str(watch_path)
    return Path.cwd().name if watch_path == Path(".") else str(watch_path)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _changed_path_candidates(raw: Path, *, change_root: Path, watch_root: Path) -> list[Path]:
    """Return plausible absolute locations for a hook-provided changed path.

    Git hooks pass paths relative to the repository root. Watch callers may
    also pass paths relative to the watched root. Keep both interpretations so
    a graph rooted at ``src`` accepts ``src/app.py`` and ``app.py``.
    """
    if raw.is_absolute():
        lexical = Path(os.path.abspath(raw))
        resolved = raw.resolve()
        return [lexical] if lexical == resolved else [lexical, resolved]

    candidates: list[Path] = []
    seen: set[str] = set()
    for base in (change_root, watch_root):
        lexical = Path(os.path.abspath(base / raw))
        for cand in (lexical, lexical.resolve()):
            key = os.fspath(cand)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(cand)
    return candidates


def _relativize_source_files(payload: dict, root: Path, *, scope: Path | None = None) -> None:
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            source = item.get("source_file")
            if not source:
                continue
            source_path = Path(source)
            if not source_path.is_absolute():
                continue
            try:
                resolved = source_path.resolve()
                if scope is not None and not _is_relative_to(resolved, scope):
                    continue
                item["source_file"] = resolved.relative_to(root).as_posix()
            except ValueError:
                continue


def _rebase_relative_source_files(payload: dict, source_root: Path, target_root: Path) -> None:
    """Rebase cache-root-relative source paths onto the project root."""
    if source_root == target_root:
        return
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in payload.get(bucket, []):
            source = item.get("source_file")
            if not source or Path(source).is_absolute():
                continue
            try:
                item["source_file"] = (source_root / source).relative_to(target_root).as_posix()
            except ValueError:
                continue


class _StoredSourcePaths:
    """Resolve source_file values across current and legacy graph roots."""

    def __init__(
        self,
        existing: dict,
        *,
        out: Path,
        project_root: Path,
        watch_root: Path,
        normalize_source,
    ) -> None:
        self.project_root = project_root
        self.watch_root = watch_root
        self._normalize_source = normalize_source
        self.existing_source_root = project_root
        relative_marker_prefix: str | None = None

        root_marker = out / ".graphify_root"
        if root_marker.exists():
            try:
                saved_root = Path(root_marker.read_text(encoding="utf-8").strip())
                if saved_root.is_absolute():
                    self.existing_source_root = saved_root.resolve()
                else:
                    invocation_root = Path.cwd().resolve()
                    if (invocation_root / saved_root).resolve() == watch_root:
                        self.existing_source_root = invocation_root
                        relative_marker_prefix = posixpath.normpath(saved_root.as_posix())
            except (OSError, ValueError):
                pass

        self.legacy_watch_relative = False
        if relative_marker_prefix not in (None, "."):
            has_project_relative_source = False
            for bucket in ("nodes", "links", "edges", "hyperedges"):
                for item in existing.get(bucket, []):
                    stored = normalize_source(item.get("source_file"))
                    if not stored or Path(stored).is_absolute():
                        continue
                    normalized = posixpath.normpath(stored)
                    if (
                        normalized == relative_marker_prefix
                        or normalized.startswith(relative_marker_prefix + "/")
                    ):
                        has_project_relative_source = True
                        break
                if has_project_relative_source:
                    break
            self.legacy_watch_relative = not has_project_relative_source

    def normalize(self, source_file: str | None) -> str | None:
        normalized = self._normalize_source(source_file, str(self.project_root))
        return posixpath.normpath(normalized) if normalized else normalized

    def absolute_identity(self, source_file: str | None, root: Path) -> str | None:
        normalized = self._normalize_source(source_file)
        if not normalized:
            return normalized
        source_path = Path(posixpath.normpath(normalized))
        if not source_path.is_absolute():
            source_path = root / source_path
        return Path(os.path.abspath(source_path)).as_posix()

    def identity(self, source_file: str | None) -> str | None:
        normalized = self._normalize_source(source_file)
        if normalized and not Path(normalized).is_absolute() and self.legacy_watch_relative:
            return self.absolute_identity(normalized, self.watch_root)
        return self.absolute_identity(normalized, self.existing_source_root)

    def in_watch_root(self, source_file: str | None) -> bool:
        identity = self.identity(source_file)
        return bool(identity) and _is_relative_to(Path(identity), self.watch_root)

    def is_evicted(self, item: dict, identities: set[str]) -> bool:
        return self.identity(item.get("source_file")) in identities

    def rebase_preserved(self, item: dict) -> None:
        identity = self.identity(item.get("source_file"))
        if not identity:
            return
        identity_path = Path(identity)
        if not _is_relative_to(identity_path, self.watch_root):
            normalized = self.normalize(item.get("source_file"))
            if normalized:
                item["source_file"] = normalized
            return
        try:
            item["source_file"] = identity_path.relative_to(self.project_root).as_posix()
        except ValueError:
            item["source_file"] = identity


def _reconcile_existing_graph(
    existing_graph: Path,
    result: dict,
    *,
    out: Path,
    project_root: Path,
    watch_root: Path,
    code_files: list[Path],
    extract_targets: list[Path],
    full_rebuild: bool,
    deleted_paths: set[str],
    deleted_source_identities: set[str],
) -> tuple[dict, dict]:
    """Merge fresh extraction with preserved graph entries and evict stale sources."""
    existing_graph_data: dict = {}
    if not existing_graph.exists():
        return result, existing_graph_data

    try:
        from graphify.build import _norm_source_file as _nsf
        from graphify.extract import _get_extractor
        from graphify.security import check_graph_file_size_cap

        check_graph_file_size_cap(existing_graph)
        existing = json.loads(existing_graph.read_text(encoding="utf-8"))
        existing_graph_data = existing
        source_paths = _StoredSourcePaths(
            existing,
            out=out,
            project_root=project_root,
            watch_root=watch_root,
            normalize_source=_nsf,
        )
        new_ast_ids = {n["id"] for n in result["nodes"]}
        current_sources = {
            source_paths.absolute_identity(str(path), project_root) for path in code_files
        }
        rebuilt_source_identities = {
            source_paths.absolute_identity(str(path), project_root) for path in extract_targets
        }
        node_evicted_source_identities = set(deleted_source_identities)
        hyperedge_evicted_source_identities = set(deleted_source_identities)
        # Deletion evicts edges regardless of tier; re-extraction only owns a
        # source's AST-tier edges (checked per-edge below, #1865).
        edge_evicted_source_identities = set(deleted_source_identities)
        if not full_rebuild:
            node_evicted_source_identities.update(rebuilt_source_identities)

        # Reconcile every rebuild against the current watched corpus. Hook change
        # lists can contain only a rename destination, so explicit paths alone
        # cannot identify the stale source. Keep the comparison scoped to the
        # watched root so subfolder updates preserve records outside that subtree.
        #
        # Fail-closed eviction: a source identity missing from the corpus is only
        # DELETION evidence when the file is actually gone from disk. A file that
        # still exists but stopped being collected was *excluded* (ignore rules or
        # filters changed — e.g. a .gitignore the scanner newly honors), and
        # treating that as deletion silently mass-evicts good nodes. Preserve
        # instead and say so; a full re-extraction still purges deliberately
        # excluded sources via the AST ownership rule below.
        excluded_alive_files: set[str] = set()
        excluded_alive_nodes = 0
        _alive_cache: dict[str, bool] = {}
        for node in existing.get("nodes", []):
            source_file = node.get("source_file")
            if not source_file or _get_extractor(Path(source_file)) is None:
                continue
            identity = source_paths.identity(source_file)
            if not source_paths.in_watch_root(source_file):
                continue
            if identity not in current_sources:
                if identity:
                    alive = _alive_cache.get(identity)
                    if alive is None:
                        alive = Path(identity).exists()
                        _alive_cache[identity] = alive
                    if alive:
                        excluded_alive_files.add(identity)
                        excluded_alive_nodes += 1
                        continue
                normalized = source_paths.normalize(source_file)
                if normalized:
                    deleted_paths.add(normalized)
                if identity:
                    node_evicted_source_identities.add(identity)
                    edge_evicted_source_identities.add(identity)
                    hyperedge_evicted_source_identities.add(identity)
        if excluded_alive_files:
            print(
                f"[graphify watch] fail-closed: kept {excluded_alive_nodes} node(s) "
                f"from {len(excluded_alive_files)} file(s) that left the scan corpus "
                "but still exist on disk (ignore rules or filters changed?). "
                "Run a full re-extraction to purge them if the exclusion is intentional."
            )

        # A full re-extraction owns every AST node under watch_root. Incremental
        # extraction owns only nodes from rebuilt or deleted sources. Semantic
        # nodes lack the AST origin marker and remain preserved.
        preserved_nodes = [
            node
            for node in existing.get("nodes", [])
            if node["id"] not in new_ast_ids
            and not (
                node.get("_origin") == "ast"
                and (
                    (
                        not node.get("source_file")
                        and (full_rebuild or not code_files)
                    )
                    or (
                        full_rebuild
                        and source_paths.in_watch_root(node.get("source_file"))
                    )
                )
            )
            and not source_paths.is_evicted(node, node_evicted_source_identities)
        ]
        all_ids = new_ast_ids | {node["id"] for node in preserved_nodes}

        # Edges are owned by source_file, but ownership is tier-scoped: the AST
        # pass replaces a re-extracted source's AST edges, while that source's
        # semantic/LLM edges — which the AST pass cannot regenerate — survive
        # until a semantic re-extraction supersedes them. Same provenance rule
        # the node reconciliation above applies via _origin (#1865). Deletion
        # eviction stays provenance-blind.
        preserved_edges = [
            edge
            for edge in existing.get("links", existing.get("edges", []))
            if edge.get("source") in all_ids
            and edge.get("target") in all_ids
            and not source_paths.is_evicted(edge, edge_evicted_source_identities)
            and not (
                edge.get("_origin") == "ast"
                and source_paths.is_evicted(edge, rebuilt_source_identities)
            )
        ]

        new_hyperedge_ids = {
            edge.get("id") for edge in result.get("hyperedges", []) if edge.get("id")
        }
        preserved_hyperedges = []
        for edge in existing.get("hyperedges", []):
            members = edge.get("nodes", edge.get("members", edge.get("node_ids", [])))
            if edge.get("id") in new_hyperedge_ids or source_paths.is_evicted(
                edge, hyperedge_evicted_source_identities
            ):
                continue
            if isinstance(members, list) and any(member not in all_ids for member in members):
                continue
            preserved_hyperedges.append(edge)

        for item in preserved_nodes + preserved_edges + preserved_hyperedges:
            source_paths.rebase_preserved(item)

        return {
            "nodes": result["nodes"] + preserved_nodes,
            "edges": result["edges"] + preserved_edges,
            "hyperedges": result.get("hyperedges", []) + preserved_hyperedges,
            "input_tokens": 0,
            "output_tokens": 0,
        }, existing_graph_data
    except Exception:
        return result, existing_graph_data


def _node_community_map(graph_data: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in graph_data.get("nodes", []):
        node_id = node.get("id")
        cid = node.get("community")
        if node_id is None or cid is None:
            continue
        try:
            out[str(node_id)] = int(cid)
        except (TypeError, ValueError):
            print(
                f"[graphify watch] Skipping node with invalid community id: "
                f"node_id={node_id!r} community={cid!r}",
                file=sys.stderr,
            )
            continue
    return out


def _canonical_graph_for_compare(graph_data: dict) -> dict:
    canonical = dict(graph_data)
    canonical.pop("built_at_commit", None)
    for key in ("nodes", "links", "edges", "hyperedges"):
        if key in canonical and isinstance(canonical[key], list):
            canonical[key] = sorted(
                canonical[key],
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
            )
    return canonical


def _canonical_topology_for_compare(graph_data: dict) -> dict:
    canonical = dict(graph_data)
    canonical.pop("built_at_commit", None)

    nodes = canonical.get("nodes")
    if isinstance(nodes, list):
        norm_nodes = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            n = dict(node)
            n.pop("community", None)
            n.pop("community_name", None)
            n.pop("norm_label", None)
            norm_nodes.append(n)
        canonical["nodes"] = sorted(
            norm_nodes,
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
        )

    for key in ("links", "edges"):
        items = canonical.get(key)
        if not isinstance(items, list):
            continue
        norm_edges = []
        for edge in items:
            if not isinstance(edge, dict):
                continue
            e = dict(edge)
            # to_json writes _src/_tgt as the canonical directed endpoints and
            # overwrites source/target with them before serialising, so the
            # on-disk graph has no _src/_tgt. The candidate topology (fresh from
            # node_link_data) still has them. Popping and reassigning here makes
            # both sides comparable: existing gets no-op pops (None), candidate
            # gets source/target overwritten from _src/_tgt — same result.
            true_src = e.pop("_src", None)
            true_tgt = e.pop("_tgt", None)
            if true_src is not None and true_tgt is not None:
                e["source"] = true_src
                e["target"] = true_tgt
            e.pop("confidence_score", None)
            norm_edges.append(e)
        canonical[key] = sorted(
            norm_edges,
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
        )

    hyperedges = canonical.get("hyperedges")
    if isinstance(hyperedges, list):
        canonical["hyperedges"] = sorted(
            hyperedges,
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
        )

    return canonical


def _topology_from_graph(G) -> dict:
    from networkx.readwrite import json_graph
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    return data


def _check_shrink(
    force: bool,
    existing_data: dict,
    new_data: dict,
    tmp: "Path | None" = None,
    *,
    had_explicit_deletions: bool = False,
    rebuilt_sources: "set[str] | None" = None,
) -> bool:
    """Return True (ok to proceed) or False (shrink refused).

    When False, cleans up *tmp* if provided and prints a warning to stderr.

    The shrink-guard exists to catch SILENT shrinkage from failed extraction
    chunks (a half-written semantic pass leaving thousands of nodes
    unaccounted for). When ``had_explicit_deletions`` is True, the caller
    has declared which files were removed (e.g. the post-commit hook saw
    a ``D`` in ``git diff --name-only``) and a smaller graph is the expected
    outcome — skip the guard so legitimate refactors don't require ``--force``.

    ``rebuilt_sources`` (when given) is the set of source files re-extracted this
    run. A net shrink is legitimate — not a failed chunk — when every *lost* node
    belonged to one of those files (a symbol removed from a re-extracted file) or
    carries no source_file. Only an unexplained loss (a node from a file we did
    NOT touch — e.g. a dropped semantic/doc node) refuses the write. This lets a
    plain ``graphify update`` after deleting a function refresh the graph without
    ``--force`` (#1116 left stale nodes write-blocked even though build dropped them).
    """
    if force or not existing_data or had_explicit_deletions:
        return True
    existing_nodes = existing_data.get("nodes", [])
    new_nodes = new_data.get("nodes", [])
    if len(new_nodes) >= len(existing_nodes):
        return True
    if rebuilt_sources is not None:
        from graphify.build import _norm_source_file
        new_ids = {n.get("id") for n in new_nodes}
        lost = [n for n in existing_nodes if n.get("id") not in new_ids]

        def _accounted(n: dict) -> bool:
            sf = n.get("source_file")
            return (not sf
                    or sf in rebuilt_sources
                    or _norm_source_file(sf) in rebuilt_sources)
        if all(_accounted(n) for n in lost):
            return True
    if tmp is not None:
        tmp.unlink(missing_ok=True)
    print(
        f"[graphify] WARNING: new graph has {len(new_nodes)} nodes but existing "
        f"graph.json has {len(existing_nodes)}. Refusing to overwrite — you may be "
        f"missing chunk files from a previous session. "
        f"Pass --force to override.",
        file=sys.stderr,
    )
    return False


def _report_for_compare(report_text: str) -> str:
    return re.sub(r"^- Built from commit: `[^`]+`\n?", "", report_text, flags=re.MULTILINE)


def _json_text(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _stabilize_rebuild_cwd(watch_path: Path) -> bool:
    """Ensure relative rebuild paths have a usable CWD before queue/lock setup.

    Detached git hooks can inherit a transient working directory that is deleted
    before the background rebuild starts. In that state Path.cwd(),
    Path('.').resolve(), and relative graphify-out mkdirs raise FileNotFoundError
    before the normal rebuild error handling can run. Hooks that know the repo
    root export GRAPHIFY_REPO_ROOT so the rebuild can recover by chdir'ing there.
    """
    if watch_path.is_absolute():
        return True

    repo_root = os.environ.get("GRAPHIFY_REPO_ROOT", "").strip()
    if repo_root and Path(repo_root).is_dir():
        try:
            os.chdir(repo_root)
            return True
        except OSError:
            pass

    try:
        Path.cwd()
        return True
    except FileNotFoundError:
        print(
            "[graphify watch] Rebuild failed: current working directory "
            "no longer exists and GRAPHIFY_REPO_ROOT is not set."
        )
        return False


def _rebuild_code(
    watch_path: Path,
    *,
    changed_paths: list[Path] | None = None,
    follow_symlinks: bool = False,
    force: bool = False,
    no_cluster: bool = False,
    acquire_lock: bool = True,
    block_on_lock: bool = False,
) -> bool:
    """Re-run AST extraction + build + optional cluster + report for code files. No LLM needed.

    When ``force`` is True the node-count safety check in ``to_json`` is bypassed
    so the rebuilt graph overwrites graph.json even if it has fewer nodes.
    Use this after refactors that legitimately delete code.

    When ``changed_paths`` is provided, only those files are re-extracted; nodes
    for unchanged files are preserved from the existing graph. Deleted paths
    in ``changed_paths`` (paths that no longer exist on disk) are dropped from
    the preserved set. When ``changed_paths`` is None the full code corpus is
    re-extracted (used by the watcher and post-checkout hook).

    ``acquire_lock`` (default True) takes a non-blocking per-repo flock around
    the rebuild so concurrent post-commit hooks across multiple repos do not
    pile up. Returns False with a log line if the lock is held. Pass
    ``block_on_lock=True`` to wait instead of skip (used by the interactive
    ``graphify update`` CLI).

    ``no_cluster`` skips community detection and writes raw merged extraction
    JSON to graphify-out/graph.json (mirrors ``extract --no-cluster``).

    Returns True on success, False on error or skipped-due-to-lock.
    """
    if not _stabilize_rebuild_cwd(watch_path):
        return False

    out = watch_path / _GRAPHIFY_OUT
    if acquire_lock:
        # #1059: incremental (changed_paths is not None) hooks must not drop
        # their change set when another rebuild is already running. Queue
        # before attempting the lock so a non-blocking failure still records
        # the work; the lock-holder drains the queue and merges it in. Full-
        # corpus rebuilds skip the queue entirely — they already cover every
        # file, so there is nothing to merge.
        if changed_paths is not None and not block_on_lock:
            _queue_pending(out, list(changed_paths))
        with _rebuild_lock(out, blocking=block_on_lock) as got:
            if not got:
                print("[graphify watch] Rebuild already in progress for "
                      f"{watch_path.resolve()} - changes queued.")
                return False
            # Lock acquired. Drain anything queued by earlier contenders
            # (including, importantly, the paths we just queued ourselves)
            # and merge with our own change set so a single rebuild covers
            # everything outstanding.
            if changed_paths is not None:
                merged = _merge_changed_paths(changed_paths, _drain_pending(out))
            else:
                # Full-corpus rebuild supersedes any queued incremental work.
                _drain_pending(out)
                merged = None
            ok = _rebuild_code(
                watch_path,
                changed_paths=merged,
                follow_symlinks=follow_symlinks,
                force=force,
                no_cluster=no_cluster,
                acquire_lock=False,
            )
            # Late-arrival drain: another hook may have queued work while we
            # were rebuilding. Loop up to _PENDING_DRAIN_MAX_PASSES times so a
            # storm of commits eventually quiesces without livelocking. A full
            # rebuild already saw everything, so skip this for changed_paths is None.
            if merged is not None:
                for _ in range(_PENDING_DRAIN_MAX_PASSES):
                    late = _drain_pending(out)
                    if not late:
                        break
                    ok = _rebuild_code(
                        watch_path,
                        changed_paths=late,
                        follow_symlinks=follow_symlinks,
                        force=force,
                        no_cluster=no_cluster,
                        acquire_lock=False,
                    ) and ok
            return ok

    watch_root = watch_path.resolve()
    project_root = Path.cwd().resolve() if not watch_path.is_absolute() else watch_root
    report_root = _report_root_label(watch_path)
    try:
        from graphify.extract import extract, _get_extractor
        from graphify.detect import detect
        from graphify.build import build_from_json, _norm_source_file as _nsf
        from graphify.cluster import cluster, remap_communities_to_previous, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json, to_html
        from graphify.security import check_graph_file_size_cap

        # Re-apply the excludes the initial extract recorded, so an update/watch/
        # hook rebuild does not silently re-include deliberately excluded paths
        # (#1886).
        _persisted_excludes = _read_build_excludes(out)
        detected = detect(
            watch_path, follow_symlinks=follow_symlinks,
            extra_excludes=_persisted_excludes or None,
        )
        code_files = [Path(f) for f in detected['files']['code']]

        # Include document files that have AST extractors (e.g. .md, .mdx, .qmd)
        for doc_file in detected['files'].get('document', []):
            p = Path(doc_file)
            if _get_extractor(p) is not None:
                code_files.append(p)

        existing_graph = out / "graph.json"
        if not code_files and not existing_graph.exists():
            print("[graphify watch] No code files found - nothing to rebuild.")
            return False

        # Incremental path: when the caller passed an explicit change list,
        # extract only changed-and-still-existing files. Deleted paths are
        # tracked separately so their stale nodes can be evicted below.
        deleted_paths: set[str] = set()
        deleted_source_identities: set[str] = set()
        def _add_deleted_source(path: Path) -> None:
            deleted_source_identities.add(Path(os.path.abspath(path)).as_posix())
            for root in (project_root, watch_root):
                deleted_paths.add(_nsf(str(path), str(root)) or str(path))

        if changed_paths is not None:
            code_set = {Path(os.path.abspath(p)) for p in code_files}
            wanted: list[Path] = []
            change_root = Path.cwd().resolve()
            for raw in changed_paths:
                candidates = _changed_path_candidates(
                    raw,
                    change_root=change_root,
                    watch_root=watch_root,
                )
                tracked = next((cand for cand in candidates if cand.exists() and cand in code_set), None)
                if tracked is not None:
                    if tracked not in wanted:
                        wanted.append(tracked)
                    continue

                existing_in_root = next(
                    (
                        cand for cand in candidates
                        if cand.exists() and _is_relative_to(cand, watch_root)
                    ),
                    None,
                )
                if existing_in_root is not None:
                    # The path exists under the watched root but detect filtered
                    # it out. Evict any stale nodes that still claim it.
                    _add_deleted_source(existing_in_root)
                    continue

                deleted_in_root = next(
                    (cand for cand in candidates if _is_relative_to(cand, watch_root)),
                    None,
                )
                if deleted_in_root is not None:
                    # File was deleted or renamed away inside the watched root.
                    # Evict preserved nodes that still claim this source path.
                    _add_deleted_source(deleted_in_root)
            if not wanted and not deleted_paths:
                print("[graphify watch] No tracked code files in change set - skipping rebuild.")
                return True
            extract_targets = wanted
        else:
            extract_targets = code_files

        commit = _git_head()
        result = extract(extract_targets, cache_root=watch_root) if extract_targets else {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0,
        }
        _rebase_relative_source_files(result, watch_root, project_root)

        # Preserve semantic nodes/edges from a previous full run.
        # AST-only rebuild replaces nodes for changed files; everything else is kept.
        # Filter by node ID membership in the new AST output, not by file_type —
        # INFERRED/AMBIGUOUS nodes extracted from code files also carry file_type="code"
        # and would be wrongly dropped by a file_type-based filter.
        # When the caller supplied changed_paths, also evict preserved nodes whose
        # source_file matches a path that was changed (re-extracted) or deleted —
        # otherwise the old nodes for those files would survive forever.
        result, existing_graph_data = _reconcile_existing_graph(
            existing_graph,
            result,
            out=out,
            project_root=project_root,
            watch_root=watch_root,
            code_files=code_files,
            extract_targets=extract_targets,
            full_rebuild=changed_paths is None,
            deleted_paths=deleted_paths,
            deleted_source_identities=deleted_source_identities,
        )

        _relativize_source_files(result, project_root, scope=watch_root)
        # Source files re-extracted this run — their symbol sets may legitimately
        # shrink (a removed function), so the shrink-guard should not block the
        # write when every lost node belongs to one of them (or a deleted file).
        _rebuilt_root = str(project_root)
        if changed_paths is None:
            rebuilt_sources = {
                _nsf(str(p.relative_to(project_root)), _rebuilt_root)
                for p in code_files if p.is_relative_to(project_root)
            }
        else:
            rebuilt_sources = {(_nsf(str(p), _rebuilt_root) or str(p)) for p in extract_targets}
        rebuilt_sources |= set(deleted_paths)
        out.mkdir(exist_ok=True)

        if no_cluster:
            # Normalise to "links" key so schema is consistent with the full clustered path.
            # Dedupe parallel edges (the clustered path's DiGraph collapses them implicitly);
            # without it, --no-cluster + repeated `update` accumulate duplicates and edge
            # counts diverge across build modes (#1317).
            from graphify.build import dedupe_edges as _dedupe_edges, dedupe_nodes as _dedupe_nodes
            candidate_graph_data = {
                **{k: v for k, v in result.items() if k not in ("edges", "nodes")},
                "nodes": _dedupe_nodes(result.get("nodes", [])),
                "links": _dedupe_edges(result.get("edges", [])),
            }
            candidate_graph_text = _json_text(candidate_graph_data)
            same_graph = False
            if existing_graph.exists():
                try:
                    check_graph_file_size_cap(existing_graph)
                    existing_payload = json.loads(existing_graph.read_text(encoding="utf-8"))
                    same_graph = (
                        json.dumps(_canonical_graph_for_compare(existing_payload), sort_keys=True, ensure_ascii=False)
                        == json.dumps(_canonical_graph_for_compare(candidate_graph_data), sort_keys=True, ensure_ascii=False)
                    )
                except Exception:
                    same_graph = False
            if not same_graph:
                if not _check_shrink(
                    force, existing_graph_data, candidate_graph_data,
                    had_explicit_deletions=bool(deleted_paths),
                    rebuilt_sources=rebuilt_sources,
                ):
                    return False
                existing_graph.write_text(candidate_graph_text, encoding="utf-8")

            # Write the user-supplied path only after the candidate graph is
            # accepted, so a refused shrink cannot mismatch graph and marker.
            (out / ".graphify_root").write_text(str(watch_path), encoding="utf-8")

            try:
                from graphify.detect import save_manifest
                save_manifest(detected["files"], kind="ast", root=project_root)
            except Exception:
                pass

            # clear stale needs_update flag if present
            flag = out / "needs_update"
            if flag.exists():
                flag.unlink()

            if same_graph:
                print("[graphify watch] No code-graph changes detected (--no-cluster); outputs left untouched.")
            else:
                print(
                    "[graphify watch] Rebuilt (no clustering): "
                    f"{len(candidate_graph_data.get('nodes', []))} nodes, "
                    f"{len(candidate_graph_data.get('links', []))} edges"
                )
                print(f"[graphify watch] graph.json updated in {out}")
            return True

        detection = {
            "files": {"code": [str(f) for f in code_files], "document": [], "paper": [], "image": []},
            "total_files": len(code_files),
            "total_words": detected.get("total_words", 0),
        }

        G = build_from_json(result)
        candidate_topology = _topology_from_graph(G)
        if existing_graph_data:
            try:
                same_topology = (
                    json.dumps(_canonical_topology_for_compare(existing_graph_data), sort_keys=True, ensure_ascii=False)
                    == json.dumps(_canonical_topology_for_compare(candidate_topology), sort_keys=True, ensure_ascii=False)
                )
            except Exception:
                same_topology = False
            if same_topology:
                try:
                    from graphify.detect import save_manifest
                    save_manifest(detected["files"], kind="ast", root=project_root)
                except Exception:
                    pass
                flag = out / "needs_update"
                if flag.exists():
                    flag.unlink()
                print("[graphify watch] No code-graph topology changes detected; outputs left untouched.")
                return True

        communities = cluster(G)
        previous_node_community = _node_community_map(existing_graph_data)
        if previous_node_community:
            communities = remap_communities_to_previous(communities, previous_node_community)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels_file = out / ".graphify_labels.json"
        try:
            raw = json.loads(labels_file.read_text(encoding="utf-8")) if labels_file.exists() else {}
            labels = {int(k): v for k, v in raw.items() if int(k) in communities}
        except Exception:
            raw = {}
            labels = {}
        missing = {cid: members for cid, members in communities.items() if cid not in labels}
        if missing:
            # Deterministic hub name (highest-degree member) beats a bare "Community N"
            # placeholder for any community without a saved label.
            from graphify.cluster import label_communities_by_hub
            labels.update(label_communities_by_hub(G, missing))
        questions = suggest_questions(G, communities, labels)
        from graphify.report import load_learning_for_report as _llfr
        report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                          {"input": 0, "output": 0}, report_root, suggested_questions=questions,
                          built_at_commit=commit, learning=_llfr(out / "graph.json"))
        report_path = out / "GRAPH_REPORT.md"
        labels_json = json.dumps({str(k): v for k, v in sorted(labels.items())}, ensure_ascii=False, indent=2) + "\n"
        graph_tmp = out / ".graph.tmp.json"
        json_written = to_json(G, communities, str(graph_tmp), force=True, built_at_commit=commit, community_labels=labels)
        if not json_written:
            return False
        candidate_graph_data = json.loads(graph_tmp.read_text(encoding="utf-8"))
        same_graph = False
        same_report = False
        if existing_graph.exists():
            try:
                check_graph_file_size_cap(existing_graph)
                existing_payload = json.loads(existing_graph.read_text(encoding="utf-8"))
                same_graph = (
                    json.dumps(_canonical_graph_for_compare(existing_payload), sort_keys=True, ensure_ascii=False)
                    == json.dumps(_canonical_graph_for_compare(candidate_graph_data), sort_keys=True, ensure_ascii=False)
                )
            except Exception:
                same_graph = False
        if report_path.exists():
            old_report = report_path.read_text(encoding="utf-8")
            same_report = _report_for_compare(old_report) == _report_for_compare(report)
        no_change = same_graph and same_report
        if no_change:
            graph_tmp.unlink(missing_ok=True)
            print("[graphify watch] No code-graph changes detected; graph.json/GRAPH_REPORT.md left untouched.")
        else:
            if not _check_shrink(
                force, existing_graph_data, candidate_graph_data,
                tmp=graph_tmp,
                had_explicit_deletions=bool(deleted_paths),
                rebuilt_sources=rebuilt_sources,
            ):
                return False
            from graphify.export import backup_if_protected as _backup
            _backup(out)
            graph_tmp.replace(existing_graph)
            report_path.write_text(report, encoding="utf-8")
            labels_file.write_text(labels_json, encoding="utf-8")

        (out / ".graphify_root").write_text(str(watch_path), encoding="utf-8")

        try:
            from graphify.detect import save_manifest
            save_manifest(detected["files"], kind="ast", root=project_root)
        except Exception:
            pass

        # to_html raises ValueError for graphs > MAX_NODES_FOR_VIZ (5000).
        # Wrap so core outputs (graph.json + GRAPH_REPORT.md) always land.
        html_written = False
        if not no_change:
            try:
                to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
                html_written = True
            except ValueError as viz_err:
                print(f"[graphify watch] Skipped graph.html: {viz_err}")
                stale = out / "graph.html"
                if stale.exists():
                    stale.unlink()

        # Regenerate callflow HTML if the user previously generated one —
        # opt-in by existence so users who never ran callflow-html aren't affected.
        callflow_files = list(out.glob("*-callflow.html"))
        if callflow_files and not no_change:
            try:
                from graphify.callflow_html import write_callflow_html
                for cf in callflow_files:
                    write_callflow_html(
                        graph=out / "graph.json",
                        report=out / "GRAPH_REPORT.md",
                        labels=out / ".graphify_labels.json",
                        output=cf,
                        verbose=False,
                    )
            except Exception as cf_err:
                print(f"[graphify watch] callflow HTML update skipped: {cf_err}")

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        if not no_change:
            print(f"[graphify watch] Rebuilt: {G.number_of_nodes()} nodes, "
                  f"{G.number_of_edges()} edges, {len(communities)} communities")
            products = "graph.json" + (", graph.html" if html_written else "") + " and GRAPH_REPORT.md"
            if callflow_files:
                products += f", {len(callflow_files)} callflow HTML"
            print(f"[graphify watch] {products} updated in {out}")
        return True

    except Exception as exc:
        print(f"[graphify watch] Rebuild failed: {exc}")
        return False


def check_update(watch_path: Path) -> bool:
    """Check for pending semantic update flag and notify the user if set.

    Cron-safe: always returns True so cron jobs do not alarm.
    Non-code file changes (docs, papers, images) require LLM-backed
    re-extraction via `/graphify --update` — this function only signals
    that the update is needed.
    """
    flag = Path(watch_path) / _GRAPHIFY_OUT / "needs_update"
    if flag.exists():
        print(f"[graphify check-update] Pending non-code changes in {watch_path}.")
        print("[graphify check-update] Run `/graphify --update` to apply semantic re-extraction.")
    return True


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    flag = watch_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[graphify watch] New or changed files detected in {watch_path}")
    print("[graphify watch] Non-code files changed - semantic re-extraction requires LLM.")
    print("[graphify watch] Run `/graphify --update` in Claude Code to update the graph.")
    print(f"[graphify watch] Flag written to {flag}")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(p.suffix.lower() not in _CODE_EXTENSIONS for p in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0) -> None:
    """
    Watch watch_path for new or modified files and auto-update the graph.

    For code-only changes: re-runs AST extraction + rebuild immediately (no LLM).
    For doc/paper/image changes: writes a needs_update flag and notifies the user
    to run /graphify --update (LLM extraction required).

    debounce: seconds to wait after the last change before triggering (avoids
    running on every keystroke when many files are saved at once).
    """
    try:
        from watchdog.observers import Observer
        from watchdog.observers.polling import PollingObserver
        from watchdog.events import FileSystemEventHandler
    except ImportError as e:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from e

    last_trigger: float = 0.0
    pending: bool = False
    changed: set[Path] = set()

    # Load .graphifyignore patterns ONCE at startup so the handler does not
    # re-parse the file on every filesystem event. Watchdog's handler runs on
    # the observer thread and is invoked for every event the OS delivers
    # (Time Machine writes, Docker/Colima VM I/O, Spotlight indexing, …) —
    # without this short-circuit a busy volume can saturate a CPU core
    # discarding events one extension at a time. (gh-928)
    watch_root_for_ignore = watch_path.resolve()
    ignore_patterns = _load_graphifyignore(watch_root_for_ignore)

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(os.fsdecode(event.src_path))
            # Check .graphifyignore BEFORE the extension/dotfile/out filters so
            # the cheapest short-circuit for users with broad ignore patterns
            # (node_modules/, .venv/, build/, …) fires first. _is_ignored
            # tolerates absolute paths outside watch_root via its internal
            # relative_to guard, so a stray symlinked event won't raise.
            if ignore_patterns and _is_ignored(path, watch_root_for_ignore, ignore_patterns):
                return
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            try:
                filter_parts = path.relative_to(watch_root_for_ignore).parts
            except ValueError:
                filter_parts = path.parts
            if any(part.startswith(".") for part in filter_parts):
                return
            if _GRAPHIFY_OUT in filter_parts:
                return
            last_trigger = time.monotonic()
            pending = True
            changed.add(path)

    handler = Handler()
    # Use polling observer on macOS — FSEvents can miss rapid saves in some editors
    observer = PollingObserver() if sys.platform == "darwin" else Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    print(f"[graphify watch] Watching {watch_path.resolve()} - press Ctrl+C to stop")
    print(f"[graphify watch] Code changes rebuild graph automatically. "
          f"Doc/image changes require /graphify --update.")
    print(f"[graphify watch] Debounce: {debounce}s")

    try:
        while True:
            time.sleep(0.5)
            if pending and (time.monotonic() - last_trigger) >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                print(f"\n[graphify watch] {len(batch)} file(s) changed")
                has_non_code = _has_non_code(batch)
                has_code = any(p.suffix.lower() in _CODE_EXTENSIONS for p in batch)
                if has_code:
                    _rebuild_code(watch_path)
                if has_non_code:
                    _notify_only(watch_path)
    except KeyboardInterrupt:
        print("\n[graphify watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watch a folder and auto-update the graphify graph")
    parser.add_argument("path", nargs="?", default=".", help="Folder to watch (default: .)")
    parser.add_argument("--debounce", type=float, default=3.0,
                        help="Seconds to wait after last change before updating (default: 3)")
    args = parser.parse_args()
    watch(Path(args.path), debounce=args.debounce)
