"""Watch a project and atomically activate native Helix graph generations."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from .helix.model import node_attributes
from .paths import GRAPHIFY_OUT as _GRAPHIFY_OUT


_PENDING_FILENAME = ".pending_changes"
_PENDING_DRAIN_MAX_PASSES = 20


from graphify.detect import (  # noqa: E402
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PAPER_EXTENSIONS,
    _is_ignored,
    _load_graphifyignore,
)


_WATCHED_EXTENSIONS = CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _queue_pending(out_dir: Path, changed_paths: list[Path]) -> None:
    """Append an incremental change set for the active lock holder to drain."""
    if not changed_paths:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = "".join(f"{os.fspath(path)}\n" for path in changed_paths)
    with (out_dir / _PENDING_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _drain_pending(out_dir: Path) -> list[Path]:
    """Atomically consume and de-duplicate queued incremental paths."""
    pending = out_dir / _PENDING_FILENAME
    try:
        raw = pending.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    with contextlib.suppress(FileNotFoundError):
        pending.unlink()
    seen: set[str] = set()
    paths: list[Path] = []
    for line in raw.splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            paths.append(Path(value))
    return paths


def _merge_changed_paths(*sources: list[Path] | None) -> list[Path]:
    """Merge path lists in first-seen order."""
    seen: set[str] = set()
    merged: list[Path] = []
    for source in sources:
        for path in source or []:
            key = os.fspath(path)
            if key not in seen:
                seen.add(key)
                merged.append(path)
    return merged


def _write_build_config(
    out_dir: Path,
    *,
    excludes: list[str] | None,
    gitignore: bool | None = None,
) -> None:
    """Persist corpus-shaping scan options used by watch and update."""
    if not excludes and gitignore is None:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ".graphify_build.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if excludes:
        payload["excludes"] = list(excludes)
    if gitignore is not None:
        payload["gitignore"] = gitignore
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_build_excludes(out_dir: Path) -> list[str]:
    try:
        data = json.loads((out_dir / ".graphify_build.json").read_text(encoding="utf-8"))
        values = data.get("excludes", [])
        return [str(item) for item in values] if isinstance(values, list) else []
    except (OSError, ValueError):
        return []


def _read_build_gitignore(out_dir: Path) -> bool:
    try:
        data = json.loads((out_dir / ".graphify_build.json").read_text(encoding="utf-8"))
        value = data.get("gitignore")
        return value if isinstance(value, bool) else True
    except (OSError, ValueError):
        return True


def _stabilize_rebuild_cwd(watch_path: Path) -> bool:
    """Recover detached hooks whose inherited working directory was removed."""
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
            "[graphify watch] Rebuild failed: current working directory no longer "
            "exists and GRAPHIFY_REPO_ROOT is not set."
        )
        return False


@contextmanager
def _rebuild_lock(out_dir: Path, *, blocking: bool = False):
    """Serialize local rebuild preparation; Helix also enforces writer exclusion."""
    from graphify.helix.persistence import _StoreLock

    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / ".rebuild.lock"
    lock = _StoreLock(
        lock_path,
        shared=False,
        timeout=120.0 if blocking else 0.0,
    )
    acquired = False
    try:
        try:
            lock.acquire()
        except TimeoutError:
            yield False
        else:
            acquired = True
            yield True
    finally:
        lock.release()
        if acquired:
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _git_head(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
        check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _community_labels(graph, communities: dict[int, list]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for community_id, members in communities.items():
        ranked = sorted(
            members,
            key=lambda node: (
                -graph.degree(node).degree,
                str(node_attributes(graph, node).get("label", node)),
            ),
        )
        names = [
            str(node_attributes(graph, node).get("label", node))
            for node in ranked[:2]
        ]
        labels[community_id] = " & ".join(names) if names else f"Community {community_id}"
    return labels


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _warn_obsolete_store(out: Path) -> None:
    legacy = out / "graph.json"
    if legacy.exists():
        print(
            "[graphify] warning: graph.json is obsolete and ignored; rebuild from source to create graph.helix.",
            file=sys.stderr,
        )


def _check_shrink(
    force: bool,
    existing_data: dict,
    new_data: dict,
    tmp: Path | None = None,
    *,
    had_explicit_deletions: bool = False,
    rebuilt_sources: set[str] | None = None,
) -> bool:
    """Refuse unexplained node loss before activating a staged generation."""
    if force or not existing_data or had_explicit_deletions:
        return True
    existing_nodes = existing_data.get("nodes", [])
    new_nodes = new_data.get("nodes", [])
    if len(new_nodes) >= len(existing_nodes):
        return True
    if rebuilt_sources is not None:
        from graphify.build import _norm_source_file

        new_ids = {node.get("id") for node in new_nodes}
        lost = [node for node in existing_nodes if node.get("id") not in new_ids]

        def accounted(node: dict) -> bool:
            source = node.get("source_file")
            return bool(
                not source
                or source in rebuilt_sources
                or _norm_source_file(source) in rebuilt_sources
            )

        if all(accounted(node) for node in lost):
            return True
    if tmp is not None:
        if tmp.is_dir():
            import shutil

            shutil.rmtree(tmp)
        else:
            tmp.unlink(missing_ok=True)
    print(
        f"[graphify] WARNING: new graph has {len(new_nodes)} nodes but the active "
        f"graph.helix generation has {len(existing_nodes)}. Refusing to overwrite "
        "because untouched source nodes disappeared; pass --force to override.",
        file=sys.stderr,
    )
    return False


def _rebuild_code(
    watch_path: Path,
    *,
    output_root: Path | None = None,
    changed_paths: list[Path] | None = None,
    follow_symlinks: bool = False,
    force: bool = False,
    no_cluster: bool = False,
    acquire_lock: bool = True,
    block_on_lock: bool = False,
    include_semantic: bool = False,
    code_only: bool = False,
    backend: str | None = None,
    model: str | None = None,
    deep_mode: bool = False,
    token_budget: int = 60_000,
    max_concurrency: int = 4,
    retain_rollback: bool = False,
    raise_on_error: bool = False,
    _root_marker: str | None = None,
) -> bool:
    """Extract source and atomically activate topology, analysis, and state.

    ``update`` and git hooks leave ``include_semantic`` false, so they remain
    local AST-only refreshes.  The headless ``extract`` command enables it and
    feeds documents, papers, and images through the configured LLM backend.
    """
    watch_path = Path(watch_path)
    if _root_marker is None:
        _root_marker = os.fspath(watch_path)
    if not _stabilize_rebuild_cwd(watch_path):
        return False
    watch_path = watch_path.resolve()
    source_root = (
        watch_path
        if Path(_root_marker).is_absolute()
        else Path.cwd().resolve()
    )
    output_root = Path(output_root).resolve() if output_root is not None else watch_path
    out = output_root / _GRAPHIFY_OUT
    if acquire_lock:
        with _rebuild_lock(out, blocking=block_on_lock) as acquired:
            if not acquired:
                if changed_paths is not None:
                    _queue_pending(out, changed_paths)
                    print(
                        f"[graphify watch] Rebuild already in progress for {watch_path}; "
                        f"queued {len(changed_paths)} changed path(s)."
                    )
                else:
                    print(f"[graphify watch] Rebuild already in progress for {watch_path}.")
                return False

            queued = _drain_pending(out)
            first_paths = (
                None if changed_paths is None else _merge_changed_paths(changed_paths, queued)
            )

            def run_inner(paths: list[Path] | None) -> bool:
                return _rebuild_code(
                    watch_path,
                    changed_paths=paths,
                    output_root=output_root,
                    follow_symlinks=follow_symlinks,
                    force=force,
                    no_cluster=no_cluster,
                    acquire_lock=False,
                    include_semantic=include_semantic,
                    code_only=code_only,
                    backend=backend,
                    model=model,
                    deep_mode=deep_mode,
                    token_budget=token_budget,
                    max_concurrency=max_concurrency,
                    retain_rollback=retain_rollback,
                    raise_on_error=raise_on_error,
                    _root_marker=_root_marker,
                )

            result = run_inner(first_paths)
            if changed_paths is None:
                return result
            for _ in range(_PENDING_DRAIN_MAX_PASSES):
                late = _drain_pending(out)
                if not late:
                    break
                result = run_inner(late) and result
            return result

    try:
        from graphify.analyze import god_nodes, suggest_questions, surprising_connections
        from graphify.build import build_from_extraction
        from graphify.cluster import cluster, score_all
        from graphify.cache import check_semantic_cache, save_semantic_cache
        from graphify.detect import detect
        from graphify.export import to_html
        from graphify.extract import extract
        from graphify.helix.model import GraphBuildData
        from graphify.helix.native import HELIX_PYTHON_VERSION
        from graphify.helix.persistence import HelixEmbeddedStore
        from graphify.helix.state import (
            communities_from_state,
            community_records,
            community_summaries,
            labels_from_state,
            new_state,
        )
        from graphify.report import generate

        out.mkdir(parents=True, exist_ok=True)
        _warn_obsolete_store(out)
        store_path = out / "graph.helix"
        detected = detect(
            watch_path,
            follow_symlinks=follow_symlinks,
            extra_excludes=_read_build_excludes(out) or None,
            gitignore=_read_build_gitignore(out),
        )
        files_by_type = detected.get("files", {})
        code_files = [Path(item) for item in files_by_type.get("code", [])]
        semantic_files = [
            Path(item)
            for kind in ("document", "paper", "image")
            for item in files_by_type.get(kind, [])
        ]
        quick_document_files = [
            path
            for path in semantic_files
            if path.suffix.lower() in {".md", ".mdx", ".qmd", ".skill"}
        ]
        quick_files = [*code_files, *quick_document_files]
        if deep_mode:
            semantic_files = [*code_files, *semantic_files]
        if code_only:
            semantic_files = []
            quick_files = code_files
        current_files = [*code_files, *semantic_files]
        current_absolute = {
            identity
            for path in current_files
            for identity in (
                Path(os.path.abspath(path)),
                path.resolve(),
            )
        }

        def resolve_changed(path: Path) -> Path:
            if path.is_absolute():
                return Path(os.path.abspath(path))
            candidates = [
                Path(os.path.abspath(source_root / path)),
                Path(os.path.abspath(watch_path / path)),
            ]
            for candidate in candidates:
                if candidate in current_absolute:
                    return candidate
            for candidate in candidates:
                if candidate.exists():
                    return candidate
            return candidates[0] if candidates[0].is_relative_to(watch_path) else candidates[1]

        deleted_sources: set[str] = set()
        if changed_paths is not None:
            requested = [resolve_changed(Path(path)) for path in changed_paths]
            extract_targets = [
                path for path in requested
                if path.resolve() in {item.resolve() for item in quick_files} and path.is_file()
            ]
            semantic_targets = [
                path for path in requested
                if include_semantic
                and path.resolve() in {item.resolve() for item in semantic_files}
                and path.is_file()
            ]
            deleted_sources.update(
                path.relative_to(source_root).as_posix()
                for path in requested
                if not path.exists()
                and path.is_relative_to(watch_path)
                and path.is_relative_to(source_root)
            )
        else:
            extract_targets = quick_files
            semantic_targets = semantic_files if include_semantic else []

        previous_state = new_state()
        loaded = None
        existing_source_root = source_root
        marker = out / ".graphify_root"
        saved_root = Path(".")
        if marker.is_file():
            try:
                saved_root = Path(marker.read_text(encoding="utf-8").strip())
                existing_source_root = (
                    saved_root.resolve()
                    if saved_root.is_absolute()
                    else source_root
                )
            except (OSError, ValueError):
                pass
        if store_path.is_dir():
            try:
                # Updates are already a writer operation. Open through the
                # ordinary public writer so Helix can complete any required
                # embedded-format migration before Graphify takes a snapshot.
                with HelixEmbeddedStore(store_path) as existing_store:
                    loaded = existing_store.load()
                    previous_state = copy.deepcopy(dict(loaded.state))
            except RuntimeError as exc:
                if "no active generation" not in str(exc):
                    raise
            if loaded is not None:
                stored_files = previous_state.get("incremental", {}).get("files", {})
                stored_sources = (
                    [str(source) for source in stored_files]
                    if isinstance(stored_files, dict)
                    else []
                )
                if marker.is_file() and not saved_root.is_absolute() and saved_root != Path("."):
                    marker_prefix = saved_root.as_posix().rstrip("/") + "/"
                    if stored_sources and not any(
                        source.startswith(marker_prefix) for source in stored_sources
                    ):
                        existing_source_root = watch_path
                excluded_alive: set[str] = set()
                for source in stored_sources:
                    source_path = Path(str(source))
                    absolute = (
                        Path(os.path.abspath(source_path))
                        if source_path.is_absolute()
                        else Path(os.path.abspath(existing_source_root / source_path))
                    )
                    if not absolute.is_relative_to(watch_path):
                        continue
                    if not absolute.exists():
                        deleted_sources.add(str(source).replace("\\", "/"))
                    elif absolute not in current_absolute:
                        excluded_alive.add(str(source))
                if excluded_alive:
                    print(
                        "[graphify watch] fail-closed: kept native nodes from "
                        f"{len(excluded_alive)} excluded-but-existing source file(s)."
                    )

        semantic_backed_sources: set[str] = set()
        previous_cache = previous_state.get("incremental", {}).get(
            "extraction_cache", {}
        )
        if isinstance(previous_cache, dict):
            for entry in previous_cache.values():
                if not isinstance(entry, dict) or not str(entry.get("kind", "")).startswith(
                    "semantic"
                ):
                    continue
                result_value = entry.get("result", {})
                if not isinstance(result_value, dict):
                    continue
                for node in result_value.get("nodes", []):
                    if not isinstance(node, dict):
                        continue
                    source = node.get("source_file")
                    if source and Path(str(source)).suffix.lower() in {
                        ".md", ".mdx", ".qmd", ".skill",
                    }:
                        semantic_backed_sources.add(str(source).replace("\\", "/"))
        if semantic_backed_sources:
            extract_targets = [
                path
                for path in extract_targets
                if Path(os.path.abspath(path)).relative_to(source_root).as_posix()
                not in semantic_backed_sources
            ]

        cache_state = copy.deepcopy(
            previous_state.get("incremental", {}).get("extraction_cache", {})
        )
        if not isinstance(cache_state, dict):
            cache_state = {}
        if force or os.environ.get("GRAPHIFY_FORCE", "").strip() == "1":
            cache_state.clear()
        if deleted_sources:
            deleted_suffixes = {":" + source.replace("\\", "/") for source in deleted_sources}
            for key in list(cache_state):
                if any(key.endswith(suffix) for suffix in deleted_suffixes):
                    del cache_state[key]

        build_root = existing_source_root if loaded is not None else source_root

        def cached_source_paths(kind_prefix: str) -> list[Path]:
            paths: dict[str, Path] = {}
            for entry in cache_state.values():
                if not isinstance(entry, dict) or not str(entry.get("kind", "")).startswith(
                    kind_prefix
                ):
                    continue
                cached_result = entry.get("result", {})
                if not isinstance(cached_result, dict):
                    continue
                for bucket in ("nodes", "edges", "hyperedges"):
                    for item in cached_result.get(bucket, []):
                        if not isinstance(item, dict) or not item.get("source_file"):
                            continue
                        source_path = Path(str(item["source_file"]))
                        unresolved = (
                            source_path
                            if source_path.is_absolute()
                            else build_root / source_path
                        )
                        absolute = Path(os.path.abspath(unresolved))
                        if absolute.is_file():
                            paths[os.fspath(absolute)] = absolute
            return list(paths.values())

        if not extract_targets and not semantic_targets and not deleted_sources and not store_path.is_dir():
            print("[graphify watch] No supported source files found - nothing to rebuild.")
            return False

        # Build from extraction DTOs, never by projecting the active native
        # topology back into Python. ``extract`` receives the complete live file
        # set; unchanged files are served from the cache stored in Helix state,
        # while only invalidated files run an extractor.
        ast_candidates = {
            os.fspath(Path(os.path.abspath(path))): Path(os.path.abspath(path))
            for path in [*quick_files, *cached_source_paths("ast")]
            if Path(path).is_file()
        }
        ast_build_files = []
        for path in ast_candidates.values():
            try:
                relative = path.relative_to(build_root).as_posix()
            except ValueError:
                continue
            if relative not in semantic_backed_sources:
                ast_build_files.append(path)
        ast_result = extract(
            ast_build_files, root=build_root, cache=cache_state
        ) if ast_build_files else {
            "nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
        }
        selected_backend = backend
        semantic_result = {
            "nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0,
            "output_tokens": 0,
        }
        previous_semantic = previous_state.get("semantic", {})
        semantic_was_used = (
            isinstance(previous_semantic, dict)
            and bool(previous_semantic.get("used"))
        )
        semantic_build_files = (
            list({
                os.fspath(Path(os.path.abspath(path))): Path(os.path.abspath(path))
                for path in [*semantic_files, *cached_source_paths("semantic")]
                if Path(path).is_file()
            }.values())
            if include_semantic or semantic_was_used
            else []
        )
        if semantic_build_files:
            from graphify.llm import _extraction_system, detect_backend, extract_corpus_parallel

            previous_mode = previous_state.get("incremental", {}).get(
                "extractor_state", {}
            ).get("mode")
            effective_deep = deep_mode or (not include_semantic and previous_mode == "deep")
            semantic_mode = "deep" if effective_deep else None
            prompt = _extraction_system(deep=effective_deep)
            cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(
                [str(path) for path in semantic_build_files],
                cache_state,
                root=build_root,
                mode=semantic_mode,
                prompt=prompt,
                allow_stale=not include_semantic,
            )
            requested_semantic = {
                Path(os.path.abspath(path)) for path in semantic_targets
            }
            uncached_targets = [
                Path(path)
                for path in uncached
                if include_semantic and Path(os.path.abspath(path)) in requested_semantic
            ]
            fresh = {
                "nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 0, "output_tokens": 0,
            }
            if uncached_targets:
                selected_backend = backend or detect_backend()
                if selected_backend is None:
                    raise RuntimeError(
                        "semantic sources were detected but no LLM backend is configured; "
                        "pass --backend, configure an API key, or use --code-only"
                    )
                fresh = extract_corpus_parallel(
                    uncached_targets,
                    backend=selected_backend,
                    model=model,
                    root=build_root,
                    token_budget=token_budget,
                    max_concurrency=max_concurrency,
                    deep_mode=effective_deep,
                    cache=cache_state,
                    cache_root=output_root,
                )
                if fresh.get("failed_chunks"):
                    raise RuntimeError(
                        f"semantic extraction failed for {fresh['failed_chunks']} chunk(s); "
                        "the active generation was left unchanged"
                    )
                save_semantic_cache(
                    fresh.get("nodes", []),
                    fresh.get("edges", []),
                    fresh.get("hyperedges", []),
                    root=build_root,
                    cache_root=output_root,
                    allowed_source_files=uncached_targets,
                    mode=semantic_mode,
                    prompt=prompt,
                    cache=cache_state,
                )
            elif not uncached:
                selected_backend = (
                    backend or previous_state.get("semantic", {}).get("backend")
                )
            semantic_result = {
                "nodes": [*cached_nodes, *fresh.get("nodes", [])],
                "edges": [*cached_edges, *fresh.get("edges", [])],
                "hyperedges": [*cached_hyperedges, *fresh.get("hyperedges", [])],
                "input_tokens": fresh.get("input_tokens", 0),
                "output_tokens": fresh.get("output_tokens", 0),
            }
        current_files = list({
            os.fspath(Path(os.path.abspath(path))): Path(os.path.abspath(path))
            for path in [*current_files, *ast_build_files, *semantic_build_files]
            if Path(path).is_file()
        }.values())
        result = {
            "nodes": [*ast_result.get("nodes", []), *semantic_result.get("nodes", [])],
            "edges": [*ast_result.get("edges", []), *semantic_result.get("edges", [])],
            "hyperedges": [
                *ast_result.get("hyperedges", []), *semantic_result.get("hyperedges", [])
            ],
            "input_tokens": ast_result.get("input_tokens", 0) + semantic_result.get("input_tokens", 0),
            "output_tokens": ast_result.get("output_tokens", 0) + semantic_result.get("output_tokens", 0),
        }
        build_data = build_from_extraction(result, root=build_root)
        if loaded is not None:
            previous_files = previous_state.get("incremental", {}).get("files", {})
            expected_sources = {
                str(path).replace("\\", "/")
                for path in previous_files
                if isinstance(path, str)
                and (build_root / path).is_file()
            } if isinstance(previous_files, dict) else set()
            candidate_sources = {
                str(node.attributes.get("source_file", "")).replace("\\", "/")
                for node in build_data.nodes
                if node.attributes.get("source_file")
            }
            missing_live_sources = expected_sources - candidate_sources
            if missing_live_sources and not force:
                sample = ", ".join(sorted(missing_live_sources)[:5])
                print(
                    "[graphify] WARNING: extraction omitted live source file(s) "
                    f"present in the active generation ({sample}); pass --force "
                    "after confirming the extractor change.",
                    file=sys.stderr,
                )
                return False

        detection = {
            "files": {key: list(value) for key, value in files_by_type.items()},
            "total_files": detected.get("total_files", len(current_files)),
            "total_words": detected.get("total_words", 0),
        }

        def analyze_generation(graph, *, reuse_communities: bool = False):
            if no_cluster:
                communities = {}
                cohesion = {}
                labels = {}
            elif reuse_communities:
                communities = communities_from_state(previous_state)
                labels = labels_from_state(previous_state)
                cohesion = {
                    int(record["id"]): float(record["cohesion"])
                    for record in previous_state.get("communities", [])
                    if isinstance(record, dict)
                    and isinstance(record.get("id"), int)
                    and isinstance(record.get("cohesion"), (int, float))
                }
            else:
                communities = cluster(graph)
                cohesion = score_all(graph, communities)
                labels = _community_labels(graph, communities)
            gods = god_nodes(graph)
            surprises = surprising_connections(graph, communities)
            questions = suggest_questions(graph, communities, labels)
            state = copy.deepcopy(previous_state)
            state["build"] = {
                "helix_python_version": HELIX_PYTHON_VERSION,
                "node_count": graph.node_count,
                "edge_count": graph.edge_count,
                "directed": graph.directed,
                "multigraph": graph.multigraph,
                "semantic": bool(semantic_targets)
                or bool(previous_state.get("semantic", {}).get("used")),
                "source_root": str(source_root),
                "source_commit": _git_head(watch_path),
            }
            state["communities"] = community_records(
                communities,
                labels=labels,
                cohesion=cohesion,
                naming_source="generated",
            )
            state["analysis"] = {
                "god_nodes": gods,
                "surprises": surprises,
                "suggested_questions": questions,
                "confidence_counts": {
                    confidence: sum(
                        1
                        for edge in build_data.edges
                        if str(edge.attributes.get("confidence", "EXTRACTED"))
                        == confidence
                    )
                    for confidence in ("EXTRACTED", "INFERRED", "AMBIGUOUS")
                },
                "community_summaries": community_summaries(
                    graph, communities, labels
                ),
                "report_inputs": {
                    "detection": detection,
                    "tokens": {
                        "input": result.get("input_tokens", 0),
                        "output": result.get("output_tokens", 0),
                    },
                    "source": str(watch_path),
                },
            }
            state["incremental"] = {
                "files": {
                    path.relative_to(build_root).as_posix(): {
                        "content_hash": _content_hash(path),
                        "semantic_hash": "",
                        "extractor_state": "ast",
                    }
                    for path in current_files
                    if path.is_file() and path.is_relative_to(build_root)
                },
                "extractor_state": {
                    "mode": "deep" if deep_mode else "semantic" if semantic_targets else "ast",
                    "backend": selected_backend if semantic_targets else None,
                },
                "extraction_cache": cache_state,
            }
            state["semantic"] = {
                "used": bool(semantic_targets)
                or bool(previous_state.get("semantic", {}).get("used")),
                "backend": selected_backend
                if semantic_targets
                else previous_state.get("semantic", {}).get("backend"),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
            }
            return communities, cohesion, labels, gods, surprises, questions, state

        with HelixEmbeddedStore(
            store_path, retain_rollback=retain_rollback
        ) as store:
            topology_unchanged = loaded is not None and store.topology_matches(build_data)
            if topology_unchanged:
                assert loaded is not None
                graph = loaded.graph
                (
                    communities,
                    cohesion,
                    labels,
                    gods,
                    surprises,
                    questions,
                    state,
                ) = analyze_generation(graph, reuse_communities=True)
                store.replace_state(
                    state,
                    previous_state=previous_state,
                    snapshot=loaded,
                )
                print("[graphify watch] No code-graph topology changes detected.")
            else:
                with store.staged_graph(build_data) as staged:
                    graph = staged.graph
                    (
                        communities,
                        cohesion,
                        labels,
                        gods,
                        surprises,
                        questions,
                        state,
                    ) = analyze_generation(graph)
                    activated = store.activate_staged(staged, state)
                    graph = activated.graph

        report = generate(
            graph, communities, cohesion, labels, gods, surprises, detection,
            {
                "input": result.get("input_tokens", 0),
                "output": result.get("output_tokens", 0),
            }, str(watch_path),
            suggested_questions=questions, built_at_commit=_git_head(watch_path),
            learning=state.get("learning", {}),
        )
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        try:
            to_html(graph, communities, str(out / "graph.html"), community_labels=labels)
        except ValueError as exc:
            print(f"[graphify watch] Skipped graph.html: {exc}")
            (out / "graph.html").unlink(missing_ok=True)

        for callflow in out.glob("*-callflow.html"):
            try:
                from graphify.callflow_html import write_callflow_html

                write_callflow_html(
                    graph=store_path, report=out / "GRAPH_REPORT.md",
                    output=callflow,
                    verbose=False,
                )
            except Exception as exc:
                print(f"[graphify watch] callflow HTML update skipped: {exc}")

        (out / ".graphify_root").write_text(_root_marker, encoding="utf-8")
        (out / "needs_update").unlink(missing_ok=True)
        print(
            f"[graphify watch] Rebuilt: {graph.node_count} nodes, {graph.edge_count} edges, "
            f"{len(communities)} communities"
        )
        print(f"[graphify watch] graph.helix and GRAPH_REPORT.md updated in {out}")
        return True
    except Exception as exc:
        if raise_on_error:
            raise
        print(f"[graphify watch] Rebuild failed: {exc}")
        return False


def check_update(watch_path: Path) -> bool:
    flag = Path(watch_path) / _GRAPHIFY_OUT / "needs_update"
    if flag.exists():
        print(f"[graphify check-update] Pending non-code changes in {watch_path}.")
        print("[graphify check-update] Run `graphify --update` to apply semantic re-extraction.")
    return True


def _notify_only(watch_path: Path) -> None:
    flag = watch_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[graphify watch] Non-code files changed in {watch_path}; run `graphify update .`.")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(path.suffix.lower() not in _CODE_EXTENSIONS for path in changed_paths)


def watch(
    watch_path: Path,
    debounce: float = 3.0,
    *,
    retain_rollback: bool = False,
) -> None:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
        from watchdog.observers.polling import PollingObserver
    except ImportError as exc:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from exc

    watch_path = Path(watch_path).resolve()
    last_trigger = 0.0
    pending = False
    changed: list[Path] = []
    ignore_root = watch_path.resolve()
    ignore_patterns = _load_graphifyignore(
        ignore_root,
        gitignore=_read_build_gitignore(watch_path / _GRAPHIFY_OUT),
    )

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(os.fsdecode(event.src_path))
            if ignore_patterns and _is_ignored(path, ignore_root, ignore_patterns):
                return
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            try:
                filter_parts = path.relative_to(ignore_root).parts
            except ValueError:
                filter_parts = path.parts
            if any(part.startswith(".") for part in filter_parts) or _GRAPHIFY_OUT in filter_parts:
                return
            last_trigger = time.monotonic()
            pending = True
            if path not in changed:
                changed.append(path)

    observer = PollingObserver() if sys.platform == "darwin" else Observer()
    observer.schedule(Handler(), str(watch_path), recursive=True)
    observer.start()
    print(f"[graphify watch] Watching {watch_path} - press Ctrl+C to stop")
    try:
        while True:
            time.sleep(0.5)
            if pending and time.monotonic() - last_trigger >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                if _has_non_code(batch):
                    _notify_only(watch_path)
                else:
                    _rebuild_code(
                        watch_path,
                        changed_paths=batch,
                        retain_rollback=retain_rollback,
                    )
    except KeyboardInterrupt:
        print("\n[graphify watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Watch a folder and update graph.helix")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--debounce", type=float, default=3.0)
    parser.add_argument("--retain-rollback", action="store_true")
    args = parser.parse_args()
    watch(
        Path(args.path),
        debounce=args.debounce,
        retain_rollback=args.retain_rollback,
    )
