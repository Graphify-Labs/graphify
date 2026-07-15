"""graphify command dispatch — every non-install subcommand.

Extracted verbatim from __main__.main(); __main__ now calls dispatch_command(cmd)
after the install/platform dispatch. Kept out of __main__ to shrink the CLI entry
module. The path-redirect (`graphify <path>` -> extract) re-enters via a lazy
import of main to avoid a cli<->__main__ import cycle.
"""
from __future__ import annotations
import json
import os
import sys
from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT
from pathlib import Path


_SEARCH_NUDGE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            'MANDATORY: graphify-out/graph.json exists. You MUST run '
            '`graphify query "<question>"` before grepping raw files. Only grep '
            'after graphify has oriented you, or to modify/debug specific lines.'
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_READ_NUDGE = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            'MANDATORY: graphify-out/graph.json exists. You MUST run graphify '
            'before reading source files. Use: `graphify query "<question>"` '
            '(scoped subgraph), `graphify explain "<concept>"`, or '
            '`graphify path "<A>" "<B>"`. Only read raw files after graphify has '
            'oriented you, or to modify/debug specific lines. This rule applies to '
            'subagents too — include it in every subagent prompt involving code '
            'exploration.'
        ),
    }
}, ensure_ascii=False, separators=(",", ":")) + "\n"
_HOOK_SOURCE_EXTS = (
    '.py', '.js', '.ts', '.tsx', '.jsx', '.astro', '.vue', '.svelte', '.go',
    '.rs', '.java', '.rb', '.c', '.h', '.cpp', '.hpp', '.cc', '.cs', '.kt',
    '.swift', '.php', '.scala', '.lua', '.sh', '.md', '.rst', '.txt', '.mdx',
)
_GEMINI_NUDGE_TEXT = (
    'graphify: knowledge graph at graphify-out/. For focused questions, run '
    '`graphify query "<question>"` (scoped subgraph, usually much smaller than '
    'GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only '
    'for broad architecture context.'
)


def _default_graph_path() -> str:
    return str(Path(_GRAPHIFY_OUT) / "graph.json")


def _stamped_manifest_files(
    files_by_type: dict[str, list[str]],
    sem_result: dict,
    root: Path,
) -> dict[str, list[str]]:
    """Manifest-safe files dict: only stamp semantic files that actually
    produced output (cache hit or fresh extraction). Files whose chunk failed
    have no source_file entry in sem_result — leaving their semantic_hash
    empty so detect_incremental re-queues them (#933).

    Both sides of the membership test are resolved against the scan ``root``
    before comparing (#1897): node/edge ``source_file`` values are
    root-relative on a fresh extraction while ``files_by_type`` entries are
    absolute (from detect()), so a raw string comparison never matched and
    every freshly-extracted semantic doc was dropped from the manifest.
    Mirrors the #1890 path normalization in graphify.llm.
    """
    root = Path(root)

    def _resolve(value: str) -> Path:
        p = Path(value)
        if not p.is_absolute():
            p = root / p
        try:
            return p.resolve()
        except (OSError, RuntimeError):
            return p

    sem_extracted: set[Path] = set()
    for coll in ("nodes", "edges"):
        for item in sem_result.get(coll, []):
            sf = item.get("source_file", "")
            if sf:
                sem_extracted.add(_resolve(sf))
    sem_types = {"document", "paper", "image"}
    return {
        ftype: [
            f for f in flist
            if ftype not in sem_types or _resolve(f) in sem_extracted
        ]
        for ftype, flist in files_by_type.items()
    }
class _StageTimer:
    """Print per-stage wall-clock timings to stderr when --timing is set (#1490).

    Monotonic (perf_counter), diagnostic-only: emits ``[graphify timing] <stage>:
    N.Ns`` after each stage and a final total. Off by default, so normal output is
    byte-identical and machine-read stdout is untouched.
    """

    def __init__(self, enabled: bool) -> None:
        import time as _time
        self._now = _time.perf_counter
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
def _enforce_graph_size_cap_or_exit(gp: Path) -> None:
    """Reject oversized graph files before parsing (CLI exit-on-fail flavor).

    Delegates to ``graphify.security.check_graph_file_size_cap`` and turns the
    raised ``ValueError`` into a CLI-style ``error: ...`` message + exit 1.
    Use this from ``__main__.py`` subcommands that already use the ``print +
    sys.exit(1)`` idiom. Library/MCP/loader callers (``serve._load_graph``,
    ``build``, ``benchmark``, ``tree_html``, ``callflow_html``, ``prs``,
    ``global_graph``, ``watch``, ``export``) call the security helper directly
    and let the ``ValueError`` propagate.
    """
    from graphify.security import check_graph_file_size_cap
    try:
        check_graph_file_size_cap(gp)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
def _run_hook_guard(kind: str) -> None:
    """Shell-agnostic PreToolUse guard (#522).

    Reads the tool-call JSON from stdin and, when a knowledge graph exists in the
    current output dir, prints a nudge (`additionalContext`) telling the agent to
    use graphify instead of grepping/reading raw files. Replaces the old inline
    bash hooks that failed to parse on Windows. Always fails open: any error, or a
    non-matching tool call, prints nothing and the caller exits 0, so a legitimate
    tool call is never blocked. Detection mirrors the previous hooks exactly.
    """
    from graphify.paths import out_path, GRAPHIFY_OUT_NAME
    # Gemini's BeforeTool hook takes no stdin and must ALWAYS return a decision so
    # the tool is never blocked; the graph nudge is appended only when a graph
    # exists. Handled before the stdin read below (which the search/read guards need).
    if kind == "gemini":
        payload = {"decision": "allow"}
        try:
            if out_path("graph.json").is_file():
                payload["additionalContext"] = _GEMINI_NUDGE_TEXT
        except Exception:
            pass
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    try:
        d = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if not isinstance(d, dict):
        return
    t = d.get("tool_input", d)
    if not isinstance(t, dict):
        return
    try:
        if kind == "search":
            cmd_str = str(t.get("command", "") or "")
            # Same set the old `case` matched: *grep*, *ripgrep*, and rg/find/fd/
            # ack/ag as a token (name followed by a space).
            if any(tok in cmd_str for tok in ("grep", "ripgrep", "rg ", "find ", "fd ", "ack ", "ag ")) \
                    and out_path("graph.json").is_file():
                sys.stdout.write(_SEARCH_NUDGE)
        elif kind == "read":
            vals = [str(t.get("file_path") or ""), str(t.get("pattern") or ""), str(t.get("path") or "")]
            j = " ".join(vals).lower().replace("\\", "/")
            tails = [
                "." + seg.rsplit(".", 1)[-1]
                for v in vals if v
                for seg in [v.lower().replace("\\", "/").rsplit("/", 1)[-1]]
                if "." in seg
            ]
            under_out = "graphify-out/" in j or (GRAPHIFY_OUT_NAME.lower() + "/") in j
            if not under_out and any(tl in _HOOK_SOURCE_EXTS for tl in tails) \
                    and out_path("graph.json").is_file():
                sys.stdout.write(_READ_NUDGE)
    except Exception:
        pass
def _clone_repo(
    url: str, branch: str | None = None, out_dir: Path | None = None
) -> Path:
    """Clone a GitHub repo to a local cache dir and return the path.

    Clones into ~/.graphify/repos/<owner>/<repo> by default so repeated
    runs on the same URL reuse the existing clone (git pull instead of clone).
    """
    import subprocess as _sp
    import re as _re

    # Normalise URL — strip trailing .git if present
    url = url.rstrip("/")
    if not url.endswith(".git"):
        git_url = url + ".git"
    else:
        git_url = url
        url = url[:-4]

    # Extract owner/repo from URL
    m = _re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        print(f"error: not a recognised GitHub URL: {url}", file=sys.stderr)
        sys.exit(1)
    owner, repo = m.group(1), m.group(2)

    if out_dir:
        dest = out_dir
    else:
        dest = Path.home() / ".graphify" / "repos" / owner / repo

    if branch and branch.startswith("-"):
        print(f"error: invalid branch name: {branch!r}", file=sys.stderr)
        sys.exit(1)

    if dest.exists():
        print(f"Repo already cloned at {dest} - pulling latest...", flush=True)
        cmd = ["git", "-C", str(dest), "pull"]
        if branch:
            cmd += ["origin", "--", branch]
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"warning: git pull failed:\n{result.stderr}", file=sys.stderr)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning {url} -> {dest} ...", flush=True)
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += ["--", git_url, str(dest)]
        result = _sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"error: git clone failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

    print(f"Ready at: {dest}", flush=True)
    return dest


def _reenter_main() -> None:
    from graphify.__main__ import main
    main()


