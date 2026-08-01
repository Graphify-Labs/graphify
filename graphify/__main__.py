"""graphify CLI - `graphify install` sets up the Claude Code skill."""

from __future__ import annotations
import errno
import functools
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"

# Output directory — override with GRAPHIFY_OUT env var for worktrees or shared-output setups.
# Accepts a relative name ("graphify-out-feature") or an absolute path ("/shared/graphify-out").
# Defined once in graphify.paths so the security/callflow path guards honour the
# same override (#1423).
from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT

# Install/uninstall subsystem moved to graphify/install.py; re-exported here so
# `from graphify.__main__ import <name>` keeps working unchanged.
from graphify.install import (  # noqa: E402,F401
    dispatch_install_cli,
    _agents_install,
    _agents_platform_install,
    _agents_platform_uninstall,
    _agents_uninstall,
    _always_on,
    _amp_install,
    _amp_legacy_cleanup,
    _amp_uninstall,
    _antigravity_finalize,
    _antigravity_install,
    _antigravity_uninstall,
    _canonical_platform,
    _claude_pretooluse_hooks,
    _copy_skill_file,
    _cursor_install,
    _cursor_uninstall,
    _devin_rules_install,
    _devin_rules_uninstall,
    _gemini_hook,
    _install_claude_hook,
    _install_codebuddy_hook,
    _install_codex_hook,
    _install_gemini_hook,
    _install_kilo_plugin,
    _install_opencode_plugin,
    _install_skill_references,
    _kilo_config_path,
    _kilo_config_write_path,
    _kilo_install,
    _kilo_uninstall,
    _kilo_uninstall_global,
    _kiro_install,
    _kiro_uninstall,
    _load_json_like,
    _packaged_skill_refs_dir,
    _platform_skill_destination,
    _print_banner,
    _print_install_usage,
    _print_project_git_add_hint,
    _project_install,
    _project_scope_root,
    _project_uninstall,
    _project_uninstall_all,
    _refresh_all_version_stamps,
    _remove_claude_skill_registration,
    _remove_skill_file,
    _replace_or_append_section,
    _resolve_graphify_exe,
    _skill_registration,
    _strip_graphify_hook,
    _strip_graphify_md_section,
    _strip_json_comments,
    _uninstall_claude_hook,
    _uninstall_codebuddy_hook,
    _uninstall_codex_hook,
    _uninstall_gemini_hook,
    _uninstall_kilo_plugin,
    _uninstall_opencode_plugin,
    claude_install,
    claude_uninstall,
    codebuddy_install,
    codebuddy_uninstall,
    gemini_install,
    gemini_uninstall,
    install,
    uninstall_all,
    vscode_install,
    vscode_uninstall,
    _PLATFORM_ALIASES,
    _CLAUDE_MD_MARKER,
    _CODEBUDDY_MD_MARKER,
    _AGENTS_MD_MARKER,
    _GEMINI_MD_MARKER,
    _VSCODE_INSTRUCTIONS_MARKER,
    _ANTIGRAVITY_RULES_PATH,
    _ANTIGRAVITY_WORKFLOW_PATH,
    _ANTIGRAVITY_WORKFLOW,
    _CURSOR_RULE_PATH,
    _CURSOR_RULE,
    _DEVIN_RULES_PATH,
    _DEVIN_RULES,
    _KILO_PLUGIN_JS,
    _KILO_PLUGIN_PATH,
    _KILO_CONFIG_JSON_PATH,
    _KILO_CONFIG_JSONC_PATH,
    _OPENCODE_PLUGIN_JS,
    _OPENCODE_PLUGIN_PATH,
    _OPENCODE_CONFIG_PATH,
    _PLATFORM_CONFIG,
)
from graphify.cli import (  # noqa: E402,F401
    dispatch_command,
    _StageTimer,
    _clone_repo,
    _default_graph_path,
    _enforce_graph_size_cap_or_exit,
    _run_hook_guard,
    _SEARCH_NUDGE,
    _READ_NUDGE,
    _HOOK_SOURCE_EXTS,
    _GEMINI_NUDGE_TEXT,
)




