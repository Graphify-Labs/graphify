#!/usr/bin/env bash
#
# Build graphify-installer.exe (and the bundled graphify.exe / graphify-mcp.exe)
# on Windows. Run from a checkout of graphify, with Visual Studio Build Tools
# installed and on PATH (Nuitka needs a C compiler).
#
# Usage:
#     tools/build_windows_installer.sh
#
# Output:
#     dist/graphify-installer.exe   — the offline installer
#     dist/graphify.exe             — the bundled graphify CLI
#     dist/graphify-mcp.exe         — the bundled graphify MCP server
#
# Wheelhouse (cached at ./wheelhouse-windows/) is reused across builds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python}"
WHEELHOUSE="$REPO_ROOT/wheelhouse-windows"
DIST="$REPO_ROOT/dist"

echo "==> Python: $($PYTHON --version)"
echo "==> Wheelhouse: $WHEELHOUSE"
echo "==> Output:     $DIST"

# 1. Download Windows wheels for every default-bundled dep (one-time).
echo "==> Resolving wheels..."
mkdir -p "$WHEELHOUSE"
$PYTHON -m pip download \
    --dest "$WHEELHOUSE" \
    --python-version 3.10 \
    --platform win_amd64 \
    --only-binary=:all: \
    --requirement <($PYTHON -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print('\n'.join(data['project']['optional-dependencies']['windows-offline']))
")

# 2. Install graphify itself as a wheel (so Nuitka finds the package).
echo "==> Building graphify wheel..."
$PYTHON -m pip wheel . --no-deps --wheel-dir "$WHEELHOUSE" >/dev/null

# 3. Set up a clean venv that uses ONLY the wheelhouse (offline simulation).
echo "==> Building offline venv..."
VENV="$REPO_ROOT/.venv-offline-build"
rm -rf "$VENV"
$PYTHON -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install \
    --no-index \
    --find-links "$WHEELHOUSE" \
    graphifyy \
    >/dev/null

# 4. Run Nuitka three times in the offline venv.
echo "==> Compiling graphify.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=networkx,numpy,rapidfuzz \
    --include-module=anthropic \
    --include-module=mcp,starlette \
    --include-module=graspologic \
    --include-module=tree_sitter,tree_sitter_python,tree_sitter_javascript,tree_sitter_typescript,tree_sitter_go,tree_sitter_rust,tree_sitter_java,tree_sitter_groovy,tree_sitter_c,tree_sitter_cpp,tree_sitter_ruby,tree_sitter_c_sharp,tree_sitter_kotlin,tree_sitter_scala,tree_sitter_php,tree_sitter_swift,tree_sitter_lua,tree_sitter_zig,tree_sitter_powershell,tree_sitter_elixir,tree_sitter_objc,tree_sitter_julia,tree_sitter_verilog,tree_sitter_fortran,tree_sitter_bash,tree_sitter_json \
    --include-module=matplotlib,watchdog,tree_sitter_sql,tree_sitter_hcl,jieba \
    --output-filename=graphify.exe \
    graphify/__main__.py

echo "==> Compiling graphify-mcp.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=networkx,numpy,rapidfuzz \
    --include-module=anthropic \
    --include-module=mcp,starlette \
    --include-module=graspologic \
    --include-module=tree_sitter,tree_sitter_python,tree_sitter_javascript,tree_sitter_typescript,tree_sitter_go,tree_sitter_rust,tree_sitter_java,tree_sitter_groovy,tree_sitter_c,tree_sitter_cpp,tree_sitter_ruby,tree_sitter_c_sharp,tree_sitter_kotlin,tree_sitter_scala,tree_sitter_php,tree_sitter_swift,tree_sitter_lua,tree_sitter_zig,tree_sitter_powershell,tree_sitter_elixir,tree_sitter_objc,tree_sitter_julia,tree_sitter_verilog,tree_sitter_fortran,tree_sitter_bash,tree_sitter_json \
    --include-module=matplotlib,watchdog,tree_sitter_sql,tree_sitter_hcl,jieba \
    --output-filename=graphify-mcp.exe \
    graphify/serve.py

echo "==> Compiling graphify-installer.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=graphify.installer \
    --output-filename=graphify-installer.exe \
    tools/installer_main.py

# 5. Collect artifacts.
echo "==> Collecting artifacts..."
mkdir -p "$DIST"
mv graphify.exe "$DIST/"
mv graphify-mcp.exe "$DIST/"
mv graphify-installer.exe "$DIST/"

ls -la "$DIST"
echo "==> Done. Distribute $DIST/graphify-installer.exe."
