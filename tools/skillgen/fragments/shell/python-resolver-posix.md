# Resolve a persistent interpreter and verify graphify before saving it.
graphify_accept_python() {
    [ -n "$1" ] || return 1
    _GRAPHIFY_RESOLVED=$("$1" -c "import graphify, sys; from pathlib import Path; assert not any(part.startswith('archive-v') for p in (Path(sys.executable), Path(sys.executable).resolve()) for part in p.parts), 'ephemeral uv interpreter'; print(sys.executable)" 2>/dev/null) || return 1
    [ -n "$_GRAPHIFY_RESOLVED" ] || return 1
    PYTHON="$_GRAPHIFY_RESOLVED"
}
graphify_find_python() {
    PYTHON=""
    # uv tool dir identifies the persistent tool environment, including Windows.
    if command -v uv >/dev/null 2>&1; then
        _GRAPHIFY_TOOLS=$(uv tool dir 2>/dev/null)
        if [ -n "$_GRAPHIFY_TOOLS" ]; then
            for _GRAPHIFY_CANDIDATE in "$_GRAPHIFY_TOOLS/graphifyy/bin/python" "$_GRAPHIFY_TOOLS/graphifyy/Scripts/python.exe"; do
                graphify_accept_python "$_GRAPHIFY_CANDIDATE" && return 0
            done
        fi
    fi
    if command -v pipx >/dev/null 2>&1; then
        _GRAPHIFY_TOOLS=$(pipx environment --value PIPX_LOCAL_VENVS 2>/dev/null)
        if [ -n "$_GRAPHIFY_TOOLS" ]; then
            for _GRAPHIFY_CANDIDATE in "$_GRAPHIFY_TOOLS/graphifyy/bin/python" "$_GRAPHIFY_TOOLS/graphifyy/Scripts/python.exe"; do
                graphify_accept_python "$_GRAPHIFY_CANDIDATE" && return 0
            done
        fi
    fi
    # Only text launchers with a literal, single-path shebang are candidates.
    # Never read a PE executable as a shebang or evaluate launcher contents.
    _GRAPHIFY_BIN=$(command -v graphify 2>/dev/null)
    case "$_GRAPHIFY_BIN" in
        *.exe|*.EXE) ;;
        *)
            if [ -f "$_GRAPHIFY_BIN" ] && [ "$(head -c 2 "$_GRAPHIFY_BIN" 2>/dev/null)" = '#!' ]; then
                IFS= read -r _GRAPHIFY_FIRST < "$_GRAPHIFY_BIN"
                _GRAPHIFY_SHEBANG=${_GRAPHIFY_FIRST#\#!}
                case "$_GRAPHIFY_SHEBANG" in
                    ''|*[!a-zA-Z0-9/_.@-]*) ;;
                    *) graphify_accept_python "$_GRAPHIFY_SHEBANG" && return 0 ;;
                esac
            fi
            ;;
    esac
    for _GRAPHIFY_COMMAND in python3 python; do
        _GRAPHIFY_CANDIDATE=$(command -v "$_GRAPHIFY_COMMAND" 2>/dev/null)
        graphify_accept_python "$_GRAPHIFY_CANDIDATE" && return 0
    done
    return 1
}