_ALWAYS_ON_ALIASES = {
    "_CLAUDE_MD_SECTION": "claude-md",
    "_AGENTS_MD_SECTION": "agents-md",
    "_GEMINI_MD_SECTION": "gemini-md",
    "_VSCODE_INSTRUCTIONS_SECTION": "vscode-instructions",
    "_ANTIGRAVITY_RULES": "antigravity-rules",
    "_KIRO_STEERING": "kiro-steering",
}


def __getattr__(name: str) -> str:
    # PEP 562: lazily resolve the legacy always-on section constants for external
    # importers (e.g. the install-string tests). In-module code calls _always_on()
    # directly; nothing is read at import time, so a missing block can no longer
    # brick the CLI on `import graphify.__main__` (#1121 follow-up).
    base = _ALWAYS_ON_ALIASES.get(name)
    if base is not None:
        return _always_on(base)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")








def _check_skill_version(skill_dst: Path) -> None:
    """Warn if the installed skill is from an older graphify version."""
    version_file = skill_dst.parent / ".graphify_version"
    try:
        if not version_file.exists():
            return
    except OSError:
        return
    try:
        skill_exists = skill_dst.exists()
    except OSError:
        return
    if not skill_exists:
        print("  warning: skill dir exists but SKILL.md is missing. Run 'graphify install' to repair.", file=sys.stderr)
        return
    # A progressive SKILL.md links to its references/ sidecar. If the body points
    # at references/ but the dir is gone (manual delete, partial upgrade), the
    # on-demand fragments won't load — flag it for repair.
    try:
        body = skill_dst.read_text(encoding="utf-8")
    except OSError:
        body = ""
    if "references/" in body and not (skill_dst.parent / "references").exists():
        print("  warning: skill references/ sidecar is missing. Run 'graphify install' to repair.", file=sys.stderr)
    try:
        installed = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if installed != __version__:
        if _version_tuple(installed) > _version_tuple(__version__):
            # The skill on disk is NEWER than the running package. `graphify install`
            # writes the package's OWN (older) bundled skill and re-stamps the version,
            # so following the old "run install" advice would silently DOWNGRADE the
            # skill. The real fix is to upgrade the package (#1568). Common for a stale
            # `uv tool` CLI, or a contributor whose dev checkout stamped a newer skill.
            print(
                f"  warning: skill is from graphify {installed}, but the package is "
                f"{__version__} (older). Upgrade the package "
                f"(e.g. 'uv tool upgrade graphifyy' or 'pip install -U graphifyy'); "
                f"running 'graphify install' would downgrade the skill.",
                file=sys.stderr,
            )
        else:
            print(f"  warning: skill is from graphify {installed}, package is {__version__}. Run 'graphify install' to update.", file=sys.stderr)


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a version string into a comparable integer tuple (``0.9.2`` -> ``(0, 9, 2)``).

    Reads the leading digits of each dot-segment, so pre/post-release suffixes
    (``1.0.0rc1``) compare by their numeric core. A non-numeric or empty segment
    becomes 0, so a malformed stamp degrades to a conservative comparison rather
    than raising.
    """
    parts: list[int] = []
    for segment in str(version).split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)



















# PreToolUse nudge payloads, emitted verbatim by the shell-agnostic
# `graphify hook-guard` subcommand (see _run_hook_guard). The previous hooks
# inlined POSIX bash (case/esac, [ -f ], single-quoted echo) which Windows
# cmd.exe/PowerShell cannot parse, so on Windows the hook failed and the nudge
# silently vanished — users had to invoke /graphify by hand (#522). Moving the
# logic into a Python subcommand invoked via an absolute exe path makes the hook
# parse identically under sh, cmd.exe and PowerShell. Claude Code accepts
# additionalContext on PreToolUse (Codex Desktop does not — that path stays a
# no-op via `hook-check`). Compact separators keep the payload byte-for-byte the
# same JSON the old `echo` emitted.


# Source/doc extensions the Read|Glob guard nudges on (verbatim from the old hook).
# The trailing-extension test (real final path segment, then its last '.') means
# '.json' never false-matches '.js', and framework files like '.astro' are kept.


















# The always-on instruction blocks are packaged markdown under graphify/always_on/,
# generated by tools/skillgen and guarded by `skillgen --check`. Reading them at
# load keeps the install-string / issue-#580 contract byte-for-byte while letting
# a human edit one fragment instead of a triple-quoted literal here.



# AGENTS.md section for Codex, OpenCode, and OpenClaw.
# All three platforms read AGENTS.md in the project root for persistent instructions.




# Gemini CLI BeforeTool hook nudge text. The hook always returns
# {"decision":"allow"} (never blocks a tool) and appends this as additionalContext
# when a graph exists. Emitted by `graphify hook-guard gemini`. The old hook was a
# `python -c "..."` one-liner that depended on a bare `python` on PATH (often
# `python`/`py` or absent on Windows) and embedded backticks + escaped quotes that
# Windows PowerShell mangles (#522 follow-up); the subcommand form has no such
# dependency and parses under every shell.























_KIRO_STEERING_MARKER = "graphify: A knowledge graph of this project"














































_CODEX_HOOK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        # Use the graphify CLI itself so the hook is shell-agnostic:
                        # no [ -f ] bash syntax, no python3 vs python Conda issue,
                        # no JSON escaping inside PowerShell strings. Works on
                        # Windows (PowerShell/cmd.exe), macOS, and Linux.
                        "command": "graphify hook-check",
                    }
                ],
            }
        ]
    }
}



























































def _silence_broken_pipe() -> None:
    """Handle a downstream reader that closed the pipe early. Redirect stdout to
    devnull so the interpreter's shutdown flush does not raise a second time, then
    exit 0 — the reader (head, `Select-Object -First N`, `sed q`) has what it needs."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception:
        pass
    sys.exit(0)


