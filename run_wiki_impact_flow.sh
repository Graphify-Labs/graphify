#!/bin/bash
# wiki-impact flow: baseline branch -> incremental branch -> impact
# Usage:
#   ./run_wiki_impact_flow.sh                 # defaults: test1 -> test2
#   ./run_wiki_impact_flow.sh <base> <incr>    # custom branches
#   FILE_LEVEL=1 ./run_wiki_impact_flow.sh     # enable --cluster-on-files
set -euo pipefail

GRAPHIFY_DIR="${GRAPHIFY_DIR:-/Users/bingqing_1/Documents/projects/moran/tmp/graphify}"
GRAPHIFY="${GRAPHIFY_DIR}/.venv-arm64/bin/graphify"
NEUG_DIR="${NEUG_DIR:-/Users/bingqing_1/Documents/projects/tmp/neug}"
RES=0.001
MIN_CONCEPT_SIZE=3

# Optional: file-level clustering (set FILE_LEVEL=1 to enable)
CLUSTER_FLAG=""
if [ "${FILE_LEVEL:-0}" = "1" ]; then
  CLUSTER_FLAG="--cluster-on-files"
fi

BASE_BRANCH="${1:-test1}"
INCR_BRANCH="${2:-test2}"

# Pre-flight checks
if [ ! -x "$GRAPHIFY" ]; then
  echo "error: graphify not found at $GRAPHIFY" >&2
  exit 1
fi
if ! "$GRAPHIFY_DIR/.venv-arm64/bin/python3" -c "import neug" 2>/dev/null; then
  echo "error: neug not installed in $GRAPHIFY_DIR/.venv-arm64" >&2
  exit 1
fi

EXCLUDES=(
  --exclude "*.md" --exclude "*.txt" --exclude "*.rst"
  --exclude "*.pdf" --exclude "*.png" --exclude "*.jpg" --exclude "*.svg"
  --exclude "*.yml" --exclude "*.yaml" --exclude "*.toml" --exclude "*.cfg"
  --exclude "*.ini" --exclude "*.json" --exclude "*.html" --exclude "*.css"
  --exclude "*.xml" --exclude "*.csv" --exclude "*.properties" --exclude "*.jsonl"
  --exclude "docs/*" --exclude "third_party/*" --exclude "*/.venv*"
  --exclude "example_dataset/*" --exclude "LICENSE"
)

cd "$NEUG_DIR"

echo "=== [1/5] clean graphify-out ==="
rm -rf graphify-out/

echo "=== [2/5] checkout $BASE_BRANCH ==="
git checkout "$BASE_BRANCH"

echo "=== [3/5] full extract $BASE_BRANCH (with cluster, res=$RES) $CLUSTER_FLAG ==="
"$GRAPHIFY" extract . --resolution "$RES" $CLUSTER_FLAG "${EXCLUDES[@]}"

echo "=== [4/5] checkout $INCR_BRANCH + incremental extract (--no-cluster) ==="
git checkout "$INCR_BRANCH"
"$GRAPHIFY" extract . --resolution "$RES" --no-cluster "${EXCLUDES[@]}"

echo "=== [5/5] wiki-impact ($BASE_BRANCH -> $INCR_BRANCH, res=$RES) $CLUSTER_FLAG ==="
"$GRAPHIFY" delta-cluster . --resolution "$RES" $CLUSTER_FLAG

echo "=== done ==="
