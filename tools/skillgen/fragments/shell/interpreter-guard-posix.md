```bash
if [ ! -f graphify-out/.graphify_python ]; then
    GRAPHIFY_BIN=$(which graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
        # Resolve `/usr/bin/env python` and strip any shebang argument (pipx
        # writes `.../python -E`) before the allowlist check, else the space
        # forces the unverified python3 fallback into .graphify_python (#2629).
        case "$PYTHON" in */env\ *) PYTHON="${PYTHON#*/env }" ;; esac
        PYTHON="${PYTHON%% *}"
        case "$PYTHON" in *[!a-zA-Z0-9/_.@-]*) PYTHON="python3" ;; esac
        if [ "$PYTHON" != "python3" ] && ! "$PYTHON" -c "import graphify" 2>/dev/null; then
            PYTHON="python3"
        fi
    else
        PYTHON="python3"
    fi
    mkdir -p graphify-out
    "$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)"
fi
```
