#!/bin/bash
# wiki-impact flow: baseline branch -> incremental branch -> impact
# Usage:
#   ./run_wiki_impact_flow.sh                 # defaults: test1 -> test2
#   ./run_wiki_impact_flow.sh <base> <incr>    # custom branches
set -euo pipefail

GRAPHIFY_DIR="${GRAPHIFY_DIR:-/Users/bingqing_1/Documents/projects/moran/tmp/graphify}"
GRAPHIFY="${GRAPHIFY_DIR}/.venv-arm64/bin/graphify"
NEUG_DIR="${NEUG_DIR:-/Users/bingqing_1/Documents/projects/tmp/neug}"
RES=0.7
MIN_CONCEPT_SIZE=3

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

echo "=== [3/5] full extract $BASE_BRANCH (with cluster, res=$RES) ==="
"$GRAPHIFY" extract . "${EXCLUDES[@]}"

echo "=== [4/5] checkout $INCR_BRANCH + incremental extract (--no-cluster) ==="
git checkout "$INCR_BRANCH"
"$GRAPHIFY" extract . --no-cluster "${EXCLUDES[@]}"

echo "=== [5/5] delta-cluster ($BASE_BRANCH -> $INCR_BRANCH, res=$RES, min-concept-size=$MIN_CONCEPT_SIZE) ==="
"$GRAPHIFY" delta-cluster .

echo "=== done ==="
