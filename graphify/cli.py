"""Helix-only command dispatch for every non-install Graphify command."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT


_SEARCH_NUDGE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "MANDATORY: graphify-out/graph.helix exists. Run "
            "`graphify query \"<question>\"` before broad source searches."
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_READ_NUDGE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "MANDATORY: orient with graphify-out/graph.helix before broad source reads. "
            "Use `graphify query`, `graphify explain`, or `graphify path`."
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_READ_NUDGE_STALE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "graphify-out/graph.helix may be stale for this file. Use `graphify query` "
            "for orientation and run `graphify update`; reading the file is allowed."
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_READ_DENY = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "graphify strict mode: run `graphify query <question>`, `graphify explain`, "
            "or `graphify path` first, then retry this read. This blocks at most once "
            "per session."
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_HOOK_SOURCE_EXTS = (
    ".py", ".js", ".cjs", ".ts", ".tsx", ".jsx", ".astro", ".vue", ".svelte",
    ".go", ".rs", ".java", ".rb", ".c", ".h", ".cpp", ".hpp", ".cc",
    ".cs", ".kt", ".swift", ".php", ".scala", ".lua", ".sh", ".md",
    ".rst", ".txt", ".mdx",
)
_GEMINI_NUDGE_TEXT = (
    "graphify: native knowledge graph at graphify-out/graph.helix. "
    "Use `graphify query \"<question>\"` before broad source searches."
)


class _StageTimer:
    def __init__(self, enabled: bool) -> None:
        import time

        self._now = time.perf_counter
        self.enabled = enabled
        self.start = self._now()
        self._last = self.start

    def mark(self, stage: str) -> None:
        now = self._now()
        if self.enabled:
            print(f"[graphify timing] {stage}: {now - self._last:.1f}s", file=sys.stderr)
        self._last = now

    def total(self) -> None:
        if self.enabled:
            print(f"[graphify timing] total: {self._now() - self.start:.1f}s", file=sys.stderr)


def _default_graph_path() -> str:
    return str(Path(_GRAPHIFY_OUT) / "graph.helix")


def _option(args: list[str], *names: str) -> str | None:
    for index, value in enumerate(args):
        for name in names:
            if value == name and index + 1 < len(args):
                return args[index + 1]
            if value.startswith(name + "="):
                return value.split("=", 1)[1]
    return None


def _options(args: list[str], *names: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(args):
        value = args[index]
        matched = False
        for name in names:
            if value == name and index + 1 < len(args):
                values.append(args[index + 1])
                index += 2
                matched = True
                break
            if value.startswith(name + "="):
                values.append(value.split("=", 1)[1])
                index += 1
                matched = True
                break
        if not matched:
            index += 1
    return values


def _store_arg(args: list[str], *, default: str | Path | None = None) -> Path:
    value = _option(args, "--store", "--graph") or str(
        default or Path(_GRAPHIFY_OUT) / "graph.helix"
    )
    path = Path(value).expanduser()
    if path.suffix.lower() == ".json" or path.is_file():
        raise ValueError(
            "legacy JSON graphs are obsolete; pass a graph.helix store and rebuild from source"
        )
    return path


def _validate_store_or_exit(gp: Path) -> None:
    """Validate a native store path for command-line callers."""
    from graphify.security import validate_store_path

    try:
        validate_store_path(gp)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _hook_strict_enabled(flag: bool) -> bool:
    value = os.environ.get("GRAPHIFY_HOOK_STRICT", "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return flag


def _touch_query_stamp(graph_path: Path) -> None:
    try:
        from graphify.paths import write_text_atomic

        stamp = graph_path.parent / "cache" / "last_query_stamp"
        stamp.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(stamp, str(time.time()))
    except Exception:
        pass


def _query_stamp_fresh() -> bool:
    from graphify.paths import out_path

    try:
        ttl = float(os.environ.get("GRAPHIFY_HOOK_STRICT_TTL", "1800"))
        return time.time() - out_path("cache", "last_query_stamp").stat().st_mtime < ttl
    except Exception:
        return False


def _mark_session_denied(session_id: str) -> bool:
    from graphify.paths import out_path

    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))[:64]
    if not safe_id:
        return False
    try:
        directory = out_path("cache", "hook_sessions")
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            str(directory / f"{safe_id}.denied"),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
        os.close(fd)
        return True
    except (FileExistsError, OSError):
        return False


def _target_is_indexed(file_path: str, root: Path) -> bool:
    from graphify.paths import out_path

    if not file_path:
        return True
    try:
        manifest_path = out_path("manifest.json")
        if manifest_path.stat().st_size > 2_000_000:
            return True
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not manifest:
            return True
        path = Path(file_path)
        relative: set[str] = {path.name}
        try:
            relative.add(path.resolve().relative_to(root).as_posix())
        except (ValueError, OSError, RuntimeError):
            pass
        keys = {str(key).replace("\\", "/") for key in manifest}
        absolute = str(path).replace("\\", "/")
        return absolute in keys or any(
            value and any(key == value or key.endswith("/" + value) for key in keys)
            for value in relative
        )
    except Exception:
        return True


def _run_hook_guard(kind: str, strict: bool = False) -> None:
    from graphify.paths import GRAPHIFY_OUT_NAME, out_path

    if kind == "gemini":
        payload: dict[str, Any] = {"decision": "allow"}
        try:
            if out_path("graph.helix").is_dir():
                payload["additionalContext"] = _GEMINI_NUDGE_TEXT
        except Exception:
            pass
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not isinstance(data, dict):
            return
        tool_input = data.get("tool_input", data)
        if not isinstance(tool_input, dict):
            return
        store_path = out_path("graph.helix")
        if not store_path.is_dir():
            return
        if kind == "search":
            command = str(tool_input.get("command", ""))
            is_grep_tool = not command and bool(tool_input.get("pattern"))
            is_bash_search = any(
                token in command
                for token in ("grep", "ripgrep", "rg ", "find ", "fd ", "ack ", "ag ")
            )
            if is_grep_tool or is_bash_search:
                sys.stdout.write(_SEARCH_NUDGE)
            return
        if kind != "read":
            return

        values = [
            str(tool_input.get("file_path") or ""),
            str(tool_input.get("pattern") or ""),
            str(tool_input.get("path") or ""),
        ]
        joined = " ".join(values).lower().replace("\\", "/")
        tails = [Path(value).suffix.lower() for value in values if value]
        if GRAPHIFY_OUT_NAME.lower() + "/" in joined or not any(
            extension in _HOOK_SOURCE_EXTS for extension in tails
        ):
            return

        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        try:
            root = root.resolve()
        except (OSError, RuntimeError):
            pass
        explicit = [
            str(tool_input.get(name) or "")
            for name in ("file_path", "path")
            if tool_input.get(name)
        ]
        if explicit:
            in_project = False
            for value in explicit:
                path = Path(value)
                if not path.is_absolute():
                    in_project = True
                    break
                try:
                    path.resolve().relative_to(root)
                    in_project = True
                    break
                except (ValueError, OSError, RuntimeError):
                    continue
            if not in_project:
                return

        graph_mtime = store_path.stat().st_mtime
        file_path = str(tool_input.get("file_path") or "")
        stale = False
        if file_path:
            try:
                stale = Path(file_path).stat().st_mtime > graph_mtime
            except OSError:
                pass
        if out_path("needs_update").exists():
            stale = True
        if stale:
            sys.stdout.write(_READ_NUDGE_STALE)
            return
        if (
            _hook_strict_enabled(strict)
            and data.get("tool_name") in (None, "Read")
            and not _query_stamp_fresh()
            and _target_is_indexed(file_path, root)
            and _mark_session_denied(str(data.get("session_id") or ""))
        ):
            sys.stdout.write(_READ_DENY)
            return
        sys.stdout.write(_READ_NUDGE)
    except Exception:
        return


def _clone_repo(url: str, branch: str | None = None, out_dir: Path | None = None) -> Path:
    import re
    import subprocess

    clean = url.rstrip("/")
    git_url = clean if clean.endswith(".git") else clean + ".git"
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", clean)
    if not match:
        raise ValueError(f"not a recognized GitHub URL: {url}")
    owner, repo = match.group(1), match.group(2)
    destination = out_dir or Path.home() / ".graphify" / "repos" / owner / repo
    if branch and branch.startswith("-"):
        raise ValueError(f"invalid branch name: {branch!r}")
    if destination.exists():
        command = ["git", "-C", str(destination), "pull"]
        if branch:
            command += ["origin", "--", branch]
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--depth", "1"]
        if branch:
            command += ["--branch", branch]
        command += ["--", git_url, str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    print(f"Ready at: {destination}")
    return destination


def _loaded(args: list[str]):
    from graphify.helix.persistence import load_graph
    from graphify.security import validate_store_path

    return load_graph(validate_store_path(_store_arg(args)))


def _communities(loaded) -> tuple[dict[int, list[Any]], dict[int, str], dict[int, float]]:
    communities: dict[int, list[Any]] = {}
    labels: dict[int, str] = {}
    cohesion: dict[int, float] = {}
    for record in loaded.state.get("communities", []):
        if not isinstance(record, dict) or not isinstance(record.get("id"), int):
            continue
        cid = record["id"]
        communities[cid] = list(record.get("members", []))
        labels[cid] = str(record.get("name") or f"Community {cid}")
        if isinstance(record.get("cohesion"), (int, float)):
            cohesion[cid] = float(record["cohesion"])
    return communities, labels, cohesion


def _query(args: list[str]) -> None:
    from graphify.serve import _query_graph_text

    question = args[0] if args and not args[0].startswith("-") else ""
    if not question:
        raise ValueError("query requires a question")
    loaded = _loaded(args)
    _touch_query_stamp(loaded.store_path)
    budget = int(_option(args, "--budget") or 2000)
    mode = "dfs" if "--dfs" in args else "bfs"
    filters: list[str] = []
    for index, value in enumerate(args):
        if value == "--context" and index + 1 < len(args):
            filters.append(args[index + 1])
        elif value.startswith("--context="):
            filters.append(value.split("=", 1)[1])
    print(_query_graph_text(
        loaded.graph,
        question,
        native_query=loaded.query,
        mode=mode,
        depth=2,
        token_budget=budget,
        context_filters=filters,
        learning_overlay=(
            dict(learning.get("nodes", {}))
            if isinstance((learning := loaded.state.get("learning", {})), dict)
            else {}
        ),
    ))


def _path(args: list[str]) -> None:
    from graphify.helix.model import edge_attributes, node_attributes
    from graphify.serve import _pick_scored_endpoint, _query_terms, _score_nodes

    positional = [value for value in args if not value.startswith("-")]
    if len(positional) < 2:
        raise ValueError("path requires source and target")
    loaded = _loaded(args)
    _touch_query_stamp(loaded.store_path)
    graph = loaded.graph
    source_scores = _score_nodes(
        graph, _query_terms(positional[0]), native_query=loaded.query
    )
    target_scores = _score_nodes(
        graph, _query_terms(positional[1]), native_query=loaded.query
    )
    if not source_scores or not target_scores:
        raise ValueError("source or target did not resolve uniquely")
    source = _pick_scored_endpoint(graph, source_scores, positional[0])
    target = _pick_scored_endpoint(graph, target_scores, positional[1])
    result = graph.shortest_path(source, target, direction="both")
    node_ids = getattr(result, "node_ids", ())
    if not node_ids:
        print("No path found.")
        raise SystemExit(0)
    path = list(node_ids)
    segments = []
    for index, (left, right) in enumerate(zip(path, path[1:])):
        records = [
            graph.edge(edge_id)
            for edge_id in graph.incident_edge_ids(left)
        ]
        edge = next(
            (
                record for record in records
                if record is not None
                and {record.source, record.target} == {left, right}
            ),
            None,
        )
        if edge is None:
            raise RuntimeError("native shortest path returned an edge-less hop")
        attrs = edge_attributes(edge)
        relation = attrs.get("relation", "related")
        confidence = attrs.get("confidence")
        confidence_text = f" [{confidence}]" if confidence else ""
        if index == 0:
            segments.append(str(node_attributes(graph, left).get("label", left)))
        label = str(node_attributes(graph, right).get("label", right))
        if edge.source == left and edge.target == right:
            segments.append(f"--{relation}{confidence_text}--> {label}")
        else:
            segments.append(f"<--{relation}{confidence_text}-- {label}")
    print(f"Shortest path ({len(path) - 1} hops):\n  " + " ".join(segments))


def _explain(args: list[str]) -> None:
    from graphify.helix.model import edge_attributes, node_attributes
    from graphify.serve import _find_node

    query = next((value for value in args if not value.startswith("-")), "")
    if not query:
        raise ValueError("explain requires a node label or ID")
    loaded = _loaded(args)
    _touch_query_stamp(loaded.store_path)
    graph = loaded.graph
    matches = _find_node(graph, query, native_query=loaded.query)
    if len(matches) > 1:
        query_path = query.replace("\\", "/")
        file_matches = [
            node_id for node_id in matches
            if str(node_attributes(graph, node_id).get("source_file", "")).replace("\\", "/") == query_path
            and str(node_attributes(graph, node_id).get("label", "")) == Path(query_path).name
        ]
        if len(file_matches) == 1:
            matches = file_matches
    if len(matches) != 1:
        print(f"No unique node match for {query}")
        return
    node_id = matches[0]
    attrs = node_attributes(graph, node_id)
    print(f"Node: {attrs.get('label', node_id)}")
    print(f"ID:        {node_id}")
    print(f"Source:    {attrs.get('source_file', '-')} {attrs.get('source_location', '')}".rstrip())
    print(f"Type:      {attrs.get('file_type', '-')}" )
    print(f"Degree:    {graph.degree(node_id).degree}")
    from graphify.reflect import load_learning_overlay

    entry = load_learning_overlay(loaded.store_path).get(str(node_id))
    if isinstance(entry, dict) and entry.get("status"):
        status = entry["status"]
        if status == "preferred":
            lesson = (
                f"Lesson: preferred source (start here) — {entry.get('uses', 0)} useful, "
                f"score={entry.get('score', 0)}"
            )
        elif status == "contested":
            lesson = (
                f"Lesson: contested (useful {entry.get('uses', 0)} / "
                f"dead-end {entry.get('neg', 0)})"
            )
        else:
            lesson = f"Lesson: {status} ({entry.get('uses', 0)} useful)"
        if entry.get("stale"):
            lesson += " [code changed since — re-verify]"
        print(lesson)
    print("Connections:")
    for edge_id in graph.incident_edge_ids(node_id):
        edge = graph.edge(edge_id)
        if edge is None:
            continue
        neighbor = edge.target if edge.source == node_id else edge.source
        relation = edge_attributes(edge).get("relation", "related")
        arrow = "-->" if edge.source == node_id else "<--"
        print(f"  {arrow} {node_attributes(graph, neighbor).get('label', neighbor)} [{relation}]")


def _export(args: list[str]) -> None:
    if not args:
        raise ValueError("export requires a format")
    kind = args[0]
    tail = args[1:]
    positional_store = tail[0] if tail and not tail[0].startswith("-") else None
    store_args = ["--store", positional_store, *tail[1:]] if positional_store else tail
    store_path = _store_arg(store_args)
    from graphify.helix.persistence import load_graph
    from graphify.security import validate_store_path

    loaded = load_graph(validate_store_path(store_path))
    graph = loaded.graph
    communities, labels, cohesion = _communities(loaded)
    output = _option(args, "--out", "--output")
    from graphify import export

    if kind == "html":
        html_output = output or str(Path(_GRAPHIFY_OUT) / "graph.html")
        if "--no-viz" in args:
            Path(html_output).unlink(missing_ok=True)
        else:
            export.to_html(graph, communities, html_output, community_labels=labels)
    elif kind == "graphml":
        export.to_graphml(graph, communities, output or str(Path(_GRAPHIFY_OUT) / "graph.graphml"))
    elif kind in {"cypher", "neo4j", "falkordb"}:
        export.to_cypher(graph, output or str(Path(_GRAPHIFY_OUT) / "cypher.txt"))
    elif kind == "svg":
        export.to_svg(graph, communities, output or str(Path(_GRAPHIFY_OUT) / "graph.svg"), community_labels=labels)
    elif kind == "obsidian":
        count = export.to_obsidian(
            graph, communities, output or str(Path(_GRAPHIFY_OUT) / "obsidian"),
            community_labels=labels, cohesion=cohesion,
        )
        print(f"Wrote {count} Obsidian notes.")
    elif kind == "canvas":
        export.to_canvas(graph, communities, output or str(Path(_GRAPHIFY_OUT) / "graph.canvas"), community_labels=labels)
    elif kind == "wiki":
        from graphify.wiki import to_wiki

        count = to_wiki(
            graph, communities, output or str(Path(_GRAPHIFY_OUT) / "wiki"),
            community_labels=labels, cohesion=cohesion,
            god_nodes_data=list(loaded.state.get("analysis", {}).get("god_nodes", [])),
        )
        print(f"Wrote {count} wiki articles.")
    elif kind == "callflow-html":
        from graphify.callflow_html import write_callflow_html

        result = write_callflow_html(graph=store_path, output=output, verbose=True)
        print(result)
    else:
        raise ValueError(f"unknown export format: {kind}")


def _global(args: list[str]) -> None:
    from graphify.global_graph import global_add, global_list, global_path, global_remove

    if not args or args[0] == "list":
        repos = global_list()
        if not repos:
            print("No projects in the global graph.")
        for tag, record in sorted(repos.items()):
            print(f"{tag}: {record.get('node_count', 0)} nodes ({record.get('source_path', '')})")
        return
    if args[0] == "add" and len(args) >= 2:
        source = Path(args[1])
        tag = _option(args[2:], "--as") or source.resolve().name
        print(global_add(source, tag, retain_rollback="--retain-rollback" in args))
        return
    if args[0] == "remove" and len(args) >= 2:
        print(
            f"Removed {global_remove(args[1], retain_rollback='--retain-rollback' in args)} "
            "nodes."
        )
        return
    if args[0] == "path":
        print(global_path())
        return
    raise ValueError("usage: graphify global add <project|graph.helix> [--as TAG] | remove TAG | list | path")


def _update_or_extract(cmd: str, args: list[str]) -> None:
    from graphify.watch import _rebuild_code, _write_build_config

    timer = _StageTimer("--timing" in args)
    target = Path(next((value for value in args if not value.startswith("-")), "."))
    force = "--force" in args
    no_cluster = "--no-cluster" in args
    changed: list[Path] | None = None
    if cmd == "update" and _option(args, "--changed"):
        changed = [Path(value) for value in str(_option(args, "--changed")).split(",")]
    include_semantic = cmd == "extract" and "--code-only" not in args
    output_value = _option(args, "--out", "--output")
    output = Path(output_value) if output_value else None
    explicit_excludes = _options(args, "--exclude")
    if "--no-gitignore" in args or explicit_excludes:
        config_root = output if output is not None else target
        _write_build_config(
            config_root / _GRAPHIFY_OUT,
            excludes=explicit_excludes or None,
            gitignore=False if "--no-gitignore" in args else None,
        )
    try:
        if not _rebuild_code(
            target, output_root=output, changed_paths=changed, force=force, no_cluster=no_cluster,
            block_on_lock=True,
            include_semantic=include_semantic,
            code_only="--code-only" in args,
            backend=_option(args, "--backend"),
            model=_option(args, "--model"),
            deep_mode=_option(args, "--mode") == "deep" or "--deep" in args,
            token_budget=int(_option(args, "--token-budget") or 60_000),
            max_concurrency=int(_option(args, "--max-concurrency") or 4),
            retain_rollback="--retain-rollback" in args,
            raise_on_error=True,
            _timer=timer,
        ):
            raise RuntimeError("graph rebuild failed")
    finally:
        timer.total()


def _save_result(args: list[str]) -> None:
    from graphify.ingest import save_query_result

    question = _option(args, "--question")
    answer = _option(args, "--answer")
    answer_file = _option(args, "--answer-file")
    if answer_file:
        answer = Path(answer_file).read_text(encoding="utf-8").strip()
    if not question or not answer:
        raise ValueError("save-result requires --question and --answer or --answer-file")
    nodes: list[str] = []
    if "--nodes" in args:
        index = args.index("--nodes") + 1
        while index < len(args) and not args[index].startswith("--"):
            nodes.append(args[index])
            index += 1
    output = save_query_result(
        question=question,
        answer=answer,
        memory_dir=Path(_option(args, "--memory-dir") or Path(_GRAPHIFY_OUT) / "memory"),
        query_type=_option(args, "--type") or "query",
        source_nodes=nodes or None,
        outcome=_option(args, "--outcome"),
        correction=_option(args, "--correction"),
    )
    print(f"Saved to {output}")


def _reflect(args: list[str]) -> None:
    from graphify.reflect import lessons_fresh, reflect

    memory_dir = Path(_option(args, "--memory-dir") or Path(_GRAPHIFY_OUT) / "memory")
    output = Path(_option(args, "--out") or Path(_GRAPHIFY_OUT) / "reflections" / "LESSONS.md")
    store_value = _option(args, "--store", "--graph")
    candidate = _store_arg(args)
    if store_value:
        _validate_store_or_exit(candidate)
        store = candidate
    else:
        # Preserve v8's automatic graph-aware reflection when the project's
        # default graph exists, while still allowing a graph-less cold start.
        store = candidate if candidate.is_dir() else None
    if "--if-stale" in args and lessons_fresh(output, memory_dir, store):
        print(f"Lessons already up to date -> {output}")
        return
    result, aggregate = reflect(
        memory_dir=memory_dir,
        out_path=output,
        graph_path=store,
        half_life_days=float(_option(args, "--half-life-days") or 30),
        min_corroboration=int(_option(args, "--min-corroboration") or 2),
    )
    print(f"Reflected {aggregate['total']} memories -> {result}")


def _tree(args: list[str]) -> None:
    from graphify.tree_html import write_tree_html

    store = _store_arg(args)
    output = Path(_option(args, "--output", "--out") or Path(_GRAPHIFY_OUT) / "GRAPH_TREE.html")
    result = write_tree_html(
        store,
        output,
        root=_option(args, "--root"),
        max_children=int(_option(args, "--max-children") or 200),
        project_label=_option(args, "--label"),
        top_k_edges=int(_option(args, "--top-k-edges") or 12),
    )
    print(result)


def _cache_check(args: list[str]) -> None:
    from graphify.cache import check_semantic_cache
    from graphify.helix.persistence import load_graph
    from graphify.llm import _extraction_system

    if not args or args[0].startswith("-"):
        raise ValueError("cache-check requires a newline-delimited file list")
    root = Path(_option(args, "--root") or ".")
    files = [line for line in Path(args[0]).read_text(encoding="utf-8").splitlines() if line.strip()]
    store = root / _GRAPHIFY_OUT / "graph.helix"
    cache: dict[str, dict] = {}
    if store.is_dir():
        loaded = load_graph(store)
        value = loaded.state.get("incremental", {}).get("extraction_cache", {})
        if isinstance(value, dict):
            cache = value
    mode = "deep" if "--deep" in args else _option(args, "--mode")
    prompt_file = _option(args, "--prompt-file")
    nodes, edges, hyperedges, uncached = check_semantic_cache(
        files,
        cache,
        root=root,
        mode=mode,
        prompt=None if prompt_file else _extraction_system(deep=mode == "deep"),
        prompt_file=prompt_file,
    )
    # These are transient extraction interchange files, never graph stores.
    out = root / _GRAPHIFY_OUT
    out.mkdir(parents=True, exist_ok=True)
    if nodes or edges or hyperedges:
        (out / ".graphify_cached.json").write_text(
            json.dumps({"nodes": nodes, "edges": edges, "hyperedges": hyperedges}),
            encoding="utf-8",
        )
    (out / ".graphify_uncached.txt").write_text("\n".join(uncached), encoding="utf-8")
    print(f"Cache: {len(files) - len(uncached)} hit, {len(uncached)} miss")


def _merge_chunks(args: list[str]) -> None:
    """Merge validated transient semantic DTO fragments.

    These files are untrusted extraction results, not graph stores.  They are
    validated before merging and the output is written atomically for the skill
    workflow to consume before constructing a native generation.
    """
    import glob

    from graphify.paths import write_json_atomic
    from graphify.semantic_cleanup import load_validated_semantic_fragment

    output_value = _option(args, "--out")
    if output_value is None:
        raise ValueError("merge-chunks requires --out <path>")
    output = Path(output_value)
    chunk_args: list[str] = []
    index = 0
    while index < len(args):
        if args[index] == "--out":
            index += 2
            continue
        if args[index].startswith("--out="):
            index += 1
            continue
        chunk_args.append(args[index])
        index += 1

    chunk_files: list[str] = []
    for value in chunk_args:
        expanded = glob.glob(value)
        chunk_files.extend(sorted(expanded) if expanded else [value])

    merged: dict[str, Any] = {
        "nodes": [], "edges": [], "hyperedges": [],
        "input_tokens": 0, "output_tokens": 0,
    }
    seen_ids: set[str] = set()
    valid_chunks = 0
    for raw_path in chunk_files:
        chunk, errors = load_validated_semantic_fragment(Path(raw_path))
        if errors:
            print(
                f"[graphify merge-chunks] warning: skipping invalid chunk "
                f"{raw_path}: {'; '.join(errors[:3])}",
                file=sys.stderr,
            )
            continue
        assert chunk is not None
        valid_chunks += 1
        for node in chunk.get("nodes", []):
            node_id = str(node.get("id"))
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                merged["nodes"].append(node)
        merged["edges"].extend(chunk.get("edges", []))
        merged["hyperedges"].extend(chunk.get("hyperedges", []))
        for token_key in ("input_tokens", "output_tokens"):
            value = chunk.get(token_key, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[token_key] += value
    if not valid_chunks:
        raise ValueError(
            f"no valid chunks to merge; refusing to write {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output, merged, ensure_ascii=False)
    summary = (
        f"{valid_chunks} chunks"
        if valid_chunks == len(chunk_files)
        else f"{valid_chunks} of {len(chunk_files)} chunks"
    )
    print(
        f"Merged {summary}: {len(merged['nodes'])} nodes, "
        f"{len(merged['edges'])} edges, {merged['input_tokens']:,} in / "
        f"{merged['output_tokens']:,} out tokens"
    )


def _rollback(args: list[str]) -> None:
    from graphify.helix.persistence import HelixEmbeddedStore
    from graphify.security import validate_store_path

    store_path = validate_store_path(_store_arg(args))
    with HelixEmbeddedStore(store_path, retain_rollback=True) as store:
        loaded = store.rollback()
    print(f"Rolled back {store_path} to generation {loaded.generation}.")


def _doctor(args: list[str]) -> None:
    from graphify.helix.persistence import HelixEmbeddedStore
    from graphify.security import validate_store_path

    store_path = validate_store_path(_store_arg(args))
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        result = store.verify() if "--deep" in args else store.verify_counts()
    mode = "deep" if "--deep" in args else "counts"
    print(f"Helix store OK ({mode}): {json.dumps(result, sort_keys=True)}")


def dispatch_command(cmd: str) -> None:
    args = sys.argv[2:]
    try:
        if cmd == "query":
            _query(args)
        elif cmd == "path":
            _path(args)
        elif cmd == "explain":
            _explain(args)
        elif cmd == "affected":
            from graphify.affected import DEFAULT_AFFECTED_RELATIONS, format_affected

            query = next((value for value in args if not value.startswith("-")), "")
            depth = int(_option(args, "--depth") or 2)
            relations = [
                value.split("=", 1)[1]
                for value in args
                if value.startswith("--relation=")
            ]
            for index, value in enumerate(args):
                if value == "--relation" and index + 1 < len(args):
                    relations.append(args[index + 1])
            loaded = _loaded(args)
            print(format_affected(
                loaded.graph, query,
                node_query=loaded.query,
                relations=relations or DEFAULT_AFFECTED_RELATIONS,
                depth=depth,
            ))
        elif cmd in {"god-nodes", "god_nodes"}:
            from graphify.analyze import god_nodes
            from graphify.security import sanitize_label

            loaded = _loaded(args)
            nodes = god_nodes(
                loaded.graph,
                top_n=int(_option(args, "--top") or 10),
            )
            if "--json" in args:
                print(json.dumps(nodes, indent=2))
            else:
                print("God nodes (most connected):")
                for rank, node in enumerate(nodes, 1):
                    print(
                        f"  {rank}. {sanitize_label(str(node['label']))} - "
                        f"{node['degree']} edges"
                    )
        elif cmd in {"extract", "update"}:
            _update_or_extract(cmd, args)
        elif cmd == "watch":
            from graphify.watch import watch

            target = Path(next((value for value in args if not value.startswith("-")), "."))
            watch(
                target,
                debounce=float(_option(args, "--debounce") or 3.0),
                retain_rollback="--retain-rollback" in args,
            )
        elif cmd == "check-update":
            from graphify.watch import check_update

            check_update(Path(args[0] if args else "."))
        elif cmd == "cluster-only":
            from graphify.operations import recluster, reanalyze

            store = _store_arg(args, default=Path(args[0]) / _GRAPHIFY_OUT / "graph.helix" if args and not args[0].startswith("-") else None)
            recluster(store)
            reanalyze(store)
            print(f"Reclustered {store}.")
        elif cmd == "label":
            from graphify.operations import relabel

            default = (
                Path(args[0]) / _GRAPHIFY_OUT / "graph.helix"
                if args and not args[0].startswith("-")
                else None
            )
            store = _store_arg(args, default=default)
            labels = relabel(
                store,
                backend=_option(args, "--backend"),
                model=_option(args, "--model"),
                missing_only="--missing-only" in args,
                max_concurrency=int(_option(args, "--max-concurrency") or 4),
                batch_size=int(_option(args, "--batch-size") or 100),
            )
            print(f"Labeled {len(labels)} communities in {store}.")
        elif cmd == "export":
            _export(args)
        elif cmd == "tree":
            _tree(args)
        elif cmd == "save-result":
            _save_result(args)
        elif cmd == "reflect":
            _reflect(args)
        elif cmd == "benchmark":
            from graphify.benchmark import print_benchmark, run_benchmark

            print_benchmark(run_benchmark(str(_store_arg(args))))
        elif cmd == "global":
            _global(args)
        elif cmd == "rollback":
            _rollback(args)
        elif cmd == "doctor":
            _doctor(args)
        elif cmd == "prs":
            from graphify.prs import cmd_prs

            cmd_prs(args)
        elif cmd == "clone":
            if not args:
                raise ValueError("clone requires a GitHub URL")
            clone_output = _option(args, "--out")
            _clone_repo(args[0], _option(args, "--branch"), Path(clone_output) if clone_output else None)
        elif cmd == "hook-check":
            _run_hook_guard("search")
        elif cmd == "hook-guard":
            _run_hook_guard(
                args[0] if args else "search",
                strict="--strict" in args[1:],
            )
        elif cmd == "hook":
            from graphify import hooks

            action = args[0] if args else "install"
            target = Path(args[1] if len(args) > 1 else ".")
            if action == "install":
                print(hooks.install(target))
            elif action == "uninstall":
                print(hooks.uninstall(target))
            elif action == "status":
                print(hooks.status(target))
            else:
                raise ValueError("hook action must be install, uninstall, or status")
        elif cmd == "cache-check":
            _cache_check(args)
        elif cmd == "merge-chunks":
            _merge_chunks(args)
        elif cmd == "add":
            from graphify.ingest import ingest

            if not args or args[0].startswith("-"):
                raise ValueError("add requires a URL")
            target = Path(_option(args, "--dir") or "raw")
            saved = ingest(
                args[0], target,
                author=_option(args, "--author"),
                contributor=_option(args, "--contributor"),
            )
            print(f"Saved to {saved}")
        elif cmd in {"diagnose", "merge-driver"}:
            raise ValueError(f"{cmd} was removed with the obsolete JSON graph format")
        else:
            # A bare path remains shorthand for extract.
            if Path(cmd).exists():
                _update_or_extract("extract", [cmd, *args])
            else:
                raise ValueError(f"unknown command: {cmd}")
    except (ValueError, FileNotFoundError, RuntimeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
