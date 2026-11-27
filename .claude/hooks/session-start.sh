#!/bin/bash
# SessionStart hook: install dependencies so tests and linters work in
# Claude Code on the web sessions. Idempotent and non-interactive.
set -euo pipefail

# Only run in the remote (Claude Code on the web) environment; local sessions
# manage their own virtualenv.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Install uv if it isn't already on PATH (the remote image may not ship it).
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
fi

# --frozen installs straight from the committed uv.lock without re-resolving or
# rewriting it (mirrors CI). --all-extras pulls in the dev tools (pytest, ruff).
uv sync --all-extras --frozen
