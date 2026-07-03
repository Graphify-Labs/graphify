#!/usr/bin/env bash
# Build graphify-offline-installer.zip — minimal offline Windows installer.
#
# Runs on any platform with curl + unzip + zip + sed — no Python, no Windows.
#
# Outputs: dist/graphify-offline-installer.zip  (~10 MB)
#
# Required inputs:
#   tools/installer/install.bat       (with <INTERNAL_*> placeholders)
#   tools/installer/uninstall.bat
#   docs/offline-installer-README.txt
#
# Configurable via env vars:
#   INTERNAL_PYPI_PROXY   default: http://192.168.21.14:25000/pypi/repository/pypi-all/simple
#   INTERNAL_TRUSTED_HOST default: 192.168.21.14
#   INTERNAL_TIMEOUT      default: 6000
#   PY_VERSION            default: 3.12.10

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$REPO_ROOT/build/zip-installer"
DIST="$REPO_ROOT/dist"

PY_VERSION="${PY_VERSION:-3.12.10}"
EMBED_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-embed-amd64.zip"

INTERNAL_PYPI_PROXY="${INTERNAL_PYPI_PROXY:-http://192.168.21.14:25000/pypi/repository/pypi-all/simple}"
INTERNAL_TRUSTED_HOST="${INTERNAL_TRUSTED_HOST:-192.168.21.14}"
INTERNAL_TIMEOUT="${INTERNAL_TIMEOUT:-6000}"

# Sanity: required source files
for f in tools/installer/install.bat tools/installer/uninstall.bat docs/offline-installer-README.txt; do
    [[ -f "$REPO_ROOT/$f" ]] || { echo "error: missing $f"; exit 1; }
done

rm -rf "$BUILD"
mkdir -p "$BUILD/python" "$DIST"

# 1. Download and extract Python embeddable
TMP_EMBED="$(mktemp -t py-embed.XXXXXX).zip"
trap 'rm -f "$TMP_EMBED"' EXIT
echo "==> Downloading Python ${PY_VERSION} embeddable..."
curl -fsSL -o "$TMP_EMBED" "$EMBED_URL"
unzip -q "$TMP_EMBED" -d "$BUILD/python"

# 2. Enable site-packages in _pth
_PTH="$(find "$BUILD/python" -maxdepth 1 -name 'python*._pth' | head -n1)"
[[ -n "$_PTH" ]] || { echo "error: no ._pth file found in python/"; exit 1; }
sed -i.bak 's/^#import site$/import site/' "$_PTH"
rm -f "${_PTH}.bak"

# 3. Copy scripts and README
cp "$REPO_ROOT/tools/installer/install.bat"   "$BUILD/"
cp "$REPO_ROOT/tools/installer/uninstall.bat" "$BUILD/"
cp "$REPO_ROOT/docs/offline-installer-README.txt" "$BUILD/README.txt"

# 4. Substitute placeholders in install.bat
sed -i.bak \
    -e "s|<INTERNAL_PYPI_PROXY>|${INTERNAL_PYPI_PROXY}|g" \
    -e "s|<INTERNAL_TRUSTED_HOST>|${INTERNAL_TRUSTED_HOST}|g" \
    -e "s|<INTERNAL_TIMEOUT>|${INTERNAL_TIMEOUT}|g" \
    "$BUILD/install.bat"
rm -f "$BUILD/install.bat.bak"

# 5. Package
OUT="$DIST/graphify-offline-installer.zip"
rm -f "$OUT"
cd "$BUILD"
zip -r "$OUT" . >/dev/null
cd - >/dev/null

# 6. Report
SIZE_MB=$(du -m "$OUT" | cut -f1)
echo "==> Done: $OUT (${SIZE_MB} MB)"