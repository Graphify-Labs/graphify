```bash
{{python_resolver}}
if ! graphify_find_python; then
    if command -v uv >/dev/null 2>&1; then
        uv tool install --upgrade graphifyy -q || { echo 'Graphify installation failed.' >&2; exit 1; }
    else
        _GRAPHIFY_INSTALL_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
        [ -n "$_GRAPHIFY_INSTALL_PY" ] || { echo 'Install Python or uv first.' >&2; exit 1; }
        "$_GRAPHIFY_INSTALL_PY" -m pip install graphifyy -q || { echo 'Graphify installation failed.' >&2; exit 1; }
    fi
    graphify_find_python || { echo 'No persistent Python interpreter can import graphify.' >&2; exit 1; }
fi
# Save only the interpreter that passed the persistent-path and import checks.
mkdir -p graphify-out
"$PYTHON" -c "import graphify, sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)" || exit 1
# Save scan root so `graphify update` (no args) knows where to look next time.
# The scan path is passed through a quoted heredoc, never substituted into the
# command line itself: a bare `cd <path>` (or an unquoted heredoc, which
# still expands $()/backticks in its body) would let a malicious path execute
# as shell code the moment this line runs.
"$PYTHON" -c "import os, sys; out_path = os.path.abspath('graphify-out/.graphify_root'); os.chdir(sys.stdin.readline().rstrip('\n')); open(out_path, 'w', encoding='utf-8').write(os.getcwd())" <<'GRAPHIFY_ROOT_EOF'
INPUT_PATH
GRAPHIFY_ROOT_EOF
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `"$(cat graphify-out/.graphify_python)"` to use the correct interpreter.**