def main() -> None:
    """Console entry point. Wraps the CLI so that when a downstream consumer closes
    stdout early, graphify treats it as success instead of crashing with an
    unhandled write-to-closed-pipe error and exit 255 — which made CI wrappers and
    agent harnesses read a successful query as a command failure (#1807)."""
    try:
        _run_cli()
        # Flush explicitly, inside the guard. Piped stdout is block-buffered, so a
        # small fully-buffered output would otherwise only flush at interpreter
        # shutdown — outside this try — where a reader that closed the pipe surfaces
        # as a noisy "Exception ignored on flushing sys.stdout" and a nonzero exit.
        sys.stdout.flush()
    except BrokenPipeError:
        _silence_broken_pipe()
    except OSError as exc:
        # Windows surfaces a write to a closed pipe as OSError(EINVAL) rather than
        # BrokenPipeError; EPIPE is the POSIX form when it slips past the above.
        if getattr(exc, "errno", None) in (errno.EPIPE, errno.EINVAL):
            _silence_broken_pipe()
        else:
            raise


def _run_cli() -> None:
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    # Check all known skill install locations for a stale version stamp.
    # Skip during install/uninstall (hook writes trigger a fresh check anyway).
    # Skip during hook-check — it runs on every editor tool use and must be silent.
    # Deduplicate paths so platforms sharing the same install dir don't warn twice.
    _silent_cmds = {"install", "uninstall", "hook-check", "hook-guard"}
    if not any(arg in _silent_cmds for arg in sys.argv):
        # Resolve each platform's real user-scope destination so per-platform
        # overrides (gemini, opencode, devin, antigravity, amp) check the dir
        # they actually install into, not the bare cfg['skill_dst'].
        for skill_dst in {_platform_skill_destination(name) for name in _PLATFORM_CONFIG}:
            _check_skill_version(skill_dst)

    if len(sys.argv) >= 2 and sys.argv[1] in ("-v", "--version", "version"):
        print(f"graphify {__version__}")
        return

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "-?"):
        print("Usage: graphify <command>")
        print()
        print("Commands:")
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codebuddy|codex|opencode|aider|amp|agents|claw|droid|trae|trae-cn|gemini|cursor|antigravity|hermes|kiro|pi|devin)")
        print("  uninstall               remove graphify from all detected platforms in one shot")
        print("    --purge                 also delete graphify-out/ directory")
        print("  path \"A\" \"B\"            shortest path between two nodes in graph.json")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  explain \"X\"             plain-language explanation of a node and its neighbors")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  diagnose multigraph    report same-endpoint edge collapse risk in graph.json")
        print("    --graph <path>          path to graph/extraction JSON")
        print("                            (default graphify-out/graph.json)")
        print("    --json                  emit machine-readable JSON")
        print("    --max-examples N        max same-endpoint examples to print (default 5)")
        print("    --directed              force directed post-build simulation")
        print("    --undirected            force undirected post-build simulation")
        print("                            (default follows JSON directed flag;")
        print("                             raw extraction with no flag defaults directed)")
        print("    --extract-path PATH     extractor source for suppression scan")
        print("  clone <github-url>      clone a GitHub repo locally and print its path for /graphify")
        print("  merge-driver <base> <current> <other>  git merge driver: union-merge two graph.json files (set up via hook install)")
        print("  merge-graphs <g1> <g2>  merge two or more graph.json files into one cross-repo graph")
        print("    --out <path>            output path (default: graphify-out/merged-graph.json)")
        print("    --branch <branch>       checkout a specific branch (default: repo default)")
        print("    --out <dir>             clone to a custom directory (default: ~/.graphify/repos/<owner>/<repo>)")
        print("  add <url>               fetch a URL and save it to ./raw, then update the graph")
        print("    --author \"Name\"         tag the author of the content")
        print("    --contributor \"Name\"    tag who added it to the corpus")
        print("    --dir <path>            target directory (default: ./raw)")
        print("  watch <path>            watch a folder and rebuild the graph on code changes")
        print("  update <path>           re-extract code files and update the graph (no LLM needed)")
        print("    --force                 overwrite graph.json even if the rebuild has fewer nodes")
        print("                            (also: GRAPHIFY_FORCE=1 env var; use after refactors that delete code)")
        print("    --no-cluster            skip clustering, write raw extraction only")
        print("  cluster-only <path>     rerun clustering on an existing graph.json and regenerate report")
        print("    --no-viz                skip graph.html generation (useful for >5000 node graphs / CI)")
        print("    --graph <path>          path to graph.json (default <path>/graphify-out/graph.json)")
        print("    --no-label              keep 'Community N' placeholders (skip LLM community naming)")
        print("    --backend=<name>        backend to use for community naming (default: auto-detect)")
        print("    --model=<name>          model to use for community naming")
        print("    --max-concurrency=N     parallel community-labeling LLM calls (default 4; forced to 1 for ollama/claude-cli)")
        print("    --batch-size=N          communities per labeling LLM call (default 100)")
        print("  label <path>            (re)name communities with the configured LLM backend, regenerate report")
        print("    --missing-only         keep existing labels and only name missing/placeholder communities")
        print("    --backend=<name>        backend to use (default: auto-detect from API keys)")
        print("    --model=<name>          model to use for community naming")
        print("    --max-concurrency=N     parallel labeling LLM calls (default 4; forced to 1 for ollama/claude-cli)")
        print("    --batch-size=N          communities per labeling LLM call (default 100)")
        print("  query \"<question>\"       BFS traversal of graph.json for a question")
        print("    --dfs                   use depth-first instead of breadth-first")
        print("    --context C             explicit edge-context filter (repeatable)")
        print("    --budget N              cap output at N tokens (default 2000)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  affected \"X\"             reverse traversal to find nodes impacted by X")
        print("    --relation R            edge relation to traverse in reverse (repeatable)")
        print("    --depth N               reverse traversal depth (default 2)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  god-nodes               list the most connected nodes (architectural hubs)")
        print("    --top N                 how many to show (default 10)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("    --json                  emit JSON instead of text")
        print("  save-result             save a Q&A result to graphify-out/memory/ for graph feedback loop")
        print("    --question Q            the question asked")
        print("    --answer A              the answer to save")
        print(
            "    --type T                query type: query|path_query|explain (default: query)"
        )
        print("    --nodes N1 N2 ...       source node labels cited in the answer")
        print("    --outcome O             work-memory signal: useful|dead_end|corrected")
        print("    --correction TEXT       what the right answer was (pairs with --outcome corrected)")
        print("    --memory-dir DIR        memory directory (default: graphify-out/memory)")
        print("  reflect                 aggregate graphify-out/memory/ outcomes into a deterministic lessons doc")
        print("    --memory-dir DIR        memory directory (default: graphify-out/memory)")
        print("    --out FILE              output path (default: graphify-out/reflections/LESSONS.md)")
        print("    --graph PATH            graph.json, for community grouping + dropping stale nodes (optional)")
        print("    --analysis PATH         .graphify_analysis.json (optional, auto-detected next to --graph)")
        print("    --labels PATH           .graphify_labels.json (optional, auto-detected next to --graph)")
        print("    --half-life-days N      signal weight halves every N days (default 30)")
        print("    --min-corroboration N   distinct useful results to prefer a node (default 2)")
        print("  check-update <path>     check needs_update flag and notify if semantic re-extraction is pending (cron-safe)")
        print("  tree                    emit a D3 v7 collapsible-tree HTML for graph.json")
        print("    --graph PATH            path to graph.json (default graphify-out/graph.json)")
        print("    --output HTML           output path (default graphify-out/GRAPH_TREE.html)")
        print("    --root PATH             filesystem root for the hierarchy")
        print("    --max-children N        cap children per node (default 200)")
        print("    --top-k-edges N         per-symbol outbound edges in inspector (default 12)")
        print("    --label NAME            project label in header")
        print("  extract <path>          headless full extraction (AST + semantic LLM) for CI/scripts")
        print("    --backend B             gemini|kimi|claude|openai|deepseek|ollama (default: whichever API key is set)")
        print("                            openai also reaches self-hosted OpenAI-compatible servers (llama.cpp,")
        print("                            vLLM, LM Studio): set OPENAI_BASE_URL (e.g. http://localhost:8080/v1)")
        print("                            and OPENAI_MODEL to the model name your server serves")
        print("                            claude also reaches custom Anthropic-compatible endpoints (LiteLLM")
        print("                            proxy, gateways): set ANTHROPIC_BASE_URL and ANTHROPIC_MODEL")
        print("    --model M               override backend default model")
        print("    --mode deep             aggressive INFERRED-edge semantic extraction")
        print("    --force                 full re-scan and re-dispatch: skip the incremental")
        print("                            manifest gate and semantic cache reads (env: GRAPHIFY_FORCE=1)")
        print("    --max-workers N         AST extraction subprocess count (default: cpu_count)")
        print("    --token-budget N        per-chunk token cap for semantic extraction (default: 60000)")
        print("    --max-concurrency N     parallel semantic chunks in flight (default: 4; set 1 for local LLMs)")
        print("    --api-timeout S         per-request timeout in seconds for the LLM client (default: 600)")
        print("    --out DIR, --output DIR output dir (default: <path>); writes <DIR>/graphify-out/")
        print("    --google-workspace      export .gdoc/.gsheet/.gslides shortcuts via gws before extraction")
        print("    --no-gitignore         ignore .gitignore and .git/info/exclude (prioritizes .graphifyignore)")
        print("    --no-cluster            skip clustering, write raw extraction only")
        print("    --code-only             index code (local AST, no API key) and skip doc/paper/image files")
        print("    --postgres DSN          extract schema from a live PostgreSQL database")
        print("                            maps tables, views, functions + FK relationships;")
        print("                            column-level detail is not represented in the graph")
        print("    --cargo                 extract crate→crate deps from Cargo.toml")
        print("    --global                also merge the resulting graph into the global graph")
        print("    --as <tag>              repo tag for --global (default: target directory name)")
        print("  global add <graph.json>  add/update a project graph in the global graph (~/.graphify/global-graph.json)")
        print("    --as <tag>               repo tag (default: parent directory name)")
        print("  global remove <tag>      remove a repo's nodes from the global graph")
        print("  global list              list repos in the global graph")
        print("  global path              print path to the global graph file")
        print("  benchmark [graph.json]  measure token reduction vs naive full-corpus approach")
        print("  export callflow-html    emit Mermaid-based architecture/call-flow HTML")
        print("  hook install            install post-commit/post-checkout git hooks (all platforms)")
        print("  hook uninstall          remove git hooks")
        print("  hook status             check if git hooks are installed")
        print(
            "  gemini install          write GEMINI.md section + BeforeTool hook (Gemini CLI)"
        )
        print("  gemini uninstall        remove GEMINI.md section + BeforeTool hook")
        print("  cursor install          write .cursor/rules/graphify.mdc (Cursor)")
        print("  cursor uninstall        remove .cursor/rules/graphify.mdc")
        print("  claude install          write graphify section to CLAUDE.md + PreToolUse hook (Claude Code)")
        print("  claude uninstall        remove graphify section from CLAUDE.md + PreToolUse hook")
        print("  codebuddy install       write graphify section to CODEBUDDY.md + PreToolUse hook (CodeBuddy)")
        print("  codebuddy uninstall     remove graphify section from CODEBUDDY.md + PreToolUse hook")
        print("  codex install           write graphify section to AGENTS.md (Codex)")
        print("  codex uninstall         remove graphify section from AGENTS.md")
        print(
            "  opencode install        write graphify section to AGENTS.md + tool.execute.before plugin (OpenCode)"
        )
        print(
            "  opencode uninstall      remove graphify section from AGENTS.md + plugin"
        )
        print(
            "  kilo install            install native Kilo skill + command + AGENTS.md + .kilo plugin"
        )
        print(
            "  kilo uninstall          remove native Kilo skill + command + AGENTS.md + .kilo plugin"
        )
        print("  aider install           write graphify section to AGENTS.md (Aider)")
        print("  aider uninstall         remove graphify section from AGENTS.md")
        print(
            "  copilot install         copy graphify skill to ~/.copilot/skills (GitHub Copilot CLI)"
        )
        print("  copilot uninstall       remove graphify skill from ~/.copilot/skills")
        print(
            "  vscode install          configure VS Code Copilot Chat (skill + .github/copilot-instructions.md)"
        )
        print("  vscode uninstall        remove VS Code Copilot Chat configuration")
        print(
            "  claw install            write graphify section to AGENTS.md (OpenClaw)"
        )
        print("  claw uninstall          remove graphify section from AGENTS.md")
        print(
            "  droid install           write graphify section to AGENTS.md (Factory Droid)"
        )
        print("  droid uninstall        remove graphify section from AGENTS.md")
        print("  trae install            write graphify section to AGENTS.md (Trae)")
        print("  trae uninstall         remove graphify section from AGENTS.md")
        print("  trae-cn install         write graphify section to AGENTS.md (Trae CN)")
        print("  trae-cn uninstall      remove graphify section from AGENTS.md")
        print(
            "  antigravity install     write .agents/rules + .agents/workflows + skill (Google Antigravity)"
        )
        print(
            "  antigravity uninstall   remove .agents/rules, .agents/workflows, and skill"
        )
        print(
            "  hermes install          write skill to ~/.hermes/skills/graphify/ (Hermes)"
        )
        print("  hermes uninstall        remove skill from ~/.hermes/skills/graphify/")
        print(
            "  kiro install            write skill to .kiro/skills/graphify/ + steering file (Kiro IDE/CLI)"
        )
        print("  kiro uninstall          remove skill + steering file")
        print("  pi install              write skill to ~/.pi/agent/skills/graphify/ (Pi coding agent)")
        print("  pi uninstall            remove skill from ~/.pi/agent/skills/graphify/")
        print("  devin install           write skill to ~/.config/devin/skills/graphify/ (Devin CLI)")
        print("  devin uninstall         remove skill from ~/.config/devin/skills/graphify/")
        print()
        return

    cmd = sys.argv[1]

    # Universal help guard: -h/--help/-? anywhere after the command shows help
    # and stops — prevents flags from silently triggering destructive subcommands
    # (e.g. "cursor install --help" was silently installing into Cursor, #821).
    # Exempt: free-text commands (user string may contain these tokens), and
    # "install"/"uninstall" which have their own per-subcommand help handlers.
    _FREE_TEXT_CMDS = {"query", "explain", "path", "save-result", "install", "uninstall"}
    if cmd not in _FREE_TEXT_CMDS and any(a in {"-h", "--help", "-?"} for a in sys.argv[2:]):
        print(f"Run 'graphify --help' for full usage.")
        return

    if dispatch_install_cli(cmd):
        return
    dispatch_command(cmd)


if __name__ == "__main__":
    main()
