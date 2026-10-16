If the scan path contains a line break (a newline or carriage return), stop and ask the user for a different path. Do not run the block below: a path line could end the heredoc early and run the lines after it as shell.

```bash
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs)
PYTHON=""
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
# 1. uv tool installs — most reliable on modern Mac/Linux
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
# 2. Read shebang from graphify binary (pipx and direct pip installs)
if [ -z "$PYTHON" ] && [ -n "$GRAPHIFY_BIN" ]; then
    _SHEBANG=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$_SHEBANG" in
        *[!a-zA-Z0-9/_.@-]*) ;;
        *) "$_SHEBANG" -c "import graphify" 2>/dev/null && PYTHON="$_SHEBANG" ;;
    esac
fi
# 3. Fall back to python3
if [ -z "$PYTHON" ]; then PYTHON="python3"; fi
if ! "$PYTHON" -c "import graphify" 2>/dev/null; then
    if command -v uv >/dev/null 2>&1; then
        uv tool install --upgrade graphifyy -q 2>&1 | tail -3
        _UV_PY=$(uv tool run --from graphifyy python -c "import sys; print(sys.executable)" 2>/dev/null)
        if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
    else
        "$PYTHON" -m pip install graphifyy -q 2>/dev/null \
          || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
    fi
fi
# Save the interpreter path and the scan root for all later steps.
# One Python call writes both (#4346): it first removes last run's files, writes
# each through a temp file and a rename, and exits 1 naming the file if a write
# fails, so a full disk can't leave an empty or stale marker behind.
# The shell never expands the scan path: it goes through a quoted heredoc, not the
# command line. A path with a line break is refused, because it could end the
# heredoc early and run the lines after it as shell; the Python below also
# rejects input of more than one line.
mkdir -p graphify-out
"$PYTHON" -c "
import os, sys
out = os.path.abspath('graphify-out')
for name in ('.graphify_python', '.graphify_root'):
    try:
        os.remove(os.path.join(out, name))
    except FileNotFoundError:
        pass
def save(name, text):
    path = os.path.join(out, name)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        sys.exit(f'graphify: could not write graphify-out/{name} ({e.strerror}; is the disk full?)')
save('.graphify_python', sys.executable)
raw = sys.stdin.read()
path = raw[:-1] if raw.endswith('\n') else raw
if '\n' in path or '\r' in path:
    sys.exit('graphify: the scan path has a line break, so it was not used; give a single-line path')
os.chdir(path)
save('.graphify_root', os.getcwd())
" <<'GRAPHIFY_ROOT_EOF'
INPUT_PATH
GRAPHIFY_ROOT_EOF
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `"$(cat graphify-out/.graphify_python)"` to use the correct interpreter.**
