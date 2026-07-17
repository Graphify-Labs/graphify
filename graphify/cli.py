"""Helix-only command dispatch for every non-install Graphify command."""

from __future__ import annotations

import json
import os
import sys
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


def _run_hook_guard(kind: str) -> None:
    from graphify.paths import out_path, GRAPHIFY_OUT_NAME

    try:
        exists = out_path("graph.helix").is_dir()
    except Exception:
        exists = False
    if kind == "gemini":
        payload: dict[str, Any] = {"decision": "allow"}
        if exists:
            payload["additionalContext"] = _GEMINI_NUDGE_TEXT
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tool_input = data.get("tool_input", data)
        if not isinstance(tool_input, dict) or not exists:
            return
        if kind == "search":
            command = str(tool_input.get("command", ""))
            if any(token in command for token in ("grep", "ripgrep", "rg ", "find ", "fd ", "ack ", "ag ")):
                sys.stdout.write(_SEARCH_NUDGE)
        elif kind == "read":
            values = [
                str(tool_input.get("file_path") or ""),
                str(tool_input.get("pattern") or ""),
                str(tool_input.get("path") or ""),
            ]
            joined = " ".join(values).lower().replace("\\", "/")
            tails = [Path(value).suffix.lower() for value in values if value]
            if GRAPHIFY_OUT_NAME.lower() + "/" not in joined and any(ext in _HOOK_SOURCE_EXTS for ext in tails):
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
    budget = int(_option(args, "--budget") or 2000)
    mode = "dfs" if "--dfs" in args else "bfs"
    filters: list[str] = []
    for index, value in enumerate(args):
        if value == "--context" and index + 1 < len(args):
            filters.append(args[index + 1])
        elif value.startswith("--context="):
            filters.append(value.split("=", 1)[1])
    print(_query_graph_text(
        loaded.graph, question, mode=mode, depth=3, token_budget=budget,
        context_filters=filters,
    ))


def _path(args: list[str]) -> None:
    from graphify.helix.model import edge_attributes, node_attributes
    from graphify.serve import _pick_scored_endpoint, _query_terms, _score_nodes

    positional = [value for value in args if not value.startswith("-")]
    if len(positional) < 2:
        raise ValueError("path requires source and target")
    graph = _loaded(args).graph
    source_scores = _score_nodes(graph, _query_terms(positional[0]))
    target_scores = _score_nodes(graph, _query_terms(positional[1]))
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
    graph = loaded.graph
    matches = _find_node(graph, query)
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
    learning = loaded.state.get("learning", {})
    entries = learning.get("nodes", {}) if isinstance(learning, dict) else {}
    entry = entries.get(str(node_id)) if isinstance(entries, dict) else None
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
        print(global_add(source, tag))
        return
    if args[0] == "remove" and len(args) >= 2:
        print(f"Removed {global_remove(args[1])} nodes.")
        return
    if args[0] == "path":
        print(global_path())
        return
    raise ValueError("usage: graphify global add <project|graph.helix> [--as TAG] | remove TAG | list | path")


def _update_or_extract(cmd: str, args: list[str]) -> None:
    from graphify.watch import _rebuild_code

    target = Path(next((value for value in args if not value.startswith("-")), "."))
    force = "--force" in args
    no_cluster = "--no-cluster" in args
    changed: list[Path] | None = None
    if cmd == "update" and _option(args, "--changed"):
        changed = [Path(value) for value in str(_option(args, "--changed")).split(",")]
    include_semantic = cmd == "extract" and "--code-only" not in args
    output_value = _option(args, "--out")
    output = Path(output_value) if output_value else None
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
        raise_on_error=True,
    ):
        raise RuntimeError("graph rebuild failed")


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
    store = _store_arg(args) if store_value else None
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
    nodes, edges, hyperedges, uncached = check_semantic_cache(
        files,
        cache,
        root=root,
        mode="deep" if "--deep" in args else _option(args, "--mode"),
        prompt_file=_option(args, "--prompt-file"),
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
            print(format_affected(
                _loaded(args).graph, query,
                relations=relations or DEFAULT_AFFECTED_RELATIONS,
                depth=depth,
            ))
        elif cmd in {"extract", "update"}:
            _update_or_extract(cmd, args)
        elif cmd == "watch":
            from graphify.watch import watch

            target = Path(next((value for value in args if not value.startswith("-")), "."))
            watch(target, debounce=float(_option(args, "--debounce") or 3.0))
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
            _run_hook_guard(args[0] if args else "search")
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
