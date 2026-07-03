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
# Wheelhouse is keyed by the Python version the build is running on so that
# cached wheels from a previous build (e.g. cp310 from an older windows-2022
# image) are never silently reused for a different interpreter (e.g. cp312
# on the current windows-2022 image, which has 3.12.10 on PATH). Mixing
# wheels from two interpreters in one --find-links dir is what makes
# `pip install --no-index` fail with
#   "ERROR: Could not find a version that satisfies the requirement ... (from versions: none)"
# even though the wheel file is on disk.
PY_VERSION="$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")"
WHEELHOUSE="$REPO_ROOT/wheelhouse-windows-cp${PY_VERSION}"
DIST="$REPO_ROOT/dist"

echo "==> Python: $($PYTHON --version) (cp${PY_VERSION})"
echo "==> Wheelhouse: $WHEELHOUSE"
echo "==> Output:     $DIST"

# 1. Download Windows wheels for every default-bundled dep (one-time).
echo "==> Resolving wheels..."
mkdir -p "$WHEELHOUSE"

# Emit the dependency list to a real temp file rather than relying on bash
# process substitution (`<($PYTHON ...)`). Process substitution produces a
# /proc/<pid>/fd/NN path that pip cannot open when the script runs under
# Git Bash on Windows (no /proc filesystem in MSYS), so `pip download
# --requirement <(...)` fails with
# "Could not open requirements file: [Errno 2] No such file or directory:
# '/proc/<pid>/fd/NN'".
WHEEL_REQ="$(mktemp -t graphify-wheel-req.XXXXXX)"
trap 'rm -f "$WHEEL_REQ"' EXIT
$PYTHON -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print('\n'.join(data['project']['optional-dependencies']['windows-offline']))
" > "$WHEEL_REQ"

# The offline venv below runs Nuitka, but `windows-offline` is the runtime
# extra (graphifyy + 38 runtime wheels) and intentionally does not list
# `nuitka` — Nuitka lives in the `dev` group. The venv is built with
# `--no-index --find-links "$WHEELHOUSE"`, so anything not pulled into
# the wheelhouse is unimportable, and the build then dies with
#   "No module named nuitka". Add it here so it lands in the same cache.
# Bump the pin to match the dev group (>=4.1).
echo 'nuitka>=4.1' >> "$WHEEL_REQ"
# `nuitka`'s required transitive dep. Without it, Nuitka's first import in
# the offline venv fails with No-module-named-ordered-set.
echo 'ordered-set>=4.1' >> "$WHEEL_REQ"
# Optional for Nuitka but listed in the dev group; pulling it in makes the
# onefile output compressed (without it Nuitka falls back to an uncompressed
# onefile blob, ~30% larger).
echo 'zstandard>=0.18' >> "$WHEEL_REQ"
# matplotlib's wheel METADATA declares `Requires-Dist: setuptools`, so the
# offline venv install pulls setuptools in transitively. Under
# `--no-index --find-links "$WHEELHOUSE"` pip does not fall back to whatever
# setuptools happens to be in the venv's site-packages, so without a wheel
# in the wheelhouse the install dies with
#   "ERROR: Could not find a version that satisfies the requirement
#    setuptools>=42 (from versions: none)".
# `wheel` is also pulled in for PEP 517 build isolation even when we are
# installing prebuilt wheels.
echo 'setuptools>=68' >> "$WHEEL_REQ"
echo 'wheel>=0.40' >> "$WHEEL_REQ"

# Pull the target interpreter version dynamically. Hard-coding
# `--python-version 3.10` here while the venv below is built from whatever
# `python` resolves to (e.g. 3.12 on the current windows-2022 runner) yields
# a wheelhouse the venv's pip cannot use.
#
# Keep --no-deps. With --python-version/--platform restricted, pip refuses
# to *also* follow transitives (the pass would have to assume unconstrained
# binary availability); the only way pip lets you resolve transitives under
# those flags is --only-binary=:all:, which is stricter than we want. So
# the build-tool deps (nuitka, ordered-set, zstandard) are listed explicitly
# in $WHEEL_REQ above.
$PYTHON -m pip download \
    --dest "$WHEELHOUSE" \
    --python-version "$PY_VERSION" \
    --platform win_amd64 \
    --platform py3-none-any \
    --no-deps \
    --requirement "$WHEEL_REQ"

# 2. Install graphify itself as a wheel (so Nuitka finds the package).
echo "==> Building graphify wheel..."
$PYTHON -m pip wheel . --no-deps --wheel-dir "$WHEELHOUSE" >/dev/null

# 3. Set up a clean venv from the wheelhouse, with PyPI as a fallback.
#    The wheelhouse is still the *preferred* source (--find-links makes pip
#    check it first), but we intentionally do NOT pass --no-index here:
#
#    - Under --no-index, pip refuses to consider packages already installed
#      in the venv's site-packages as a satisfier for transitive
#      requirements. That breaks on basic toolchain deps that venv
#      bootstraps (packaging, etc.) and on any matplotlib-style runtime
#      "Requires-Dist: setuptools" / "Requires-Dist: packaging" that pip
#      will keep chasing as new packages are added over time.
#    - The previous "explicit-append" approach (add setuptools, wheel,
#      packaging, ordered-set, zstandard, ...) was whack-a-mole: every
#      time something new in the dep tree declared a build-time or
#      runtime dep, the build failed with "Could not find a version that
#      satisfies the requirement X (from versions: none)".
#
#    The wheelhouse is *build-time only* — it is not shipped inside the
#    produced .exe (graphify/installer/ only edits PATH and copies
#    SKILL.md; it never re-pip-installs at runtime), so the venv does not
#    have to model a fully air-gapped user install. Letting pip fall back
#    to PyPI / already-installed packages is strictly more robust and
#    does not weaken any user-facing contract.
#
#    Nuitka is listed alongside graphifyy so the three subsequent
#    `python -m nuitka ...` invocations can actually find it.
echo "==> Building offline venv..."
VENV="$REPO_ROOT/.venv-offline-build"
rm -rf "$VENV"
$PYTHON -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install \
    --find-links "$WHEELHOUSE" \
    graphifyy \
    nuitka \
    >/dev/null

# 3.5 Pre-flight: confirm bundled_skills made it into the installed package.
# If a snapshot file is missing, this fails the build loudly instead of
# shipping a graphify.exe that's silently missing skills.
echo "==> Pre-flight: verifying bundled_skills in installed package..."
"$VENV/Scripts/python.exe" -c "
from importlib.resources import files
sp = files('graphify') / 'bundled_skills' / 'superpowers'
n = sum(1 for p in sp.iterdir() if p.is_dir())
assert n == 14, f'expected 14 superpowers skill dirs, got {n}'
assert (files('graphify') / 'bundled_skills' / 'llm-wiki' / 'SKILL.md').is_file(), 'llm-wiki SKILL.md missing'
print(f'==> Pre-flight OK: {n} superpowers + llm-wiki present')
"

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
