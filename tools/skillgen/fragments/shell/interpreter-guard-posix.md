```bash
{{python_resolver}}
# Resolve from the installed CLI/tool environment, never execute a workspace sidecar.
graphify_find_python || { echo 'No persistent Python interpreter can import graphify. Re-run Step 1.' >&2; exit 1; }
mkdir -p graphify-out
"$PYTHON" -c "import graphify, sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)" || exit 1
```
