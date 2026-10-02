```bash
{{python_resolver}}
# Validate an existing sidecar too: old releases may have saved an ephemeral path.
_GRAPHIFY_SAVED=$(cat graphify-out/.graphify_python 2>/dev/null)
if ! graphify_accept_python "$_GRAPHIFY_SAVED"; then
    graphify_find_python || { echo 'No persistent Python interpreter can import graphify. Re-run Step 1.' >&2; exit 1; }
    mkdir -p graphify-out
    "$PYTHON" -c "import graphify, sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)" || exit 1
fi
```
