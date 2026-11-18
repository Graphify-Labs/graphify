```bash
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs)
# Every symbol later steps import; `import graphify` alone passes a stale install (#5235).
_GRAPHIFY_PROBE='import importlib, sys
def has(sym):
    mod, _, name = sym.rpartition(".")
    try: return hasattr(importlib.import_module("graphify." + mod), name)
    except ImportError: return False
missing = [s for s in "analyze.god_nodes analyze.graph_diff analyze.suggest_questions analyze.surprising_connections benchmark.print_benchmark benchmark.run_benchmark build.build_from_json build.build_merge cache.check_semantic_cache cache.drop_unreported_chunk_sources cache.save_semantic_cache cli._stamped_manifest_files cluster.cluster cluster.score_all detect.detect detect.detect_incremental detect.save_manifest diagnostics.diagnose_extraction diagnostics.format_diagnostic_report export.push_to_neo4j export.to_canvas export.to_cypher export.to_graphml export.to_html export.to_json export.to_obsidian export.to_svg extract.collect_files extract.extract ingest.ingest paths.load_node_link_graph paths.out_path report.generate semantic_cleanup.load_validated_semantic_fragment semantic_cleanup.sanitize_semantic_fragment transcribe.transcribe_all watch._read_build_excludes watch._read_build_gitignore wiki.to_wiki".split() if not has(s)]
sys.exit("missing: " + ", ".join(missing) if missing else 0)'
PYTHON=""
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
# 1. uv tool installs — most reliable on modern Mac/Linux
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ] && "$_UV_PY" -c "$_GRAPHIFY_PROBE" 2>/dev/null; then PYTHON="$_UV_PY"; fi
fi
# 2. Read shebang from graphify binary (pipx and direct pip installs)
if [ -z "$PYTHON" ] && [ -n "$GRAPHIFY_BIN" ]; then
    _SHEBANG=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$_SHEBANG" in
        *[!a-zA-Z0-9/_.@-]*) ;;
        *) "$_SHEBANG" -c "$_GRAPHIFY_PROBE" 2>/dev/null && PYTHON="$_SHEBANG" ;;
    esac
fi
# 3. Fall back to python3. A PYTHON set above has already passed the probe.
if [ -z "$PYTHON" ]; then
    PYTHON="python3"
    if ! "$PYTHON" -c "$_GRAPHIFY_PROBE" 2>/dev/null; then
        if command -v uv >/dev/null 2>&1; then
            uv tool install --upgrade graphifyy -q 2>&1 | tail -3
            _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
            if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
        else
            "$PYTHON" -m pip install -U graphifyy -q 2>/dev/null \
              || "$PYTHON" -m pip install -U graphifyy -q --break-system-packages 2>&1 | tail -3
        fi
        if ! _GRAPHIFY_MISSING=$("$PYTHON" -c "$_GRAPHIFY_PROBE" 2>&1); then
            echo "graphify at $PYTHON is older than this skill ($_GRAPHIFY_MISSING)." >&2
            echo "Upgrade it with 'uv tool install --upgrade graphifyy' or 'pip install -U graphifyy', then run /graphify again." >&2
            exit 1
        fi
    fi
fi
# Write interpreter path for all subsequent steps (persists across invocations)
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)"
# Save scan root so `graphify update` (no args) knows where to look next time.
# The scan path is passed through a quoted heredoc, never substituted into the
# command line itself: a bare `cd <path>` (or an unquoted heredoc, which
# still expands $()/backticks in its body) would let a malicious path execute
# as shell code the moment this line runs.
"$PYTHON" -c "import os, sys; out_path = os.path.abspath('graphify-out/.graphify_root'); os.chdir(sys.stdin.readline().rstrip('\n')); open(out_path, 'w', encoding='utf-8').write(os.getcwd())" <<'GRAPHIFY_ROOT_EOF'
INPUT_PATH
GRAPHIFY_ROOT_EOF
```

If the block succeeds, print nothing and move straight to Step 2. If it exits with "older than this skill", stop and show the user that message; do not continue to Step 2.

**In every subsequent bash block, replace `python3` with `$(cat graphify-out/.graphify_python)` to use the correct interpreter.**
