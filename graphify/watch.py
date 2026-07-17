"""Watch a project and atomically activate native Helix graph generations."""

from __future__ import annotations

import copy
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


_WATCHED_EXTENSIONS = {
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".rb",
    ".swift", ".kt", ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp",
    ".h", ".kts", ".md", ".txt", ".rst", ".pdf", ".png", ".jpg",
    ".jpeg", ".webp", ".gif", ".svg",
}
_CODE_EXTENSIONS = {
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".rb",
    ".swift", ".kt", ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp",
    ".h", ".kts",
}


def _write_build_config(out_dir: Path, *, excludes: list[str] | None) -> None:
    """Persist non-topology scan options used by watch/update."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ".graphify_build.json"
    payload = {"excludes": list(excludes or [])}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_build_excludes(out_dir: Path) -> list[str]:
    try:
        data = json.loads((out_dir / ".graphify_build.json").read_text(encoding="utf-8"))
        values = data.get("excludes", [])
        return [str(item) for item in values] if isinstance(values, list) else []
    except (OSError, ValueError):
        return []


@contextmanager
def _rebuild_lock(out_dir: Path, *, blocking: bool = False):
    """Serialize local rebuild preparation; Helix also enforces writer exclusion."""
    import fcntl

    out_dir.mkdir(parents=True, exist_ok=True)
    handle = (out_dir / ".graphify-rebuild.lock").open("a+")
    flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError:
            yield False
        else:
            yield True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


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
    raise_on_error: bool = False,
) -> bool:
    """Extract source and atomically activate topology, analysis, and state.

    ``update`` and git hooks leave ``include_semantic`` false, so they remain
    local AST-only refreshes.  The headless ``extract`` command enables it and
    feeds documents, papers, and images through the configured LLM backend.
    """
    watch_path = Path(watch_path).resolve()
    output_root = Path(output_root).resolve() if output_root is not None else watch_path
    out = output_root / _GRAPHIFY_OUT
    if acquire_lock:
        with _rebuild_lock(out, blocking=block_on_lock) as acquired:
            if not acquired:
                print(f"[graphify watch] Rebuild already in progress for {watch_path}.")
                return False
            return _rebuild_code(
                watch_path,
                changed_paths=changed_paths,
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
                raise_on_error=raise_on_error,
            )

    try:
        from graphify.analyze import god_nodes, suggest_questions, surprising_connections
        from graphify.build import build_from_json, build_merge
        from graphify.cluster import cluster, score_all
        from graphify.cache import check_semantic_cache, save_semantic_cache
        from graphify.detect import detect
        from graphify.export import to_html
        from graphify.extract import extract
        from graphify.helix.model import GraphBuildData
        from graphify.helix.native import HELIX_PYTHON_VERSION
        from graphify.helix.persistence import HelixEmbeddedStore
        from graphify.helix.state import community_records, community_summaries, new_state
        from graphify.report import generate

        out.mkdir(parents=True, exist_ok=True)
        _warn_obsolete_store(out)
        store_path = out / "graph.helix"
        detected = detect(
            watch_path,
            follow_symlinks=follow_symlinks,
            extra_excludes=_read_build_excludes(out) or None,
        )
        files_by_type = detected.get("files", {})
        code_files = [Path(item) for item in files_by_type.get("code", [])]
        semantic_files = [
            Path(item)
            for kind in ("document", "paper", "image")
            for item in files_by_type.get(kind, [])
        ]
        if deep_mode:
            semantic_files = [*code_files, *semantic_files]
        if code_only:
            semantic_files = []
        current_files = [*code_files, *semantic_files]
        current_absolute = {path.resolve() for path in current_files}

        deleted_sources: set[str] = set()
        if changed_paths is not None:
            requested = [Path(path).resolve() for path in changed_paths]
            extract_targets = [
                path for path in requested
                if path.resolve() in {item.resolve() for item in code_files} and path.is_file()
            ]
            semantic_targets = [
                path for path in requested
                if include_semantic
                and path.resolve() in {item.resolve() for item in semantic_files}
                and path.is_file()
            ]
            deleted_sources.update(
                path.relative_to(watch_path).as_posix()
                for path in requested
                if not path.exists() and path.is_relative_to(watch_path)
            )
        else:
            extract_targets = code_files
            semantic_targets = semantic_files if include_semantic else []

        previous_state = new_state()
        has_active_generation = False
        if store_path.is_dir():
            try:
                with HelixEmbeddedStore(store_path, read_only=True) as existing_store:
                    loaded = existing_store.load()
            except RuntimeError as exc:
                if "no active generation" not in str(exc):
                    raise
                loaded = None
            if loaded is not None:
                has_active_generation = True
                previous_state = copy.deepcopy(dict(loaded.state))
                if changed_paths is None:
                    current_sources = {
                        path.relative_to(watch_path).as_posix()
                        for path in current_files if path.is_relative_to(watch_path)
                    }
                    for node in loaded.graph.nodes():
                        attrs = node_attributes(loaded.graph, node.id)
                        source = attrs.get("source_file")
                        if source and source not in current_sources:
                            deleted_sources.add(str(source))

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

        if not extract_targets and not semantic_targets and not deleted_sources and not store_path.is_dir():
            print("[graphify watch] No supported source files found - nothing to rebuild.")
            return False

        ast_result = extract(
            extract_targets, root=watch_path, cache=cache_state
        ) if extract_targets else {
            "nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
        }
        selected_backend = backend
        semantic_result = {
            "nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0,
            "output_tokens": 0,
        }
        if semantic_targets:
            from graphify.llm import _extraction_system, detect_backend, extract_corpus_parallel

            semantic_mode = "deep" if deep_mode else None
            prompt = _extraction_system(deep=deep_mode)
            cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(
                [str(path) for path in semantic_targets],
                cache_state,
                root=watch_path,
                mode=semantic_mode,
                prompt=prompt,
            )
            uncached_targets = [Path(path) for path in uncached]
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
                    root=watch_path,
                    token_budget=token_budget,
                    max_concurrency=max_concurrency,
                    deep_mode=deep_mode,
                    cache=cache_state,
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
                    root=watch_path,
                    allowed_source_files=uncached_targets,
                    mode=semantic_mode,
                    prompt=prompt,
                    cache=cache_state,
                )
            else:
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
        result = {
            "nodes": [*ast_result.get("nodes", []), *semantic_result.get("nodes", [])],
            "edges": [*ast_result.get("edges", []), *semantic_result.get("edges", [])],
            "hyperedges": [
                *ast_result.get("hyperedges", []), *semantic_result.get("hyperedges", [])
            ],
            "input_tokens": ast_result.get("input_tokens", 0) + semantic_result.get("input_tokens", 0),
            "output_tokens": ast_result.get("output_tokens", 0) + semantic_result.get("output_tokens", 0),
        }
        build_data = (
            build_merge(
                [result],
                graph_path=store_path,
                prune_sources=sorted(deleted_sources),
                root=watch_path,
            )
            if has_active_generation
            else build_from_json(result, root=watch_path)
        )

        detection = {
            "files": {key: list(value) for key, value in files_by_type.items()},
            "total_files": detected.get("total_files", len(current_files)),
            "total_words": detected.get("total_words", 0),
        }
        with HelixEmbeddedStore(store_path) as store:
            with store.staged_graph(build_data) as staged:
                graph = staged.graph
                communities = {} if no_cluster else cluster(graph)
                cohesion = {} if no_cluster else score_all(graph, communities)
                labels = _community_labels(graph, communities)
                gods = god_nodes(graph)
                surprises = surprising_connections(graph, communities)
                questions = suggest_questions(graph, communities, labels)
                state = previous_state
                state["build"] = {
                    "helix_python_version": HELIX_PYTHON_VERSION,
                    "node_count": graph.node_count,
                    "edge_count": graph.edge_count,
                    "directed": graph.directed,
                    "multigraph": graph.multigraph,
                    "semantic": bool(semantic_targets) or bool(previous_state.get("semantic", {}).get("used")),
                    "source_root": str(watch_path),
                    "source_commit": _git_head(watch_path),
                }
                state["communities"] = community_records(
                    communities, labels=labels, cohesion=cohesion,
                    naming_source="generated",
                )
                state["analysis"] = {
                    "god_nodes": gods,
                    "surprises": surprises,
                    "suggested_questions": questions,
                    "community_summaries": community_summaries(graph, communities, labels),
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
                        path.relative_to(watch_path).as_posix(): {
                            "content_hash": _content_hash(path),
                            "semantic_hash": "",
                            "extractor_state": "ast",
                        }
                        for path in current_files if path.is_file() and path.is_relative_to(watch_path)
                    },
                    "extractor_state": {
                        "mode": "deep" if deep_mode else "semantic" if semantic_targets else "ast",
                        "backend": selected_backend if semantic_targets else None,
                    },
                    "extraction_cache": cache_state,
                }
                state["semantic"] = {
                    "used": bool(semantic_targets) or bool(previous_state.get("semantic", {}).get("used")),
                    "backend": selected_backend if semantic_targets else previous_state.get("semantic", {}).get("backend"),
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                }
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

        (out / ".graphify_root").write_text(str(watch_path), encoding="utf-8")
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
        print("[graphify check-update] Run `graphify update .` to apply semantic re-extraction.")
    return True


def _notify_only(watch_path: Path) -> None:
    flag = watch_path / _GRAPHIFY_OUT / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[graphify watch] Non-code files changed in {watch_path}; run `graphify update .`.")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(path.suffix.lower() not in _CODE_EXTENSIONS for path in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0) -> None:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as exc:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from exc

    watch_path = Path(watch_path).resolve()
    last_trigger = 0.0
    pending = False
    changed: list[Path] = []

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            source = event.src_path.decode() if isinstance(event.src_path, bytes) else event.src_path
            path = Path(source)
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            if any(part.startswith(".") for part in path.parts) or _GRAPHIFY_OUT in path.parts:
                return
            last_trigger = time.monotonic()
            pending = True
            if path not in changed:
                changed.append(path)

    observer = Observer()
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
                    _rebuild_code(watch_path, changed_paths=batch)
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
    args = parser.parse_args()
    watch(Path(args.path), debounce=args.debounce)