def dispatch_command(cmd: str) -> None:
    if cmd == "provider":
        from graphify.llm import _custom_providers_path, BACKENDS
        import json as _json
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        global_path = _custom_providers_path(global_=True)

        if subcmd == "list":
            global_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if global_path.is_file():
                try:
                    existing = _json.loads(global_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if not existing:
                print("No custom providers registered.")
            else:
                for name in existing:
                    print(f"  {name}  ({existing[name].get('base_url', '')})")

        elif subcmd == "show":
            name = sys.argv[3] if len(sys.argv) > 3 else ""
            if not name:
                print("Usage: graphify provider show <name>", file=sys.stderr)
                sys.exit(1)
            existing = {}
            if global_path.is_file():
                try:
                    existing = _json.loads(global_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if name not in existing:
                print(f"Provider '{name}' not found.", file=sys.stderr)
                sys.exit(1)
            print(_json.dumps({name: existing[name]}, indent=2))

        elif subcmd == "add":
            args = sys.argv[3:]
            name = args[0] if args and not args[0].startswith("-") else ""
            if not name:
                print("Usage: graphify provider add <name> --base-url URL --default-model MODEL --env-key KEY", file=sys.stderr)
                sys.exit(1)
            if name in BACKENDS:
                print(f"Error: '{name}' is a built-in provider and cannot be overridden.", file=sys.stderr)
                sys.exit(1)
            base_url = ""
            default_model = ""
            env_key = ""
            pricing_input = 0.0
            pricing_output = 0.0
            i = 1
            while i < len(args):
                a = args[i]
                if a == "--base-url" and i + 1 < len(args):
                    base_url = args[i + 1]; i += 2
                elif a.startswith("--base-url="):
                    base_url = a.split("=", 1)[1]; i += 1
                elif a == "--default-model" and i + 1 < len(args):
                    default_model = args[i + 1]; i += 2
                elif a.startswith("--default-model="):
                    default_model = a.split("=", 1)[1]; i += 1
                elif a == "--env-key" and i + 1 < len(args):
                    env_key = args[i + 1]; i += 2
                elif a.startswith("--env-key="):
                    env_key = a.split("=", 1)[1]; i += 1
                elif a == "--pricing-input" and i + 1 < len(args):
                    pricing_input = float(args[i + 1]); i += 2
                elif a == "--pricing-output" and i + 1 < len(args):
                    pricing_output = float(args[i + 1]); i += 2
                else:
                    i += 1
            if not base_url or not default_model or not env_key:
                print("Error: --base-url, --default-model, and --env-key are required.", file=sys.stderr)
                sys.exit(1)
            from graphify.llm import provider_base_url_ok
            if not provider_base_url_ok(base_url, name):
                print(f"Error: refusing to add provider with unsafe base_url {base_url!r}.", file=sys.stderr)
                sys.exit(1)
            global_path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if global_path.is_file():
                try:
                    existing = _json.loads(global_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing[name] = {
                "base_url": base_url,
                "default_model": default_model,
                "env_key": env_key,
                "pricing": {"input": pricing_input, "output": pricing_output},
                "temperature": 0,
            }
            global_path.write_text(_json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            print(f"Provider '{name}' added. Use with: graphify extract . --backend {name}")

        elif subcmd == "remove":
            name = sys.argv[3] if len(sys.argv) > 3 else ""
            if not name:
                print("Usage: graphify provider remove <name>", file=sys.stderr)
                sys.exit(1)
            existing = {}
            if global_path.is_file():
                try:
                    existing = _json.loads(global_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if name not in existing:
                print(f"Provider '{name}' not found.", file=sys.stderr)
                sys.exit(1)
            del existing[name]
            global_path.write_text(_json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            print(f"Provider '{name}' removed.")

        else:
            print("Usage: graphify provider [add|list|show|remove]", file=sys.stderr)
            if subcmd:
                sys.exit(1)
    elif cmd == "prs":
        from graphify.prs import cmd_prs
        cmd_prs(sys.argv[2:])
    elif cmd == "hook":
        from graphify.hooks import (
            install as hook_install,
            uninstall as hook_uninstall,
            status as hook_status,
        )

        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            print(hook_install(Path(".")))
        elif subcmd == "uninstall":
            print(hook_uninstall(Path(".")))
        elif subcmd == "status":
            print(hook_status(Path(".")))
        else:
            print("Usage: graphify hook [install|uninstall|status]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: graphify query \"<question>\" [--dfs] [--context C] [--budget N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.serve import _query_graph_text
        from graphify.security import sanitize_label
        from networkx.readwrite import json_graph
        from graphify import querylog

        question = sys.argv[2]
        use_dfs = "--dfs" in sys.argv
        budget = 2000
        graph_path = _default_graph_path()
        context_filters: list[str] = []
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--budget" and i + 1 < len(args):
                try:
                    budget = int(args[i + 1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--budget="):
                try:
                    budget = int(args[i].split("=", 1)[1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--context" and i + 1 < len(args):
                context_filters.append(args[i + 1])
                i += 2
            elif args[i].startswith("--context="):
                context_filters.append(args[i].split("=", 1)[1])
                i += 1
            elif args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
                i += 2
            else:
                i += 1
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print(f"error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        try:
            import json as _json
            import networkx as _nx

            _raw = _json.loads(gp.read_text(encoding="utf-8"))
            if "links" not in _raw and "edges" in _raw:
                _raw = dict(_raw, links=_raw["edges"])
            try:
                G = json_graph.node_link_graph(_raw, edges="links")
            except TypeError:
                G = json_graph.node_link_graph(_raw)
            try:
                from graphify.build import graph_has_legacy_ids as _legacy
                if _legacy(_raw.get("nodes", [])):
                    print(
                        "[graphify] note: this graph uses the pre-#1504 node-ID scheme; "
                        "rebuild with `graphify extract --force` to get path-qualified IDs "
                        "(fixes same-name-file collisions).",
                        file=sys.stderr,
                    )
            except Exception:
                pass
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        import time as _time
        _t0 = _time.perf_counter()
        _mode = "dfs" if use_dfs else "bfs"
        _result = _query_graph_text(
            G,
            question,
            mode=_mode,
            depth=2,
            token_budget=budget,
            context_filters=context_filters,
        )
        querylog.log_query(
            kind="query",
            question=question,
            corpus=str(gp),
            result=_result,
            mode=_mode,
            depth=2,
            token_budget=budget,
            duration_ms=(_time.perf_counter() - _t0) * 1000,
        )
        print(_result)
    elif cmd == "affected":
        if len(sys.argv) < 3:
            print("Usage: graphify affected \"<node-or-label>\" [--relation R] [--depth N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.affected import DEFAULT_AFFECTED_RELATIONS, format_affected, load_graph
        query = sys.argv[2]
        graph_path = _default_graph_path()
        depth = 2
        relations: list[str] = []
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
                i += 2
            elif args[i].startswith("--graph="):
                graph_path = args[i].split("=", 1)[1]
                i += 1
            elif args[i] == "--depth" and i + 1 < len(args):
                try:
                    depth = int(args[i + 1])
                except ValueError:
                    print("error: --depth must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--depth="):
                try:
                    depth = int(args[i].split("=", 1)[1])
                except ValueError:
                    print("error: --depth must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--relation" and i + 1 < len(args):
                relations.append(args[i + 1])
                i += 2
            elif args[i].startswith("--relation="):
                relations.append(args[i].split("=", 1)[1])
                i += 1
            else:
                i += 1
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print("error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        try:
            graph = load_graph(gp)
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            format_affected(
                graph,
                query,
                relations=relations or DEFAULT_AFFECTED_RELATIONS,
                depth=depth,
            )
        )
    elif cmd == "save-result":
        # graphify save-result --question Q --answer A [--type T] [--nodes N1 N2 ...]
        #                      [--outcome useful|dead_end|corrected] [--correction TEXT]
        import argparse as _ap

        p = _ap.ArgumentParser(prog="graphify save-result")
        p.add_argument("--question", required=True)
        p.add_argument("--answer", default=None)
        p.add_argument("--answer-file", dest="answer_file", default=None)
        p.add_argument("--type", dest="query_type", default="query")
        p.add_argument("--nodes", nargs="*", default=[])
        p.add_argument("--outcome", choices=("useful", "dead_end", "corrected"), default=None)
        p.add_argument("--correction", default=None)
        p.add_argument("--memory-dir", default=str(Path(_GRAPHIFY_OUT) / "memory"))
        opts = p.parse_args(sys.argv[2:])
        if opts.answer_file:
            opts.answer = Path(opts.answer_file).read_text(encoding="utf-8").strip()
        elif not opts.answer:
            p.error("--answer or --answer-file is required")
        from graphify.ingest import save_query_result as _sqr

        out = _sqr(
            question=opts.question,
            answer=opts.answer,
            memory_dir=Path(opts.memory_dir),
            query_type=opts.query_type,
            source_nodes=opts.nodes or None,
            outcome=opts.outcome,
            correction=opts.correction,
        )
        print(f"Saved to {out}")
    elif cmd == "reflect":
        import argparse as _ap

        p = _ap.ArgumentParser(prog="graphify reflect")
        p.add_argument("--memory-dir", default=str(Path(_GRAPHIFY_OUT) / "memory"))
        p.add_argument(
            "--out",
            default=str(Path(_GRAPHIFY_OUT) / "reflections" / "LESSONS.md"),
        )
        p.add_argument("--graph", default=None)
        p.add_argument("--analysis", default=None)
        p.add_argument("--labels", default=None)
        p.add_argument("--half-life-days", type=float, default=30.0,
                       help="signal weight halves every N days (default 30)")
        p.add_argument("--min-corroboration", type=int, default=2,
                       help="distinct useful results to promote a node to preferred (default 2)")
        p.add_argument("--if-stale", action="store_true",
                       help="skip when LESSONS.md is already newer than every input "
                            "(e.g. the git hook just refreshed it)")
        opts = p.parse_args(sys.argv[2:])
        from graphify.reflect import reflect as _reflect, lessons_fresh as _lessons_fresh

        graph_arg = opts.graph
        if graph_arg is None:
            default_graph = Path(_GRAPHIFY_OUT) / "graph.json"
            if default_graph.exists():
                graph_arg = str(default_graph)

        _gp = Path(graph_arg) if graph_arg else None
        _analysis_path = None
        _labels_path = None
        if _gp is not None:
            _analysis_path = Path(opts.analysis) if opts.analysis else (
                _gp.parent / ".graphify_analysis.json")
            _labels_path = Path(opts.labels) if opts.labels else (
                _gp.parent / ".graphify_labels.json")

        if opts.if_stale and _lessons_fresh(
            Path(opts.out), Path(opts.memory_dir), _gp, _analysis_path, _labels_path
        ):
            print(f"Lessons already up to date -> {opts.out} (skipped; omit --if-stale to force)")
        else:
            out_path, agg = _reflect(
                memory_dir=Path(opts.memory_dir),
                out_path=Path(opts.out),
                graph_path=_gp,
                analysis_path=_analysis_path,
                labels_path=_labels_path,
                half_life_days=opts.half_life_days,
                min_corroboration=opts.min_corroboration,
            )
            c = agg["counts"]
            print(
                f"Reflected {agg['total']} memories "
                f"({c['useful']} useful, {c['dead_end']} dead ends, "
                f"{c['corrected']} corrected) -> {out_path}"
            )
    elif cmd == "path":
        if len(sys.argv) < 4:
            print(
                'Usage: graphify path "<source>" "<target>" [--graph path]',
                file=sys.stderr,
            )
            sys.exit(1)
        from graphify.serve import _pick_scored_endpoint, _score_nodes
        from networkx.readwrite import json_graph
        import networkx as _nx

        source_label = sys.argv[2]
        target_label = sys.argv[3]
        graph_path = _default_graph_path()
        args = sys.argv[4:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        # Force directed so the renderer can recover stored caller→callee direction.
        _raw = {**_raw, "directed": True}
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        src_scored = _score_nodes(G, [t.lower() for t in source_label.split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in target_label.split()])
        if not src_scored:
            print(f"No node matching '{source_label}' found.", file=sys.stderr)
            sys.exit(1)
        if not tgt_scored:
            print(f"No node matching '{target_label}' found.", file=sys.stderr)
            sys.exit(1)
        src_nid = _pick_scored_endpoint(G, src_scored, source_label)
        tgt_nid = _pick_scored_endpoint(G, tgt_scored, target_label)
        # Ambiguity guard: when both queries resolve to the same node, the
        # shortest path is trivially zero hops, which is almost never what the
        # caller wanted (see bug #828).
        if src_nid == tgt_nid:
            print(
                f"'{source_label}' and '{target_label}' both resolved to the same "
                f"node '{src_nid}'. Use a more specific label or the exact node ID.",
                file=sys.stderr,
            )
            sys.exit(1)
        for _name, _scored, _nid in (
            ("source", src_scored, src_nid),
            ("target", tgt_scored, tgt_nid),
        ):
            # A close runner-up only made the resolution ambiguous when the raw
            # score head is what got picked; a full-token override was chosen on
            # token coverage, not score, so the head's margin is irrelevant.
            if len(_scored) >= 2 and _nid == _scored[0][1]:
                _top, _runner = _scored[0][0], _scored[1][0]
                if _top > 0 and (_top - _runner) / _top < 0.10:
                    print(
                        f"warning: {_name} match was ambiguous "
                        f"(top score {_top:g}, runner-up {_runner:g})",
                        file=sys.stderr,
                    )
        try:
            path_nodes = _nx.shortest_path(G.to_undirected(as_view=True), src_nid, tgt_nid)
        except (_nx.NetworkXNoPath, _nx.NodeNotFound):
            print(f"No path found between '{source_label}' and '{target_label}'.")
            sys.exit(0)
        hops = len(path_nodes) - 1
        segments = []
        from graphify.build import edge_data
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            # Check which direction the stored edge points.
            if G.has_edge(u, v):
                edata = edge_data(G, u, v)
                forward = True
            else:
                edata = edge_data(G, v, u)
                forward = False
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            if forward:
                segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
            else:
                segments.append(f"<--{rel}{conf_str}-- {G.nodes[v].get('label', v)}")
        print(f"Shortest path ({hops} hops):\n  " + " ".join(segments))
        from graphify import querylog
        querylog.log_query(
            kind="path",
            question=f"{sys.argv[2]} -> {sys.argv[3]}",
            corpus=str(gp),
            nodes_returned=hops,
        )

    elif cmd == "explain":
        if len(sys.argv) < 3:
            print('Usage: graphify explain "<node>" [--graph path]', file=sys.stderr)
            sys.exit(1)
        from graphify.serve import _find_node
        from networkx.readwrite import json_graph

        label = sys.argv[2]
        graph_path = _default_graph_path()
        args = sys.argv[3:]
        for i, a in enumerate(args):
            if a == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(gp)
        _raw = json.loads(gp.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        # Force directed so the renderer can recover stored caller→callee direction.
        _raw = {**_raw, "directed": True}
        try:
            G = json_graph.node_link_graph(_raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(_raw)
        matches = _find_node(G, label)
        if not matches:
            print(f"No node matching '{label}' found.")
            sys.exit(0)
        nid = matches[0]
        d = G.nodes[nid]
        print(f"Node: {d.get('label', nid)}")
        print(f"  ID:        {nid}")
        print(
            f"  Source:    {d.get('source_file', '')} {d.get('source_location', '')}".rstrip()
        )
        print(f"  Type:      {d.get('file_type', '')}")
        print(f"  Community: {d.get('community_name') or d.get('community', '')}")
        # Work-memory overlay: a derived experiential hint from `graphify reflect`,
        # merged in display-only from the .graphify_learning.json sidecar next to
        # graph.json. No line when the node has no overlay entry.
        try:
            from graphify.reflect import load_learning_overlay as _llo
            from graphify.security import sanitize_label as _sl
            _overlay = _llo(gp)
            _entry = _overlay.get(str(nid))
            if _entry:
                _status = _sl(str(_entry.get("status", "")))
                if _status == "contested":
                    _line = (f"  Lesson: contested (useful {_entry.get('uses', 0)} / "
                             f"dead-end {_entry.get('neg', 0)})")
                elif _status == "preferred":
                    _line = (f"  Lesson: preferred source (start here) — "
                             f"{_entry.get('uses', 0)} useful, score={_entry.get('score', 0)}")
                else:
                    _line = (f"  Lesson: {_status or 'tentative'} — "
                             f"{_entry.get('uses', 0)} useful, score={_entry.get('score', 0)}")
                if _entry.get("stale"):
                    _line += " [code changed since — re-verify]"
                print(_line)
        except Exception:
            pass
        print(f"  Degree:    {G.degree(nid)}")
        from graphify.build import edge_data
        connections: list[tuple[str, str, dict]] = []  # (direction, neighbor_id, edge_data)
        for nb in G.successors(nid):
            connections.append(("out", nb, edge_data(G, nid, nb)))
        for nb in G.predecessors(nid):
            connections.append(("in", nb, edge_data(G, nb, nid)))
        if connections:
            print(f"\nConnections ({len(connections)}):")
            connections.sort(key=lambda c: G.degree(c[1]), reverse=True)
            for direction, nb, edata in connections[:20]:
                rel = edata.get("relation", "")
                conf = edata.get("confidence", "")
                arrow = "-->" if direction == "out" else "<--"
                print(f"  {arrow} {G.nodes[nb].get('label', nb)} [{rel}] [{conf}]")
            if len(connections) > 20:
                print(f"  ... and {len(connections) - 20} more")
        from graphify import querylog
        querylog.log_query(
            kind="explain",
            question=sys.argv[2],
            corpus=str(gp),
            nodes_returned=len(connections),
        )

    elif cmd == "diagnose":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd != "multigraph":
            print(
                "Usage: graphify diagnose multigraph "
                "[--graph path] [--json] [--max-examples N] "
                "[--directed] [--undirected] [--extract-path path]",
                file=sys.stderr,
            )
            sys.exit(1)

        graph_path = Path(_default_graph_path())
        max_examples = 5
        directed: bool | None = None
        direction_flag: str | None = None
        json_output = False
        extract_path: Path | None = None

        i = 3
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == "--graph":
                i += 1
                if i >= len(sys.argv):
                    print("error: --graph requires a path", file=sys.stderr)
                    sys.exit(1)
                graph_path = Path(sys.argv[i])
            elif arg == "--json":
                json_output = True
            elif arg == "--max-examples":
                i += 1
                if i >= len(sys.argv):
                    print("error: --max-examples requires an integer", file=sys.stderr)
                    sys.exit(1)
                try:
                    max_examples = int(sys.argv[i])
                except ValueError:
                    print("error: --max-examples requires an integer", file=sys.stderr)
                    sys.exit(1)
                if max_examples < 0:
                    print("error: --max-examples must be >= 0", file=sys.stderr)
                    sys.exit(1)
            elif arg == "--directed":
                if direction_flag == "undirected":
                    print(
                        "error: --directed and --undirected are mutually exclusive",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                direction_flag = "directed"
                directed = True
            elif arg == "--undirected":
                if direction_flag == "directed":
                    print(
                        "error: --directed and --undirected are mutually exclusive",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                direction_flag = "undirected"
                directed = False
            elif arg == "--extract-path":
                i += 1
                if i >= len(sys.argv):
                    print("error: --extract-path requires a path", file=sys.stderr)
                    sys.exit(1)
                extract_path = Path(sys.argv[i])
            else:
                print(f"error: unknown diagnose option {arg}", file=sys.stderr)
                sys.exit(1)
            i += 1

        from graphify.diagnostics import (
            diagnose_file,
            format_diagnostic_json,
            format_diagnostic_report,
        )

        try:
            summary = diagnose_file(
                graph_path,
                directed=directed,
                root=Path(".").resolve(),
                max_examples=max_examples,
                extract_path=extract_path,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

        if json_output:
            print(json.dumps(format_diagnostic_json(summary), indent=2))
        else:
            print(format_diagnostic_report(summary))

    elif cmd == "add":
        if len(sys.argv) < 3:
            print(
                "Usage: graphify add <url> [--author Name] [--contributor Name] [--dir ./raw]",
                file=sys.stderr,
            )
            sys.exit(1)
        from graphify.ingest import ingest as _ingest

        url = sys.argv[2]
        author: str | None = None
        contributor: str | None = None
        target_dir = Path("raw")
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--author" and i + 1 < len(args):
                author = args[i + 1]
                i += 2
            elif args[i] == "--contributor" and i + 1 < len(args):
                contributor = args[i + 1]
                i += 2
            elif args[i] == "--dir" and i + 1 < len(args):
                target_dir = Path(args[i + 1])
                i += 2
            else:
                i += 1
        try:
            saved = _ingest(url, target_dir, author=author, contributor=contributor)
            print(f"Saved to {saved}")
            print("Run /graphify --update in your AI assistant to update the graph.")
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "watch":
        watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch import watch as _watch

        try:
            _watch(watch_path)
        except ImportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif cmd in ("cluster-only", "label"):
        # `label` is `cluster-only` that always (re)generates community names with
        # the configured backend, even when a .graphify_labels.json already exists.
        force_relabel = cmd == "label"
        # Mirror the tree/export arg-parsing pattern: walk argv so flags and
        # the optional positional path can appear in any order (#724).
        no_viz = "--no-viz" in sys.argv
        no_label = "--no-label" in sys.argv
        missing_only = "--missing-only" in sys.argv
        co_timing = "--timing" in sys.argv
        _backend_arg = next((a for a in sys.argv if a.startswith("--backend=")), None)
        label_backend = _backend_arg.split("=", 1)[1] if _backend_arg else None
        _model_arg = next((a for a in sys.argv if a.startswith("--model=")), None)
        label_model = _model_arg.split("=", 1)[1] if _model_arg else None
        _min_cs_arg = next((a for a in sys.argv if a.startswith("--min-community-size=")), None)
        min_community_size = int(_min_cs_arg.split("=")[1]) if _min_cs_arg else 3
        args = sys.argv[2:]
        watch_path: Path | None = None
        graph_override: Path | None = None
        co_resolution: float = 1.0
        co_exclude_hubs: float | None = None
        label_max_concurrency: int = 4
        label_batch_size: int = 100
        i_arg = 0
        while i_arg < len(args):
            a = args[i_arg]
            if a == "--graph" and i_arg + 1 < len(args):
                graph_override = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--backend" and i_arg + 1 < len(args):
                label_backend = args[i_arg + 1]; i_arg += 2
            elif a.startswith("--backend="):
                label_backend = a.split("=", 1)[1]; i_arg += 1
            elif a == "--model" and i_arg + 1 < len(args):
                label_model = args[i_arg + 1]; i_arg += 2
            elif a.startswith("--model="):
                label_model = a.split("=", 1)[1]; i_arg += 1
            elif a == "--resolution" and i_arg + 1 < len(args):
                co_resolution = float(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--resolution="):
                co_resolution = float(a.split("=", 1)[1]); i_arg += 1
            elif a == "--exclude-hubs" and i_arg + 1 < len(args):
                co_exclude_hubs = float(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--exclude-hubs="):
                co_exclude_hubs = float(a.split("=", 1)[1]); i_arg += 1
            elif a == "--max-concurrency" and i_arg + 1 < len(args):
                label_max_concurrency = int(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--max-concurrency="):
                label_max_concurrency = int(a.split("=", 1)[1]); i_arg += 1
            elif a == "--batch-size" and i_arg + 1 < len(args):
                label_batch_size = int(args[i_arg + 1]); i_arg += 2
            elif a.startswith("--batch-size="):
                label_batch_size = int(a.split("=", 1)[1]); i_arg += 1
            elif a in ("--no-viz", "--missing-only") or a.startswith("--min-community-size="):
                i_arg += 1
            elif a.startswith("--"):
                i_arg += 1
            elif watch_path is None:
                watch_path = Path(a); i_arg += 1
            else:
                i_arg += 1
        if watch_path is None:
            watch_path = Path(".")
        graph_json = graph_override if graph_override is not None else watch_path / _GRAPHIFY_OUT / "graph.json"
        if not graph_json.exists():
            print(
                f"error: no graph found at {graph_json} — run /graphify first",
                file=sys.stderr,
            )
            sys.exit(1)
        from networkx.readwrite import json_graph as _jg
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all, remap_communities_to_previous
        from graphify.analyze import (
            god_nodes,
            surprising_connections,
            suggest_questions,
        )
        from graphify.report import generate
        from graphify.export import to_json, to_html

        stages = _StageTimer(co_timing)
        print("Loading existing graph...")
        # Solution 3 (#1019): don't hard-exit on an oversized graph.json here.
        # Core outputs (graph.json + GRAPH_REPORT.md) still get written; the
        # graph.html render below falls back to the community-aggregation view
        # (node_limit=5000) when over the cap.
        from graphify.security import check_graph_file_size_cap as _check_cap
        _over_cap = False
        try:
            _check_cap(graph_json)
        except ValueError:
            _over_cap = True
            try:
                _over_cap_bytes = graph_json.stat().st_size
            except OSError:
                _over_cap_bytes = -1
            print(
                f"warning: graph.json exceeds cap ({_over_cap_bytes} bytes); "
                f"falling back to community-aggregation view (node_limit=5000)",
                file=sys.stderr,
            )
        _raw = json.loads(graph_json.read_text(encoding="utf-8"))
        _directed = bool(_raw.get("directed", False))
        G = build_from_json(_raw, directed=_directed)
        print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        stages.mark("load")
        print("Re-clustering...")
        communities = cluster(G, resolution=co_resolution, exclude_hubs_percentile=co_exclude_hubs)
        # Mirror the watch/update path (#822): map new cids to prior ones by
        # node-overlap so the existing .graphify_labels.json keeps attaching
        # to the same conceptual community after re-clustering. Without this,
        # labels follow raw cid index and become misaligned whenever the
        # graph has changed between labeling and cluster-only (#1027).
        previous_node_community = {
            n["id"]: n["community"]
            for n in _raw.get("nodes", [])
            if n.get("community") is not None and n.get("id") is not None
        }
        if previous_node_community:
            communities = remap_communities_to_previous(communities, previous_node_community)
        stages.mark("cluster")
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        stages.mark("analyze")
        # Where outputs (GRAPH_REPORT.md, re-clustered graph.json, labels,
        # analysis, html) land. When `--graph` points at a graph INSIDE a
        # graphify-out/ dir (another project/tenant's output), write beside it,
        # not into a stray graphify-out/ in the CWD (#1747). But when `--graph`
        # points at an arbitrary path — e.g. a `backup/graph.json` archived
        # before re-clustering (#934) — fall back to the CWD's graphify-out/,
        # which is the restore-into-place workflow that test pins. The default
        # (no --graph) case already has graph_json under watch_path/graphify-out.
        _out_name = Path(_GRAPHIFY_OUT).name
        if graph_override is not None and graph_json.parent.name == _out_name:
            out = graph_json.parent
        else:
            out = watch_path / _GRAPHIFY_OUT
        out.mkdir(parents=True, exist_ok=True)
        labels_path = out / ".graphify_labels.json"
        existing_labels: dict[int, str] = {}
        if labels_path.exists():
            try:
                existing_labels = {
                    int(k): v
                    for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()
                    if isinstance(v, str)
                }
            except Exception:
                existing_labels = {}
        # Accumulate token usage from the labeling LLM calls so cluster-only mode
        # reports real cost instead of a hardcoded zero (#1694). Stays {0, 0} on
        # the reuse / no-label paths, which make no LLM calls.
        label_token_usage = {"input": 0, "output": 0}
        if labels_path.exists() and not force_relabel:
            # Reuse saved labels, but don't blindly trust them: the graph may have
            # been re-scoped/re-clustered since labeling, in which case a cid now
            # covers a DIFFERENT community and its old (LLM) name is wrong (#label-stale).
            # Validate each community against the membership signature saved beside the
            # labels; any community that changed (or has no saved label) is renamed by
            # its current hub — deterministic and correct-by-construction — and the user
            # is told to `graphify label` for fresh LLM names. Unchanged communities keep
            # their saved label. When no signature sidecar exists (labels predate this),
            # fall back to hub-filling only the communities missing a label.
            from graphify.cluster import community_member_sigs, label_communities_by_hub
            sig_path = labels_path.parent / (labels_path.name + ".sig")
            saved_sigs: dict[int, str] = {}
            if sig_path.exists():
                try:
                    saved_sigs = {
                        int(k): v for k, v in
                        json.loads(sig_path.read_text(encoding="utf-8")).items()
                        if isinstance(v, str)
                    }
                except Exception:
                    saved_sigs = {}
            cur_sigs = community_member_sigs(communities)
            count_mismatch = len(existing_labels) != len(communities)
            labels = {}
            hub_labels: dict[int, str] | None = None
            changed = 0
            for cid in communities:
                have_label = cid in existing_labels
                if saved_sigs:
                    # Precise: the membership signature tells us if this exact
                    # community changed since it was labeled.
                    fresh = have_label and saved_sigs.get(cid) == cur_sigs.get(cid)
                else:
                    # No signature sidecar (labels predate it). A differing community
                    # COUNT means the labels describe a different clustering, so a cid's
                    # old label can't be trusted; equal count is the best "same" signal.
                    fresh = have_label and not count_mismatch
                if fresh:
                    labels[cid] = existing_labels[cid]
                else:
                    if hub_labels is None:
                        hub_labels = label_communities_by_hub(G, communities)
                    labels[cid] = hub_labels[cid]
                    if have_label:
                        changed += 1
            if changed:
                print(
                    f"[graphify] community set changed since labeling "
                    f"({len(existing_labels)} saved labels, {len(communities)} communities now; "
                    f"renamed {changed} community(ies) by their hub). "
                    f"Run `graphify label` to refresh names with the LLM.",
                    file=sys.stderr,
                )
        elif no_label and not force_relabel:
            labels = {cid: f"Community {cid}" for cid in communities}
        else:
            # No labels file yet (or `graphify label` forced a refresh). When run
            # standalone there is no orchestrating agent to do skill.md Step 5, so
            # auto-name communities rather than leave "Community N" (#1097).
            from graphify.cluster import label_communities_by_hub
            from graphify.llm import generate_community_labels
            print("Labeling communities...")
            # Deterministic, LLM-free base labels: name each community after its
            # highest-degree hub, so the report is readable even with no backend
            # (previously bare "Community N"). A configured LLM backend overrides these
            # with richer names below; its no-backend placeholder fallback does NOT.
            hub_labels = label_communities_by_hub(G, communities)
            label_communities_input = communities
            labels = dict(hub_labels)
            if missing_only:
                labels = {
                    cid: existing_labels.get(cid, hub_labels[cid])
                    for cid in communities
                }
                label_communities_input = {
                    cid: members
                    for cid, members in communities.items()
                    if cid not in existing_labels or existing_labels.get(cid) == f"Community {cid}"
                }
            generated_labels, _ = generate_community_labels(
                G, label_communities_input, backend=label_backend, model=label_model, gods=gods,
                max_concurrency=label_max_concurrency, batch_size=label_batch_size,
                usage_out=label_token_usage,
            )
            # Only let the LLM OVERRIDE where it produced a real name — its no-backend
            # fallback returns "Community {cid}" placeholders, which must not clobber
            # the deterministic hub labels.
            labels.update({
                cid: v for cid, v in generated_labels.items()
                if v and v != f"Community {cid}"
            })
        stages.mark("label")
        questions = suggest_questions(G, communities, labels)
        tokens = label_token_usage
        from graphify.export import _git_head as _gh
        _commit = _gh()
        from graphify.report import load_learning_for_report as _llfr
        report = generate(G, communities, cohesion, labels, gods, surprises,
                          {"warning": "cluster-only mode — file stats not available"},
                          tokens, str(watch_path), suggested_questions=questions,
                          min_community_size=min_community_size, built_at_commit=_commit,
                          learning=_llfr(out / "graph.json"))
        (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        stages.mark("report")
        from graphify.export import backup_if_protected as _backup
        _backup(out)
        analysis = {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "questions": questions,
        }
        (out / ".graphify_analysis.json").write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        to_json(G, communities, str(out / "graph.json"), community_labels=labels)
        labels_path.write_text(json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False), encoding="utf-8")
        # Membership signatures beside the labels so a later cluster-only can detect
        # which communities changed and avoid reusing a stale label (see reuse above).
        from graphify.cluster import community_member_sigs as _cms
        (labels_path.parent / (labels_path.name + ".sig")).write_text(
            json.dumps({str(k): v for k, v in _cms(communities).items()}), encoding="utf-8")

        # Mirror watch.py pattern: gate to_html so core outputs (graph.json +
        # GRAPH_REPORT.md) always land. Honor --no-viz explicitly; otherwise
        # fall back to ValueError handling so an oversized graph doesn't crash
        # the CLI mid-write and leave a stale graph.html on disk.
        html_target = out / "graph.html"
        if no_viz:
            if html_target.exists():
                html_target.unlink()
            stages.mark("export"); stages.total()
            print(f"Done - {len(communities)} communities. GRAPH_REPORT.md and graph.json updated (--no-viz; graph.html removed).")
        else:
            try:
                # Over-cap fallback (#1019): force the community-aggregation
                # path so an oversized graph still renders a usable graph.html.
                _node_limit = 5000 if _over_cap else None
                to_html(G, communities, str(html_target), community_labels=labels or None,
                        node_limit=_node_limit)
                stages.mark("export"); stages.total()
                print(f"Done - {len(communities)} communities. GRAPH_REPORT.md, graph.json and graph.html updated.")
            except ValueError as viz_err:
                if html_target.exists():
                    html_target.unlink()
                print(f"Skipped graph.html: {viz_err}")
                stages.mark("export"); stages.total()
                print(f"Done - {len(communities)} communities. GRAPH_REPORT.md and graph.json updated.")

    elif cmd == "update":
        force = os.environ.get("GRAPHIFY_FORCE", "").lower() in ("1", "true", "yes")
        no_cluster = False
        args = sys.argv[2:]
        watch_arg: str | None = None
        for a in args:
            if a == "--force":
                force = True
                continue
            if a == "--no-cluster":
                no_cluster = True
                continue
            if a.startswith("-"):
                print(f"error: unknown update option: {a}", file=sys.stderr)
                sys.exit(2)
            if watch_arg is not None:
                print("error: update accepts at most one path argument", file=sys.stderr)
                sys.exit(2)
            watch_arg = a

        if watch_arg is not None:
            watch_path = Path(watch_arg)
        else:
            # Try to recover the scan root saved by the last full build
            saved = Path(_GRAPHIFY_OUT) / ".graphify_root"
            if saved.exists():
                watch_path = Path(saved.read_text(encoding="utf-8").strip())
            else:
                watch_path = Path(".")
        if not watch_path.exists():
            print(f"error: path not found: {watch_path}", file=sys.stderr)
            sys.exit(1)
        from graphify.watch import _rebuild_code

        print(f"Re-extracting code files in {watch_path} (no LLM needed)...")
        # Interactive CLI: block on the per-repo lock rather than skip, so the
        # user sees their explicit `graphify update` complete instead of
        # exiting silently when a hook-driven rebuild happens to be running.
        ok = _rebuild_code(watch_path, force=force, no_cluster=no_cluster, block_on_lock=True)
        if ok:
            print("Code graph updated. For doc/paper/image changes run /graphify --update in your AI assistant.")
            if not (
                os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("MOONSHOT_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY")
                or os.environ.get("GRAPHIFY_NO_TIPS")
            ):
                print("Tip: set GEMINI_API_KEY or GOOGLE_API_KEY to use Gemini for semantic extraction.")
        else:
            print(
                "Nothing to update or rebuild failed — check output above.",
                file=sys.stderr,
            )
            sys.exit(1)

    elif cmd == "hook-check":
        # Codex Desktop rejects hookSpecificOutput.additionalContext on PreToolUse.
        # Keep this as a cross-platform no-op so installed hooks never break Bash
        # tool calls. Graph guidance reaches the agent via AGENTS.md / skill instead.
        sys.exit(0)
    elif cmd == "hook-guard":
        # Shell-agnostic Claude/Codebuddy PreToolUse guard (#522). Replaces the old
        # inline-bash hooks that failed on Windows. Prints an additionalContext nudge
        # toward graphify when a graph exists; always exits 0 (never blocks a tool).
        _run_hook_guard(sys.argv[2] if len(sys.argv) > 2 else "")
        sys.exit(0)
    elif cmd == "check-update":
        if len(sys.argv) < 3:
            print("Usage: graphify check-update <path>", file=sys.stderr)
            sys.exit(1)
        from graphify.watch import check_update

        check_update(Path(sys.argv[2]).resolve())
        sys.exit(0)
    elif cmd == "tree":
        # Emit a D3 v7 collapsible-tree HTML view of graph.json:
        # expand-all / collapse-all / reset-view buttons, multi-line
        # wrapText labels with separately-coloured name + count,
        # depth-based palette, click-to-toggle subtree, hover inspector
        # showing top-K outbound edges per symbol.
        from typing import Optional as _Opt
        from graphify.tree_html import write_tree_html, DEFAULT_MAX_CHILDREN
        graph_path = Path(_GRAPHIFY_OUT) / "graph.json"
        output_path: "_Opt[Path]" = None
        root: "_Opt[str]" = None
        max_children = DEFAULT_MAX_CHILDREN
        top_k_edges = 0
        project_label: "_Opt[str]" = None
        args = sys.argv[2:]
        i_arg = 0
        while i_arg < len(args):
            a = args[i_arg]
            if a == "--graph" and i_arg + 1 < len(args):
                graph_path = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--output" and i_arg + 1 < len(args):
                output_path = Path(args[i_arg + 1]); i_arg += 2
            elif a == "--root" and i_arg + 1 < len(args):
                root = args[i_arg + 1]; i_arg += 2
            elif a == "--max-children" and i_arg + 1 < len(args):
                max_children = int(args[i_arg + 1]); i_arg += 2
            elif a == "--top-k-edges" and i_arg + 1 < len(args):
                top_k_edges = int(args[i_arg + 1]); i_arg += 2
            elif a == "--label" and i_arg + 1 < len(args):
                project_label = args[i_arg + 1]; i_arg += 2
            elif a in ("-h", "--help"):
                print("Usage: graphify tree [--graph PATH] [--output HTML]")
                print("  --graph PATH         path to graph.json (default graphify-out/graph.json)")
                print("  --output HTML        output path (default graphify-out/GRAPH_TREE.html)")
                print("  --root PATH          filesystem root (default: longest common dir of all source_files)")
                print("  --max-children N     cap visible children per node (default 200)")
                print("  --top-k-edges N      pre-compute top-K outbound edges per symbol (default 12)")
                print("  --label NAME         project label shown in the page header")
                return
            else:
                i_arg += 1
        if not graph_path.is_file():
            print(f"error: graph.json not found at {graph_path}", file=sys.stderr)
            sys.exit(1)
        _enforce_graph_size_cap_or_exit(graph_path)
        if output_path is None:
            output_path = graph_path.parent / "GRAPH_TREE.html"
        out = write_tree_html(
            graph_path=graph_path, output_path=output_path,
            root=root, max_children=max_children,
            top_k_edges=top_k_edges, project_label=project_label,
        )
        size_kb = out.stat().st_size / 1024
        print(f"wrote {out} ({size_kb:.1f} KB)")
        print(f"open with: xdg-open {out}  (or file://{out.resolve()})")
        sys.exit(0)

    elif cmd == "merge-driver":
        # git merge driver for graph.json — takes (base, current, other) and writes
        # the union of current+other nodes/edges back to current. Exits 1 on
        # corrupt input so git surfaces the conflict instead of silently
        # accepting a poisoned merge (see F-005).
        # Usage: graphify merge-driver %O %A %B  (set in .git/config merge driver)
        if len(sys.argv) < 5:
            print("Usage: graphify merge-driver <base> <current> <other>", file=sys.stderr)
            sys.exit(1)
        _base_path, _current_path, _other_path = sys.argv[2], sys.argv[3], sys.argv[4]
        # Hard caps so a malicious or corrupted graph.json cannot exhaust memory
        # at parse time. 50 MB / 100k nodes are well above any realistic graph
        # (typical graphs are <5 MB / <50k nodes); anything larger should fail
        # the merge so a human can investigate.
        _MERGE_MAX_BYTES = 50 * 1024 * 1024
        _MERGE_MAX_NODES = 100_000
        import networkx as _nx
        from networkx.readwrite import json_graph as _jg
        def _load_graph(p: str):
            path_obj = Path(p)
            try:
                size = path_obj.stat().st_size
            except OSError as exc:
                raise RuntimeError(f"cannot stat {p}: {exc}") from exc
            if size > _MERGE_MAX_BYTES:
                raise RuntimeError(
                    f"graph.json {p} is {size} bytes, exceeds {_MERGE_MAX_BYTES}-byte cap"
                )
            data = json.loads(path_obj.read_text(encoding="utf-8"))
            try:
                return _jg.node_link_graph(data, edges="links"), data
            except TypeError:
                return _jg.node_link_graph(data), data
        try:
            G_cur, _ = _load_graph(_current_path)
            G_oth, _ = _load_graph(_other_path)
        except Exception as exc:
            print(f"[graphify merge-driver] error loading graphs: {exc}", file=sys.stderr)
            sys.exit(1)  # surface the conflict so git doesn't accept a corrupt merge
        merged = _nx.compose(G_cur, G_oth)
        if merged.number_of_nodes() > _MERGE_MAX_NODES:
            print(
                f"[graphify merge-driver] merged graph has {merged.number_of_nodes()} nodes, "
                f"exceeds {_MERGE_MAX_NODES}-node cap; aborting merge.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            out_data = _jg.node_link_data(merged, edges="links")
        except TypeError:
            out_data = _jg.node_link_data(merged)
        Path(_current_path).write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        sys.exit(0)

    elif cmd == "merge-graphs":
        # graphify merge-graphs graph1.json graph2.json ... --out merged.json
        args = sys.argv[2:]
        graph_paths: list[Path] = []
        out_path = Path(_GRAPHIFY_OUT) / "merged-graph.json"
        i = 0
        while i < len(args):
            if args[i] == "--out" and i + 1 < len(args):
                out_path = Path(args[i + 1])
                i += 2
            else:
                graph_paths.append(Path(args[i]))
                i += 1
        if len(graph_paths) < 2:
            print(
                "Usage: graphify merge-graphs <graph1.json> <graph2.json> [...] [--out merged.json]",
                file=sys.stderr,
            )
            sys.exit(1)
        import networkx as _nx
        from networkx.readwrite import json_graph as _jg
        from graphify.build import prefix_graph_for_global as _prefix, distinct_repo_tags as _repo_tags
        graphs = []
        for gp in graph_paths:
            if not gp.exists():
                print(f"error: not found: {gp}", file=sys.stderr)
                sys.exit(1)
            _enforce_graph_size_cap_or_exit(gp)
            data = json.loads(gp.read_text(encoding="utf-8"))
            # Normalize edges/links key before loading — graphify writes "links"
            # via node_link_data but older runs may have used "edges" (#738).
            if "links" not in data and "edges" in data:
                data = dict(data, links=data["edges"])
            try:
                G = _jg.node_link_graph(data, edges="links")
            except TypeError:
                G = _jg.node_link_graph(data)
            graphs.append(G)
        # nx.compose requires all graphs to be the same type.  When input graphs
        # come from different sources (e.g. an AST-only run vs a full LLM run) one
        # may be a MultiGraph and another a Graph.  Normalise everything to Graph
        # (the graphify default) by converting MultiGraphs with nx.Graph().
        def _to_simple(g: "_nx.Graph") -> "_nx.Graph":
            # nx.compose requires every graph to be the same type. Inputs may
            # disagree on BOTH axes — directed vs undirected, and multi vs simple
            # — because per-repo graph.json files are written by different extract
            # paths at different times. Normalise everything to a plain undirected
            # Graph (the merged cross-repo view is undirected anyway), which covers
            # DiGraph / MultiGraph / MultiDiGraph. Without this a directed input
            # crashed compose with "All graphs must be directed or undirected" (#1606).
            if type(g) is not _nx.Graph:
                return _nx.Graph(g)
            return g
        # Unique repo tag per graph. The bare `graphify-out/..` dir name is not
        # unique across inputs (src/graphify-out and frontend/src/graphify-out both
        # → "src"), which collides same-stem node ids and silently merges unrelated
        # entities (#1729). distinct_repo_tags guarantees a distinct prefix per graph.
        repo_tags = _repo_tags(graph_paths)
        naive_tags = [gp.parent.parent.name for gp in graph_paths]
        if len(set(naive_tags)) != len(naive_tags):
            print(f"  note: repo dir names collide; using distinct tags: {', '.join(repo_tags)}")
        merged = _nx.Graph()
        for G, repo_tag in zip(graphs, repo_tags):
            prefixed = _to_simple(_prefix(G, repo_tag))
            merged = _nx.compose(merged, prefixed)
        try:
            out_data = _jg.node_link_data(merged, edges="links")
        except TypeError:
            out_data = _jg.node_link_data(merged)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        print(f"Merged {len(graphs)} graphs -> {merged.number_of_nodes()} nodes, {merged.number_of_edges()} edges")
        print(f"Written to: {out_path}")

    elif cmd == "clone":
        if len(sys.argv) < 3:
            print(
                "Usage: graphify clone <github-url> [--branch <branch>] [--out <dir>]",
                file=sys.stderr,
            )
            sys.exit(1)
        url = sys.argv[2]
        branch: str | None = None
        out_dir: Path | None = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--branch" and i + 1 < len(args):
                branch = args[i + 1]
                i += 2
            elif args[i] == "--out" and i + 1 < len(args):
                out_dir = Path(args[i + 1])
                i += 2
            else:
                i += 1
        local_path = _clone_repo(url, branch=branch, out_dir=out_dir)
        print(local_path)

    elif cmd == "export":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd not in ("html", "callflow-html", "obsidian", "wiki", "svg", "graphml", "neo4j", "falkordb"):
            print("Usage: graphify export <format>", file=sys.stderr)
            print("  html      [--graph PATH] [--labels PATH] [--node-limit N] [--no-viz]", file=sys.stderr)
            print("  callflow-html [GRAPH|DIR] [--graph PATH] [--labels PATH] [--report PATH] [--sections PATH] [--output HTML]", file=sys.stderr)
            print("            [--lang auto|zh-CN|en] [--max-sections N] [--diagram-scale N]", file=sys.stderr)
            print("  obsidian  [--graph PATH] [--labels PATH] [--dir PATH]", file=sys.stderr)
            print("  wiki      [--graph PATH] [--labels PATH]", file=sys.stderr)
            print("  svg       [--graph PATH] [--labels PATH]", file=sys.stderr)
            print("  graphml   [--graph PATH]", file=sys.stderr)
            print("  neo4j     [--graph PATH] [--push URI] [--user U] [--password P]", file=sys.stderr)
            print("            (or set NEO4J_PASSWORD instead of --password to keep it off argv)", file=sys.stderr)
            print("  falkordb  [--graph PATH] [--push URI] [--user U] [--password P]", file=sys.stderr)
            print("            (or set FALKORDB_PASSWORD instead of --password to keep it off argv)", file=sys.stderr)
            sys.exit(1)

        # Parse shared args
        args = sys.argv[3:]
        graph_path = Path(_GRAPHIFY_OUT) / "graph.json"
        graph_path_explicit = False
        labels_path = Path(_GRAPHIFY_OUT) / ".graphify_labels.json"
        labels_path_explicit = False
        report_path = Path(_GRAPHIFY_OUT) / "GRAPH_REPORT.md"
        report_path_explicit = False
        sections_path: Path | None = None
        callflow_output: Path | None = None
        callflow_lang = "auto"
        callflow_max_sections = 15
        callflow_diagram_scale = 1.0
        callflow_max_diagram_nodes = 18
        callflow_max_diagram_edges = 24
        analysis_path = Path(_GRAPHIFY_OUT) / ".graphify_analysis.json"
        node_limit = 5000
        no_viz = False
        obsidian_dir = Path(_GRAPHIFY_OUT) / "obsidian"
        # Shared push-connection settings for the graph-database sinks (neo4j,
        # falkordb), parsed from the generic --push/--user/--password flags below.
        push_uri: str | None = None
        push_user = "neo4j"  # Neo4j default user; FalkorDB auth is optional and ignores it
        # F-031: prefer an env var so the password never appears on argv (visible
        # in `ps` output / shell history). The explicit --password flag still
        # overrides it. Each sink reads its own var: FALKORDB_PASSWORD for falkordb,
        # NEO4J_PASSWORD otherwise.
        push_password: str | None = (
            os.environ.get("FALKORDB_PASSWORD") if subcmd == "falkordb"
            else os.environ.get("NEO4J_PASSWORD")
        ) or None
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--graph" and i + 1 < len(args):
                graph_path = Path(args[i + 1])
                graph_path_explicit = True
                i += 2
            elif a == "--labels" and i + 1 < len(args):
                labels_path = Path(args[i + 1])
                labels_path_explicit = True
                i += 2
            elif a == "--report" and i + 1 < len(args):
                report_path = Path(args[i + 1])
                report_path_explicit = True
                i += 2
            elif a == "--sections" and i + 1 < len(args):
                sections_path = Path(args[i + 1]); i += 2
            elif a == "--output" and i + 1 < len(args):
                callflow_output = Path(args[i + 1]).expanduser()
                if not callflow_output.is_absolute():
                    callflow_output = Path.cwd() / callflow_output
                i += 2
            elif a == "--lang" and i + 1 < len(args):
                callflow_lang = args[i + 1]; i += 2
            elif a == "--max-sections" and i + 1 < len(args):
                callflow_max_sections = int(args[i + 1]); i += 2
            elif a == "--diagram-scale" and i + 1 < len(args):
                callflow_diagram_scale = float(args[i + 1]); i += 2
            elif a == "--max-diagram-nodes" and i + 1 < len(args):
                callflow_max_diagram_nodes = int(args[i + 1]); i += 2
            elif a == "--max-diagram-edges" and i + 1 < len(args):
                callflow_max_diagram_edges = int(args[i + 1]); i += 2
            elif a in ("-h", "--help") and subcmd == "callflow-html":
                print("Usage: graphify export callflow-html [GRAPH|DIR] [--graph PATH] [--labels PATH]")
                print("  --report PATH          path to GRAPH_REPORT.md")
                print("  --sections PATH        JSON section definitions")
                print("  --output HTML          output path (default graphify-out/<project>-callflow.html)")
                print("  --lang LANG            auto, zh-CN, en, etc. (default auto)")
                print("  --max-sections N       maximum auto-derived sections (default 15)")
                print("  --diagram-scale N      Mermaid diagram scale (default 1.0)")
                print("  --max-diagram-nodes N  representative nodes per section (default 18)")
                print("  --max-diagram-edges N  representative edges per section (default 24)")
                sys.exit(0)
            elif a == "--node-limit" and i + 1 < len(args):
                node_limit = int(args[i + 1]); i += 2
            elif a == "--no-viz":
                no_viz = True; i += 1
            elif a == "--dir" and i + 1 < len(args):
                obsidian_dir = Path(args[i + 1]); i += 2
            elif a == "--push" and i + 1 < len(args):
                push_uri = args[i + 1]; i += 2
            elif a == "--user" and i + 1 < len(args):
                push_user = args[i + 1]; i += 2
            elif a == "--password" and i + 1 < len(args):
                push_password = args[i + 1]; i += 2
            elif subcmd == "callflow-html" and not a.startswith("-") and not graph_path_explicit:
                candidate = Path(a)
                if candidate.name == "graph.json" or candidate.suffix.lower() == ".json":
                    graph_path = candidate
                elif (candidate / "graph.json").exists():
                    graph_path = candidate / "graph.json"
                else:
                    graph_path = candidate / _GRAPHIFY_OUT / "graph.json"
                graph_path_explicit = True
                i += 1
            else:
                i += 1

        graph_path = graph_path.expanduser()
        if graph_path_explicit:
            graph_out_dir = graph_path.parent
            if not labels_path_explicit:
                labels_path = graph_out_dir / ".graphify_labels.json"
            if not report_path_explicit:
                report_path = graph_out_dir / "GRAPH_REPORT.md"
        labels_path = labels_path.expanduser()
        report_path = report_path.expanduser()

        if not graph_path.exists():
            print(f"error: graph not found: {graph_path}. Run /graphify <path> first.", file=sys.stderr)
            sys.exit(1)

        if subcmd == "callflow-html":
            from graphify.callflow_html import write_callflow_html as _write_callflow_html
            out = _write_callflow_html(
                graph=graph_path,
                report=report_path,
                labels=labels_path,
                sections=sections_path,
                output=callflow_output,
                lang=callflow_lang,
                max_sections=callflow_max_sections,
                diagram_scale=callflow_diagram_scale,
                max_diagram_nodes=callflow_max_diagram_nodes,
                max_diagram_edges=callflow_max_diagram_edges,
                verbose=True,
            )
            print(f"callflow HTML written - open in any browser: {out}")
            sys.exit(0)

        from networkx.readwrite import json_graph as _jg
        from graphify.build import build_from_json as _bfj
        from graphify.security import check_graph_file_size_cap as _check_cap

        # Solution 3 (#1019): for the HTML view, an oversized graph.json should
        # not be a hard error. Detect the over-cap condition here and fall back
        # to the community-aggregation view (node_limit=5000) below instead of
        # exiting 1. All other subcommands keep the hard cap.
        _over_cap = False
        try:
            _check_cap(graph_path)
        except ValueError as _cap_err:
            if subcmd == "html":
                _over_cap = True
                try:
                    _over_cap_bytes = graph_path.stat().st_size
                except OSError:
                    _over_cap_bytes = -1
                print(
                    f"warning: graph.json exceeds cap ({_over_cap_bytes} bytes); "
                    f"falling back to community-aggregation view (node_limit=5000)",
                    file=sys.stderr,
                )
            else:
                print(f"error: {_cap_err}", file=sys.stderr)
                sys.exit(1)
        _raw = json.loads(graph_path.read_text(encoding="utf-8"))
        if "links" not in _raw and "edges" in _raw:
            _raw = dict(_raw, links=_raw["edges"])
        try:
            G = _jg.node_link_graph(_raw, edges="links")
        except TypeError:
            G = _jg.node_link_graph(_raw)

        # Load optional analysis/labels
        communities: dict[int, list[str]] = {}
        if analysis_path.exists():
            _an = json.loads(analysis_path.read_text(encoding="utf-8"))
            communities = {int(k): v for k, v in _an.get("communities", {}).items()}
            cohesion: dict[int, float] = {int(k): v for k, v in _an.get("cohesion", {}).items()}
            gods_data = _an.get("gods", [])
        else:
            cohesion = {}
            gods_data = []

        # Fallback: graph.json carries the per-node community as a node attribute
        # (`to_json` writes it on every node). The analysis sidecar is the
        # canonical source — but the post-commit / watch rebuild path doesn't
        # regenerate it, and `extract` may have its temp files cleaned up. When
        # that happens, `graphify export html` previously bailed with
        # "Single community - aggregated view not useful." even though the
        # per-node attribute had the right data all along. Reconstruct from
        # the graph itself so downstream subcommands (html, obsidian, wiki,
        # svg, graphml, neo4j) don't silently produce a degraded artifact.
        if not communities:
            reconstructed: dict[int, list[str]] = {}
            for node_id, data in G.nodes(data=True):
                cid_raw = data.get("community")
                if cid_raw is None:
                    continue
                try:
                    cid = int(cid_raw)
                except (TypeError, ValueError):
                    continue
                reconstructed.setdefault(cid, []).append(str(node_id))
            if reconstructed:
                communities = reconstructed

        labels: dict[int, str] = {}
        if labels_path.exists():
            labels = {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}

        out_dir = graph_path.parent

        if subcmd == "html":
            from graphify.export import to_html as _to_html
            if no_viz:
                html_target = out_dir / "graph.html"
                if html_target.exists():
                    html_target.unlink()
                print("--no-viz: skipped graph.html")
            else:
                # Over-cap fallback (#1019): force the community-aggregation
                # path so the oversized graph still renders a usable artifact.
                _effective_node_limit = 5000 if _over_cap else node_limit
                _to_html(G, communities, str(out_dir / "graph.html"),
                         community_labels=labels or None, node_limit=_effective_node_limit)
                if G.number_of_nodes() <= _effective_node_limit:
                    print(f"graph.html written - open in any browser, no server needed")
                if _over_cap:
                    sys.exit(0)

        elif subcmd == "obsidian":
            from graphify.export import to_obsidian as _to_obsidian, to_canvas as _to_canvas
            n = _to_obsidian(G, communities, str(obsidian_dir),
                             community_labels=labels or None, cohesion=cohesion or None)
            print(f"Obsidian vault: {n} notes in {obsidian_dir}/")
            _to_canvas(G, communities, str(obsidian_dir / "graph.canvas"),
                       community_labels=labels or None)
            print(f"Canvas: {obsidian_dir}/graph.canvas")
            print(f"Open {obsidian_dir}/ as a vault in Obsidian.")

        elif subcmd == "wiki":
            from graphify.wiki import to_wiki as _to_wiki
            from graphify.analyze import god_nodes as _god_nodes
            if not communities:
                print(
                    "error: .graphify_analysis.json is missing or empty — refusing to export wiki to prevent data loss.\n"
                    "Run `graphify extract .` (or `graphify cluster-only .`) to regenerate community data first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not gods_data:
                gods_data = _god_nodes(G)
            n = _to_wiki(G, communities, str(out_dir / "wiki"),
                         community_labels=labels or None, cohesion=cohesion or None,
                         god_nodes_data=gods_data)
            print(f"Wiki: {n} articles written to {out_dir}/wiki/")
            print(f"  {out_dir}/wiki/index.md  ->  agent entry point")

        elif subcmd == "svg":
            from graphify.export import to_svg as _to_svg
            _to_svg(G, communities, str(out_dir / "graph.svg"),
                    community_labels=labels or None)
            print(f"graph.svg written - embeds in Obsidian, Notion, GitHub READMEs")

        elif subcmd == "graphml":
            from graphify.export import to_graphml as _to_graphml
            _to_graphml(G, communities, str(out_dir / "graph.graphml"))
            print(f"graph.graphml written - open in Gephi, yEd, or any GraphML tool")

        elif subcmd == "neo4j":
            if push_uri:
                from graphify.export import push_to_neo4j as _push
                if push_password is None:
                    print("error: --password required for --push", file=sys.stderr)
                    sys.exit(1)
                result = _push(G, uri=push_uri, user=push_user,
                               password=push_password, communities=communities)
                print(f"Pushed to Neo4j: {result['nodes']} nodes, {result['edges']} edges")
            else:
                from graphify.export import to_cypher as _to_cypher
                _to_cypher(G, str(out_dir / "cypher.txt"))
                print(f"cypher.txt written - import with: cypher-shell < {out_dir}/cypher.txt")

        elif subcmd == "falkordb":
            if push_uri:
                from graphify.export import push_to_falkordb as _push
                result = _push(G, uri=push_uri, user=push_user,
                               password=push_password, communities=communities)
                print(f"Pushed to FalkorDB: {result['nodes']} nodes, {result['edges']} edges")
            else:
                from graphify.export import to_cypher as _to_cypher
                _to_cypher(G, str(out_dir / "cypher.txt"))
                print(f"cypher.txt written ({out_dir}/cypher.txt) - statements are OpenCypher. "
                      f"FalkorDB's GRAPH.QUERY runs one statement at a time (no bulk script "
                      f"import), so load a graph with: graphify export falkordb --push "
                      f"falkordb://localhost:6379")

    elif cmd == "benchmark":
        from graphify.benchmark import run_benchmark, print_benchmark

        graph_path = sys.argv[2] if len(sys.argv) > 2 else _default_graph_path()
        _enforce_graph_size_cap_or_exit(Path(graph_path))
        # Try to load corpus_words from detect output
        corpus_words = None
        detect_path = Path(".graphify_detect.json")
        if detect_path.exists():
            try:
                detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
                corpus_words = detect_data.get("total_words")
            except Exception:
                pass
        result = run_benchmark(graph_path, corpus_words=corpus_words)
        print_benchmark(result)

    elif cmd == "global":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        from graphify.global_graph import (
            global_add as _global_add,
            global_remove as _global_remove,
            global_list as _global_list,
            global_path as _global_path,
        )
        if subcmd == "add":
            # graphify global add <graph.json> [--as <tag>]
            args = sys.argv[3:]
            source = None
            tag = None
            i = 0
            while i < len(args):
                if args[i] == "--as" and i + 1 < len(args):
                    tag = args[i + 1]; i += 2
                elif not source:
                    source = Path(args[i]); i += 1
                else:
                    i += 1
            if not source:
                print("Usage: graphify global add <graph.json> [--as <repo-tag>]", file=sys.stderr)
                sys.exit(1)
            tag = tag or source.parent.parent.name
            try:
                result = _global_add(source, tag)
                if result["skipped"]:
                    print(f"'{tag}' unchanged since last add - global graph not modified.")
                else:
                    print(f"Added '{tag}' to global graph: +{result['nodes_added']} nodes, "
                          f"-{result['nodes_removed']} pruned. Global: {_global_path()}")
            except Exception as exc:
                print(f"error: {exc}", file=sys.stderr); sys.exit(1)
        elif subcmd == "remove":
            tag = sys.argv[3] if len(sys.argv) > 3 else ""
            if not tag:
                print("Usage: graphify global remove <repo-tag>", file=sys.stderr); sys.exit(1)
            try:
                removed = _global_remove(tag)
                print(f"Removed '{tag}' from global graph ({removed} nodes pruned).")
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr); sys.exit(1)
        elif subcmd == "list":
            repos = _global_list()
            if not repos:
                print("Global graph is empty. Use 'graphify global add' to add a project.")
            else:
                print(f"Global graph: {_global_path()}")
                for tag, info in repos.items():
                    print(f"  {tag}: {info.get('node_count', '?')} nodes, added {info.get('added_at', '?')[:10]}")
        elif subcmd == "path":
            print(_global_path())
        else:
            print("Usage: graphify global [add|remove|list|path]", file=sys.stderr); sys.exit(1)

    elif cmd == "extract":
        # Headless full-pipeline extraction for CI / scripts (#698).
        # Runs detect -> AST extraction on code -> semantic LLM extraction on
        # docs/papers/images -> merge -> build -> cluster -> write outputs.
        # Unlike the skill.md path (which runs through Claude Code subagents),
        # this calls extract_corpus_parallel directly using whichever backend
        # has an API key set.
        if len(sys.argv) < 3:
            print(
                "Usage: graphify extract <path> [--backend gemini|kimi|claude|openai|deepseek|ollama] "
                "[--model M] [--mode deep] [--out DIR] [--google-workspace] [--no-cluster] "
                "[--max-workers N] [--token-budget N] [--max-concurrency N] "
                "[--api-timeout S] [--postgres DSN] [--cargo] [--timing]",
                file=sys.stderr,
            )
            sys.exit(1)

        has_path = True
        if sys.argv[2].startswith("-"):
            has_path = False
            target = Path(".").resolve()
        else:
            target = Path(sys.argv[2]).resolve()
            if not target.exists():
                print(f"error: path not found: {target}", file=sys.stderr)
                sys.exit(1)

        backend: str | None = None
        model: str | None = None
        extract_mode: str | None = None
        out_dir: Path | None = None
        cli_postgres_dsn: str | None = None
        cli_cargo: bool = False
        no_cluster = False
        dedup_llm = False
        google_workspace = False
        global_merge = False
        code_only = False
        global_repo_tag: str | None = None
        # Performance/tuning knobs (issue #792). None means "use library default".
        cli_max_workers: int | None = None
        cli_token_budget: int | None = None
        cli_max_concurrency: int | None = None
        cli_api_timeout: float | None = None
        # Clustering tuning knobs
        cli_resolution: float = 1.0
        cli_exclude_hubs: float | None = None
        cli_excludes: list[str] = []
        cli_timing: bool = False

        def _parse_int(name: str, raw: str) -> int:
            try:
                v = int(raw)
            except ValueError:
                print(f"error: {name} must be a positive integer (got {raw!r})", file=sys.stderr)
                sys.exit(2)
            if v <= 0:
                print(f"error: {name} must be > 0 (got {v})", file=sys.stderr)
                sys.exit(2)
            return v

        def _parse_float(name: str, raw: str) -> float:
            try:
                v = float(raw)
            except ValueError:
                print(f"error: {name} must be a positive number (got {raw!r})", file=sys.stderr)
                sys.exit(2)
            if v <= 0:
                print(f"error: {name} must be > 0 (got {v})", file=sys.stderr)
                sys.exit(2)
            return v

        args = sys.argv[3:] if has_path else sys.argv[2:]
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--backend" and i + 1 < len(args):
                backend = args[i + 1]; i += 2
            elif a.startswith("--backend="):
                backend = a.split("=", 1)[1]; i += 1
            elif a == "--model" and i + 1 < len(args):
                model = args[i + 1]; i += 2
            elif a.startswith("--model="):
                model = a.split("=", 1)[1]; i += 1
            elif a == "--mode" and i + 1 < len(args):
                extract_mode = args[i + 1]; i += 2
            elif a.startswith("--mode="):
                extract_mode = a.split("=", 1)[1]; i += 1
            elif a == "--out" and i + 1 < len(args):
                out_dir = Path(args[i + 1]); i += 2
            elif a.startswith("--out="):
                out_dir = Path(a.split("=", 1)[1]); i += 1
            elif a == "--no-cluster":
                no_cluster = True; i += 1
            elif a == "--dedup-llm":
                dedup_llm = True; i += 1
            elif a == "--code-only":
                code_only = True; i += 1
            elif a == "--google-workspace":
                google_workspace = True; i += 1
            elif a == "--global":
                global_merge = True; i += 1
            elif a == "--as" and i + 1 < len(args):
                global_repo_tag = args[i + 1]; i += 2
            elif a == "--max-workers" and i + 1 < len(args):
                cli_max_workers = _parse_int("--max-workers", args[i + 1]); i += 2
            elif a.startswith("--max-workers="):
                cli_max_workers = _parse_int("--max-workers", a.split("=", 1)[1]); i += 1
            elif a == "--token-budget" and i + 1 < len(args):
                cli_token_budget = _parse_int("--token-budget", args[i + 1]); i += 2
            elif a.startswith("--token-budget="):
                cli_token_budget = _parse_int("--token-budget", a.split("=", 1)[1]); i += 1
            elif a == "--max-concurrency" and i + 1 < len(args):
                cli_max_concurrency = _parse_int("--max-concurrency", args[i + 1]); i += 2
            elif a.startswith("--max-concurrency="):
                cli_max_concurrency = _parse_int("--max-concurrency", a.split("=", 1)[1]); i += 1
            elif a == "--api-timeout" and i + 1 < len(args):
                cli_api_timeout = _parse_float("--api-timeout", args[i + 1]); i += 2
            elif a.startswith("--api-timeout="):
                cli_api_timeout = _parse_float("--api-timeout", a.split("=", 1)[1]); i += 1
            elif a == "--resolution" and i + 1 < len(args):
                cli_resolution = _parse_float("--resolution", args[i + 1]); i += 2
            elif a.startswith("--resolution="):
                cli_resolution = _parse_float("--resolution", a.split("=", 1)[1]); i += 1
            elif a == "--exclude-hubs" and i + 1 < len(args):
                cli_exclude_hubs = float(args[i + 1]); i += 2
            elif a.startswith("--exclude-hubs="):
                cli_exclude_hubs = float(a.split("=", 1)[1]); i += 1
            elif a == "--exclude" and i + 1 < len(args):
                cli_excludes.append(args[i + 1]); i += 2
            elif a.startswith("--exclude="):
                cli_excludes.append(a.split("=", 1)[1]); i += 1
            elif a == "--postgres" and i + 1 < len(args):
                cli_postgres_dsn = args[i + 1]; i += 2
            elif a.startswith("--postgres="):
                cli_postgres_dsn = a.split("=", 1)[1]; i += 1
            elif a == "--cargo":
                cli_cargo = True
                i += 1
            elif a == "--timing":
                cli_timing = True; i += 1
            else:
                i += 1

        if not has_path and cli_postgres_dsn is None:
            print("error: must specify a path to scan or a --postgres DSN", file=sys.stderr)
            sys.exit(1)

        _VALID_MODES = {"deep"}
        if extract_mode is not None and extract_mode not in _VALID_MODES:
            print(
                f"error: unknown --mode '{extract_mode}'. "
                f"Available: {', '.join(sorted(_VALID_MODES))}",
                file=sys.stderr,
            )
            sys.exit(2)
        deep_mode = extract_mode == "deep"
        if deep_mode:
            print("[graphify extract] deep mode enabled: richer semantic extraction")

        # CLI flag wins over env var. Setting GRAPHIFY_API_TIMEOUT here so
        # _call_openai_compat picks it up without needing a new kwarg path.
        if cli_api_timeout is not None:
            os.environ["GRAPHIFY_API_TIMEOUT"] = str(cli_api_timeout)
        if cli_max_workers is not None:
            os.environ["GRAPHIFY_MAX_WORKERS"] = str(cli_max_workers)

        # Resolve output dir. The user-facing contract is "<out>/graphify-out/"
        # so a fresh checkout writes graphify-out/ at the project root, matching
        # the skill.md pipeline.
        out_root = (out_dir.resolve() if out_dir else target)
        graphify_out = out_root / _GRAPHIFY_OUT
        graphify_out.mkdir(parents=True, exist_ok=True)
        # Persist --exclude so later update/watch/hook rebuilds re-apply it
        # instead of silently re-including the excluded paths (#1886).
        from graphify.watch import _write_build_config as _write_build_cfg
        _write_build_cfg(graphify_out, excludes=cli_excludes or None)

        stages = _StageTimer(cli_timing)

        from graphify.detect import (
            detect as _detect,
            detect_incremental as _detect_incremental,
            save_manifest as _save_manifest,
        )
        manifest_path = graphify_out / "manifest.json"
        existing_graph_path = graphify_out / "graph.json"
        incremental_mode = manifest_path.exists() and existing_graph_path.exists() if has_path else False

        if not has_path:
            code_files = []
            doc_files = []
            paper_files = []
            image_files = []
            deleted_files = []
            unchanged_total = 0
            files_by_type = {}
        elif incremental_mode:
            print(f"[graphify extract] incremental scan of {target}")
            detection = _detect_incremental(
                target,
                manifest_path=str(manifest_path),
                google_workspace=google_workspace or None,
                extra_excludes=cli_excludes or None,
            )
            files_by_type = detection.get("files", {})
            new_by_type = detection.get("new_files", {})
            code_files = [Path(p) for p in new_by_type.get("code", [])]
            doc_files = [Path(p) for p in new_by_type.get("document", [])]
            paper_files = [Path(p) for p in new_by_type.get("paper", [])]
            image_files = [Path(p) for p in new_by_type.get("image", [])]
            deleted_files = list(detection.get("deleted_files", []))
            unchanged_total = sum(len(v) for v in detection.get("unchanged_files", {}).values())
        else:
            print(f"[graphify extract] scanning {target}")
            detection = _detect(target, google_workspace=google_workspace or None, extra_excludes=cli_excludes or None, cache_root=out_root)
            files_by_type = detection.get("files", {})
            code_files = [Path(p) for p in files_by_type.get("code", [])]
            doc_files = [Path(p) for p in files_by_type.get("document", [])]
            paper_files = [Path(p) for p in files_by_type.get("paper", [])]
            image_files = [Path(p) for p in files_by_type.get("image", [])]
            deleted_files = []
            unchanged_total = 0

        semantic_files = doc_files + paper_files + image_files
        # --code-only: index code (pure local AST, no key) and skip the semantic
        # (doc/paper/image) pass entirely, so a mixed repo doesn't hard-fail when no
        # LLM backend is configured (#1734). Report what was skipped rather than
        # silently dropping it.
        if code_only and semantic_files:
            print(
                f"[graphify extract] --code-only: skipping {len(semantic_files)} "
                f"non-code file(s) ({len(doc_files)} docs, {len(paper_files)} papers, "
                f"{len(image_files)} images) — no LLM extraction"
            )
            semantic_files = []
            doc_files = []
            paper_files = []
            image_files = []
        if incremental_mode:
            print(
                f"[graphify extract] {len(code_files)} code, {len(doc_files)} docs, "
                f"{len(paper_files)} papers, {len(image_files)} images changed; "
                f"{unchanged_total} unchanged; {len(deleted_files)} deleted"
            )
        else:
            print(
                f"[graphify extract] found {len(code_files)} code, "
                f"{len(doc_files)} docs, {len(paper_files)} papers, "
                f"{len(image_files)} images"
            )
        # Surface files that were seen but not classified (extensionless non-shebang
        # project files like Dockerfile/Makefile, or unsupported extensions), so they
        # are no longer invisible in graphify's own output (#1692).
        _unclassified = detection.get("unclassified", []) if isinstance(detection, dict) else []
        if _unclassified:
            _names = ", ".join(sorted({Path(p).name for p in _unclassified})[:6])
            _more = f" (+{len(_unclassified) - 6} more)" if len(_unclassified) > 6 else ""
            print(
                f"[graphify extract] {len(_unclassified)} file(s) not classified "
                f"(no supported extension or shebang), skipped: {_names}{_more}"
            )
        stages.mark("detect")

        # Resolve the LLM backend only now that we know whether the corpus
        # needs one. A code-only corpus is pure local AST and must not require
        # an API key; the key is enforced below only when there's LLM work.
        from graphify.llm import (
            BACKENDS as _BACKENDS,
            detect_backend as _detect_backend,
            estimate_cost as _estimate_cost,
            extract_corpus_parallel as _extract_corpus_parallel,
            _format_backend_env_keys,
            _get_backend_api_key,
        )
        needs_llm = bool(semantic_files) or dedup_llm
        if backend is None and needs_llm:
            backend = _detect_backend()
        if backend is not None and backend not in _BACKENDS:
            print(
                f"error: unknown backend '{backend}'. "
                f"Available: {', '.join(sorted(_BACKENDS))}",
                file=sys.stderr,
            )
            sys.exit(1)
        if needs_llm:
            if backend is None:
                reasons = []
                if semantic_files:
                    reasons.append(
                        f"{len(semantic_files)} doc/paper/image file(s) need semantic extraction"
                    )
                if dedup_llm:
                    reasons.append("--dedup-llm was passed")
                hint = ""
                if semantic_files:
                    hint = (" Or pass --code-only to index just the code "
                            "(local AST, no key) and skip the non-code files.")
                print(
                    "error: no LLM API key found (" + "; ".join(reasons) + "). "
                    "Set GEMINI_API_KEY or GOOGLE_API_KEY (gemini), MOONSHOT_API_KEY "
                    "(kimi), ANTHROPIC_API_KEY (claude), OPENAI_API_KEY (openai), "
                    "DEEPSEEK_API_KEY (deepseek), or pass --backend. A code-only "
                    "corpus needs no key." + hint,
                    file=sys.stderr,
                )
                sys.exit(1)
            if backend == "ollama":
                from graphify.llm import _validate_ollama_base_url
                _oll_url = os.environ.get("OLLAMA_BASE_URL", _BACKENDS["ollama"].get("base_url", ""))
                try:
                    _validate_ollama_base_url(_oll_url, warn=False)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    sys.exit(2)
            if not _get_backend_api_key(backend):
                allow_no_key = False
                if backend == "ollama":
                    from urllib.parse import urlparse
                    ollama_url = os.environ.get(
                        "OLLAMA_BASE_URL",
                        _BACKENDS["ollama"].get("base_url", ""),
                    )
                    try:
                        host = (urlparse(ollama_url).hostname or "").lower()
                    except Exception:
                        host = ""
                    allow_no_key = (
                        host in ("localhost", "127.0.0.1", "::1")
                        or host.startswith("127.")
                    )
                elif backend == "bedrock":
                    allow_no_key = bool(
                        os.environ.get("AWS_PROFILE")
                        or os.environ.get("AWS_REGION")
                        or os.environ.get("AWS_DEFAULT_REGION")
                        or os.environ.get("AWS_ACCESS_KEY_ID")
                    )
                elif backend == "claude-cli":
                    import shutil as _shutil
                    allow_no_key = _shutil.which("claude") is not None
                    if not allow_no_key:
                        print(
                            "error: backend 'claude-cli' requires the `claude` CLI on $PATH "
                            "(install Claude Code and run `claude` once to authenticate).",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                if not allow_no_key:
                    print(
                        f"error: backend '{backend}' requires {_format_backend_env_keys(backend)} to be set.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

        # AST extraction on code files. Empty code list (docs-only corpus) is
        # the issue #698 case — skip cleanly instead of crashing inside extract().
        ast_result: dict = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        if code_files:
            from graphify.extract import extract as _ast_extract
            # Anchor the cache at the output root, not the scanned project:
            # with --out, a <target>/graphify-out/cache/ would leak a
            # graphify-out/ dir into a project that asked for external output.
            ast_kwargs: dict = {"cache_root": out_root}
            if cli_max_workers is not None:
                ast_kwargs["max_workers"] = cli_max_workers
            print(f"[graphify extract] AST extraction on {len(code_files)} code files...")
            try:
                ast_result = _ast_extract(code_files, **ast_kwargs)
            except Exception as exc:
                print(f"[graphify extract] AST extraction failed: {exc}", file=sys.stderr)
                ast_result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
        stages.mark("AST extract")

        # Semantic extraction on docs/papers/images. Check cache first.
        from graphify.cache import (
            check_semantic_cache as _check_semantic_cache,
            prune_semantic_cache as _prune_semantic_cache,
            save_semantic_cache as _save_semantic_cache,
        )
        sem_result: dict = {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0,
        }
        sem_cache_hits = 0
        sem_cache_misses = 0
        if semantic_files:
            sem_paths_str = [str(p) for p in semantic_files]
            cached_nodes, cached_edges, cached_hyperedges, uncached_paths = (
                _check_semantic_cache(sem_paths_str, root=out_root)
            )
            sem_cache_hits = len(semantic_files) - len(uncached_paths)
            sem_cache_misses = len(uncached_paths)
            sem_result["nodes"].extend(cached_nodes)
            sem_result["edges"].extend(cached_edges)
            sem_result["hyperedges"].extend(cached_hyperedges)
            if sem_cache_hits:
                print(f"[graphify extract] semantic cache: {sem_cache_hits} hit / {sem_cache_misses} miss")

            if uncached_paths:
                print(f"[graphify extract] semantic extraction on {len(uncached_paths)} files via {backend}...")
                corpus_kwargs: dict = {
                    "backend": backend,
                    "model": model,
                    "root": target,
                }
                if deep_mode:
                    corpus_kwargs["deep_mode"] = True
                if cli_token_budget is not None:
                    corpus_kwargs["token_budget"] = cli_token_budget
                if cli_max_concurrency is not None:
                    corpus_kwargs["max_concurrency"] = cli_max_concurrency

                # Minimal progress callback so the CLI is no longer silent
                # during long local-inference runs (issue #792 addendum).
                # Also track per-chunk success so we can fail loudly when
                # every chunk errors (e.g. missing backend SDK package).
                _chunk_stats = {"total": 0, "succeeded": 0}
                def _progress(idx: int, total: int, _result: dict) -> None:
                    _chunk_stats["total"] = total
                    _chunk_stats["succeeded"] += 1
                    print(
                        f"[graphify extract] chunk {idx + 1}/{total} done",
                        flush=True,
                    )
                corpus_kwargs["on_chunk_done"] = _progress

                try:
                    fresh = _extract_corpus_parallel(
                        [Path(p) for p in uncached_paths],
                        **corpus_kwargs,
                    )
                except ImportError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    sys.exit(1)
                except Exception as exc:
                    print(
                        f"[graphify extract] semantic extraction failed: {exc}",
                        file=sys.stderr,
                    )
                    fresh = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

                # on_chunk_done only fires after a chunk succeeds. If fresh
                # semantic extraction was requested and no chunks completed,
                # fail instead of writing an AST-only graph with exit 0.
                if uncached_paths and _chunk_stats["succeeded"] == 0:
                    print(
                        f"[graphify extract] error: all semantic chunks failed "
                        f"for backend '{backend}' ({len(uncached_paths)} uncached files) - "
                        f"see per-chunk errors above. If you see 'requires the X package', "
                        f"run `pip install X` and retry.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                try:
                    _save_semantic_cache(
                        fresh.get("nodes", []),
                        fresh.get("edges", []),
                        fresh.get("hyperedges", []),
                        root=out_root,
                        allowed_source_files=uncached_paths,
                    )
                except Exception as exc:
                    print(f"[graphify extract] warning: could not write semantic cache: {exc}", file=sys.stderr)
                sem_result["nodes"].extend(fresh.get("nodes", []))
                sem_result["edges"].extend(fresh.get("edges", []))
                sem_result["hyperedges"].extend(fresh.get("hyperedges", []))
                sem_result["input_tokens"] += fresh.get("input_tokens", 0)
                sem_result["output_tokens"] += fresh.get("output_tokens", 0)

        # Prune orphaned semantic cache entries. The semantic cache is
        # content-hash-keyed and unversioned, so it is never swept by the AST
        # version-cleanup: every content change or file deletion leaves a
        # permanent orphan that accumulates unbounded (#1527). Sweep it against
        # the FULL live document set (``files_by_type`` — present in both the
        # incremental and full branches), NOT the incremental ``semantic_files``
        # changed-subset, which would delete every unchanged doc's valid entry.
        # Best-effort: a prune failure must never break extraction.
        try:
            from graphify.cache import file_hash as _file_hash
            _live_hashes: set[str] = set()
            for _kind in ("document", "paper", "image"):
                for _fp in files_by_type.get(_kind, []):
                    _abs = Path(_fp)
                    if not _abs.is_absolute():
                        _abs = Path(out_root) / _abs
                    if not _abs.is_file():
                        continue  # deleted/missing — leave out so its entry is pruned
                    try:
                        _live_hashes.add(_file_hash(_abs, out_root))
                    except OSError:
                        pass
            _prune_semantic_cache(out_root, _live_hashes)
        except Exception as exc:
            print(f"[graphify extract] warning: could not prune semantic cache: {exc}", file=sys.stderr)
        stages.mark("semantic extract")

        pg_result: dict = {"nodes": [], "edges": []}
        if cli_postgres_dsn is not None:
            from graphify.pg_introspect import introspect_postgres
            print(f"[graphify extract] introspecting PostgreSQL schema...")
            try:
                pg_result = introspect_postgres(cli_postgres_dsn)
            except (ConnectionError, ImportError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"[graphify extract] PostgreSQL: {len(pg_result['nodes'])} nodes, "
                  f"{len(pg_result['edges'])} edges")

        cargo_result: dict = {"nodes": [], "edges": []}
        if cli_cargo:
            from graphify.cargo_introspect import introspect_cargo
            print("[graphify extract] introspecting Cargo workspace...")
            try:
                cargo_result = introspect_cargo(target)
            except (ConnectionError, ImportError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"[graphify extract] Cargo: {len(cargo_result['nodes'])} nodes, "
                  f"{len(cargo_result['edges'])} edges")

        # Merge AST + semantic + pg_result + cargo_result. Order matters for deduplication: passing AST
        # first means semantic node attributes win on collision (richer labels
        # for symbols also referenced in docs). Hyperedges only come from the
        # semantic side.
        merged: dict = {
            "nodes": list(ast_result.get("nodes", [])) + list(sem_result.get("nodes", [])) + list(pg_result.get("nodes", [])) + list(cargo_result.get("nodes", [])),
            "edges": list(ast_result.get("edges", [])) + list(sem_result.get("edges", [])) + list(pg_result.get("edges", [])) + list(cargo_result.get("edges", [])),
            "hyperedges": list(sem_result.get("hyperedges", [])),
            "input_tokens": ast_result.get("input_tokens", 0) + sem_result.get("input_tokens", 0),
            "output_tokens": ast_result.get("output_tokens", 0) + sem_result.get("output_tokens", 0),
        }

        graph_json_path = graphify_out / "graph.json"
        analysis_path = graphify_out / ".graphify_analysis.json"

        # Build a manifest-safe files dict: only stamp semantic_hash for files
        # that actually produced output (cache hit or fresh extraction). Files
        # whose chunk failed have no source_file entry in sem_result — leaving
        # their semantic_hash empty so detect_incremental re-queues them (#933).
        # Path normalization against the scan root happens inside the helper
        # (#1897) so fresh root-relative source_files match detect()'s
        # absolute file lists.
        _manifest_files = _stamped_manifest_files(files_by_type, sem_result, target)

        if no_cluster:
            # --no-cluster: dump the raw merged extraction as graph.json.
            # No NetworkX, no community detection, no analysis sidecar.
            # Dedupe nodes (by id) and parallel edges so the raw output matches the
            # clustered path (whose DiGraph collapses both) and stays deterministic
            # across modes (#1317; node dedup also collapses shared Swift module
            # anchors emitted per importing file, #1327).
            from graphify.build import dedupe_edges as _dedupe_edges, dedupe_nodes as _dedupe_nodes
            from graphify.export import backup_if_protected as _backup
            if (
                incremental_mode
                and not code_files
                and not semantic_files
                and not deleted_files
                and not pg_result.get("nodes")
                and not pg_result.get("edges")
                and not cargo_result.get("nodes")
                and not cargo_result.get("edges")
            ):
                print(
                    "[graphify extract] no incremental changes detected "
                    "(--no-cluster); outputs left untouched."
                )
                try:
                    _save_manifest(_manifest_files, manifest_path=str(manifest_path), kind="both", root=target)
                except Exception as exc:
                    print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)
                stages.total()
                sys.exit(0)

            merged["nodes"] = _dedupe_nodes(merged["nodes"])
            merged["edges"] = _dedupe_edges(merged["edges"])
            # Backfill source_file from endpoint nodes — this raw path bypasses
            # build_from_json's backfill, and semantic edges sometimes omit it (#1279).
            _node_sf = {n.get("id"): n.get("source_file") for n in merged["nodes"]}
            for _e in merged["edges"]:
                if not _e.get("source_file"):
                    _e["source_file"] = (
                        _node_sf.get(_e.get("source")) or _node_sf.get(_e.get("target")) or ""
                    )
            _backup(graphify_out)
            graph_json_path.write_text(
                json.dumps(merged, indent=2), encoding="utf-8"
            )
            stages.mark("write")
            cost = _estimate_cost(
                backend, merged["input_tokens"], merged["output_tokens"]
            )
            print(
                f"[graphify extract] wrote {graph_json_path} — "
                f"{len(merged['nodes'])} nodes, {len(merged['edges'])} edges "
                f"(no clustering)"
            )
            if merged["input_tokens"] or merged["output_tokens"]:
                print(
                    f"[graphify extract] tokens: "
                    f"{merged['input_tokens']:,} in / "
                    f"{merged['output_tokens']:,} out, "
                    f"est. cost: ${cost:.4f}"
                )
            try:
                _save_manifest(_manifest_files, manifest_path=str(manifest_path), kind="both", root=target)
            except Exception as exc:
                print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)
            if global_merge:
                from graphify.global_graph import global_add as _global_add
                _tag = global_repo_tag or target.name
                try:
                    result = _global_add(graphify_out / "graph.json", _tag)
                    if result["skipped"]:
                        print(f"[graphify global] '{_tag}' unchanged since last add - skipped.")
                    else:
                        print(f"[graphify global] '{_tag}' merged into global graph "
                              f"(+{result['nodes_added']} nodes, -{result['nodes_removed']} pruned).")
                except Exception as exc:
                    print(f"[graphify global] warning: failed to merge into global graph: {exc}", file=sys.stderr)
            stages.total()
            sys.exit(0)

        # Build graph + cluster + score + write.
        from graphify.build import (
            build as _build,
            build_from_json as _build_from_json,
            build_merge as _build_merge,
        )
        from graphify.cluster import cluster as _cluster, score_all as _score_all
        from graphify.export import to_json as _to_json
        from graphify.analyze import god_nodes as _god_nodes, surprising_connections as _surprising
        dedup_backend = backend if dedup_llm else None
        if incremental_mode:
            G = _build_merge(
                [merged],
                graph_path=existing_graph_path,
                prune_sources=deleted_files or None,
                dedup=True,
                dedup_llm_backend=dedup_backend,
                root=target,
            )
        else:
            G = _build([merged], dedup=True, dedup_llm_backend=dedup_backend, root=target)
        stages.mark("build")
        if G.number_of_nodes() == 0:
            print(
                "[graphify extract] graph is empty — extraction produced no nodes. "
                "Possible causes: all files skipped, binary-only corpus, or LLM "
                "returned no edges.",
                file=sys.stderr,
            )
            sys.exit(1)

        communities = _cluster(G, resolution=cli_resolution, exclude_hubs_percentile=cli_exclude_hubs)
        stages.mark("cluster")
        cohesion = _score_all(G, communities)
        try:
            gods = _god_nodes(G)
        except Exception:
            gods = []
        try:
            surprises = _surprising(G, communities)
        except Exception:
            surprises = []
        stages.mark("analyze")

        from graphify.export import backup_if_protected as _backup
        _backup(graphify_out)
        _to_json(G, communities, str(graph_json_path), force=True)
        stages.mark("export")
        if merged.get("output_tokens", 0) > 0:
            (graphify_out / ".graphify_semantic_marker").write_text(
                json.dumps({"output_tokens": merged["output_tokens"]}), encoding="utf-8"
            )
        if global_merge:
            from graphify.global_graph import global_add as _global_add
            _tag = global_repo_tag or target.name
            try:
                result = _global_add(graphify_out / "graph.json", _tag)
                if result["skipped"]:
                    print(f"[graphify global] '{_tag}' unchanged since last add - skipped.")
                else:
                    print(f"[graphify global] '{_tag}' merged into global graph "
                          f"(+{result['nodes_added']} nodes, -{result['nodes_removed']} pruned).")
            except Exception as exc:
                print(f"[graphify global] warning: failed to merge into global graph: {exc}", file=sys.stderr)
        analysis = {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "tokens": {
                "input": merged["input_tokens"],
                "output": merged["output_tokens"],
            },
        }
        analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        try:
            _save_manifest(_manifest_files, manifest_path=str(manifest_path), kind="both", root=target)
        except Exception as exc:
            print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)

        cost = _estimate_cost(backend, merged["input_tokens"], merged["output_tokens"])
        print(
            f"[graphify extract] wrote {graph_json_path}: "
            f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
            f"{len(communities)} communities"
        )
        print(f"[graphify extract] wrote {analysis_path}")
        if incremental_mode:
            print(
                f"[graphify extract] incremental summary: "
                f"{sem_cache_hits + unchanged_total} files cached/unchanged, "
                f"{len(code_files) + sem_cache_misses} re-extracted, "
                f"{len(deleted_files)} deleted"
            )
        elif sem_cache_hits:
            print(f"[graphify extract] semantic cache: {sem_cache_hits} cached, {sem_cache_misses} re-extracted")
        if merged["input_tokens"] or merged["output_tokens"]:
            print(
                f"[graphify extract] tokens: "
                f"{merged['input_tokens']:,} in / "
                f"{merged['output_tokens']:,} out, "
                f"est. cost (~{backend}): ${cost:.4f}"
            )
        # extract intentionally stops at graph.json + analysis; the report and
        # community labels are produced by `cluster-only` (or an agent's Step 5).
        # Point standalone users at it so communities get named (#1097).
        print(
            "[graphify extract] next: run "
            f"`graphify cluster-only {graphify_out.parent}` "
            "to generate GRAPH_REPORT.md and name communities"
        )
        stages.total()

    elif cmd == "cache-check":
        # graphify cache-check <files_from> [--root <dir>]
        # Reads file paths (one per line) from <files_from>, checks semantic cache.
        # Writes:
        #   graphify-out/.graphify_cached.json   — already-cached nodes/edges/hyperedges
        #   graphify-out/.graphify_uncached.txt  — paths that need extraction
        # Stdout: "Cache: N hit, M miss"
        from graphify.cache import check_semantic_cache
        if len(sys.argv) < 3:
            print("Usage: graphify cache-check <files_from> [--root <dir>]", file=sys.stderr)
            sys.exit(1)
        files_from = Path(sys.argv[2])
        root = Path(".")
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--root" and i + 1 < len(sys.argv):
                root = Path(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        files = [f for f in files_from.read_text(encoding="utf-8").splitlines() if f.strip()]
        cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(files, root)
        out = root / _GRAPHIFY_OUT
        out.mkdir(parents=True, exist_ok=True)
        if cached_nodes or cached_edges or cached_hyperedges:
            (out / ".graphify_cached.json").write_text(
                json.dumps({"nodes": cached_nodes, "edges": cached_edges, "hyperedges": cached_hyperedges},
                           ensure_ascii=False),
                encoding="utf-8",
            )
        (out / ".graphify_uncached.txt").write_text("\n".join(uncached), encoding="utf-8")
        print(f"Cache: {len(files) - len(uncached)} hit, {len(uncached)} miss")

    elif cmd == "merge-chunks":
        # graphify merge-chunks <chunk_glob_or_files...> --out <path>
        # Concatenates .graphify_chunk_*.json files written by semantic subagents.
        # Deduplicates nodes by id (first writer wins). Sums token counts.
        import glob as _glob
        if len(sys.argv) < 3:
            print("Usage: graphify merge-chunks <chunk_files...> --out <path>", file=sys.stderr)
            sys.exit(1)
        out_path: Path | None = None
        chunk_args: list[str] = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out_path = Path(sys.argv[i + 1])
                i += 2
            else:
                chunk_args.append(sys.argv[i])
                i += 1
        if not out_path:
            print("error: --out <path> required", file=sys.stderr)
            sys.exit(1)
        chunk_files: list[str] = []
        for arg in chunk_args:
            expanded = _glob.glob(arg)
            chunk_files.extend(sorted(expanded) if expanded else [arg])
        merged: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
        seen_ids: set[str] = set()
        for cf in chunk_files:
            try:
                chunk = json.loads(Path(cf).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[graphify merge-chunks] warning: skipping {cf}: {exc}", file=sys.stderr)
                continue
            for n in chunk.get("nodes", []):
                if n.get("id") not in seen_ids:
                    seen_ids.add(n["id"])
                    merged["nodes"].append(n)
            merged["edges"].extend(chunk.get("edges", []))
            merged["hyperedges"].extend(chunk.get("hyperedges", []))
            merged["input_tokens"] += chunk.get("input_tokens", 0)
            merged["output_tokens"] += chunk.get("output_tokens", 0)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        print(
            f"Merged {len(chunk_files)} chunks: {len(merged['nodes'])} nodes, {len(merged['edges'])} edges, "
            f"{merged['input_tokens']:,} in / {merged['output_tokens']:,} out tokens"
        )

    elif cmd == "merge-semantic":
        # graphify merge-semantic --cached <path> --new <path> --out <path>
        # Merges cached semantic results with freshly-extracted chunk results.
        # Deduplicates nodes by id (cached entries take priority over new ones).
        if len(sys.argv) < 3:
            print("Usage: graphify merge-semantic --cached <path> --new <path> --out <path>", file=sys.stderr)
            sys.exit(1)
        cached_path: Path | None = None
        new_path: Path | None = None
        out_path2: Path | None = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--cached" and i + 1 < len(sys.argv):
                cached_path = Path(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--new" and i + 1 < len(sys.argv):
                new_path = Path(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
                out_path2 = Path(sys.argv[i + 1]); i += 2
            else:
                i += 1
        if not out_path2:
            print("error: --out <path> required", file=sys.stderr)
            sys.exit(1)
        empty: dict = {"nodes": [], "edges": [], "hyperedges": []}
        cached_data = json.loads(cached_path.read_text(encoding="utf-8")) if cached_path and cached_path.exists() else empty
        new_data = json.loads(new_path.read_text(encoding="utf-8")) if new_path and new_path.exists() else empty
        seen_ids2: set[str] = set()
        all_nodes: list[dict] = []
        for n in cached_data.get("nodes", []) + new_data.get("nodes", []):
            if n.get("id") not in seen_ids2:
                seen_ids2.add(n["id"])
                all_nodes.append(n)
        merged2 = {
            "nodes": all_nodes,
            "edges": cached_data.get("edges", []) + new_data.get("edges", []),
            "hyperedges": cached_data.get("hyperedges", []) + new_data.get("hyperedges", []),
        }
        out_path2.parent.mkdir(parents=True, exist_ok=True)
        out_path2.write_text(json.dumps(merged2, ensure_ascii=False), encoding="utf-8")
        print(f"Merged: {len(merged2['nodes'])} nodes, {len(merged2['edges'])} edges")

    elif Path(cmd).exists() or cmd in (".", "..") or cmd.startswith(("./", "../", "/", "~")):
        # User ran `graphify <path>` directly — treat as `graphify extract <path>`.
        # Common when following the PowerShell note in README (`graphify .`) or
        # copy-pasting skill invocations without the leading slash.
        sys.argv.insert(2, sys.argv[1])
        sys.argv[1] = "extract"
        _reenter_main()
    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'graphify --help' for usage.", file=sys.stderr)
        sys.exit(1)
