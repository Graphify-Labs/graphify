```bash
if [ ! -f graphify-out/.graphify_python ]; then
    GRAPHIFY_BIN=$(which graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        PYTHON=$(head -n 1 "$GRAPHIFY_BIN" | sed 's/^#![[:space:]]*//')
        # Resolve env [-S], strip the pipx arg (`.../python -E`), trust only an absolute allowlisted path, else python3 (#2629).
        case "$PYTHON" in */env\ -S\ *) PYTHON="${PYTHON#*/env -S }" ;; */env\ *) PYTHON="${PYTHON#*/env }" ;; esac
        case "${PYTHON%% *}" in /*[!a-zA-Z0-9/_.@-]*) PYTHON="python3" ;; /*) PYTHON="${PYTHON%% *}" ;; *) PYTHON="python3" ;; esac
        if [ "$PYTHON" != "python3" ] && ! "$PYTHON" -c "import graphify" 2>/dev/null; then PYTHON="python3"; fi
    else
        PYTHON="python3"
    fi
    mkdir -p graphify-out
    "$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)"
fi
```
