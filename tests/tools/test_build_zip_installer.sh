#!/usr/bin/env bash
# Smoke test for tools/build_zip_installer.sh.
# Builds the zip in a temp dir and asserts structural / content invariants.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_SCRIPT="$REPO_ROOT/tools/build_zip_installer.sh"
WORK="$(mktemp -d -t graphify-zip-test.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

if [[ ! -x "$BUILD_SCRIPT" ]]; then
    echo "FAIL: $BUILD_SCRIPT is not executable"
    exit 1
fi

echo "==> Running build script..."
env \
    INTERNAL_PYPI_PROXY="http://192.168.21.14:25000/pypi/repository/pypi-all/simple" \
    INTERNAL_TRUSTED_HOST="192.168.21.14" \
    INTERNAL_TIMEOUT="6000" \
    "$BUILD_SCRIPT"

ZIP="$REPO_ROOT/dist/graphify-offline-installer.zip"
if [[ ! -f "$ZIP" ]]; then
    echo "FAIL: $ZIP not produced"
    exit 1
fi

# Extract to inspect
mkdir -p "$WORK/extracted"
unzip -q "$ZIP" -d "$WORK/extracted"

# Invariant 1: install.bat exists, no placeholders, contains the real URL
INSTALL_BAT="$WORK/extracted/install.bat"
[[ -f "$INSTALL_BAT" ]] || { echo "FAIL: install.bat missing"; exit 1; }
grep -q "<INTERNAL_" "$INSTALL_BAT" && { echo "FAIL: placeholders not substituted"; exit 1; }
grep -q "192.168.21.14" "$INSTALL_BAT" || { echo "FAIL: real proxy URL missing"; exit 1; }
grep -q "graphify install claude" "$INSTALL_BAT" || { echo "FAIL: deploy step missing"; exit 1; }

# Invariant 2: uninstall.bat exists
UNINSTALL_BAT="$WORK/extracted/uninstall.bat"
[[ -f "$UNINSTALL_BAT" ]] || { echo "FAIL: uninstall.bat missing"; exit 1; }
grep -q "graphify uninstall claude" "$UNINSTALL_BAT" || { echo "FAIL: uninstall step missing"; exit 1; }

# Invariant 3: README.txt exists and mentions proxy
README_TXT="$WORK/extracted/README.txt"
[[ -f "$README_TXT" ]] || { echo "FAIL: README.txt missing"; exit 1; }
grep -q "192.168" "$README_TXT" || { echo "FAIL: README missing proxy URL"; exit 1; }

# Invariant 4: python/ exists with python.exe and _pth has 'import site' enabled
PY_DIR="$WORK/extracted/python"
[[ -d "$PY_DIR" ]] || { echo "FAIL: python/ directory missing"; exit 1; }
[[ -f "$PY_DIR/python.exe" ]] || { echo "FAIL: python.exe missing"; exit 1; }
_PTH=$(find "$PY_DIR" -maxdepth 1 -name "python*._pth" | head -n1)
[[ -n "$_PTH" ]] || { echo "FAIL: no ._pth file in python/"; exit 1; }
grep -q "^import site$" "$_PTH" || { echo "FAIL: 'import site' not enabled in $_PTH"; exit 1; }

# Invariant 5: zip size is reasonable (< 20 MB; spec says ~10 MB)
SIZE_BYTES=$(stat -f%z "$ZIP" 2>/dev/null || stat -c%s "$ZIP")
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
[[ $SIZE_MB -lt 20 ]] || { echo "FAIL: zip too large ($SIZE_MB MB)"; exit 1; }

echo "PASS: all invariants satisfied (zip=$SIZE_MB MB)"
