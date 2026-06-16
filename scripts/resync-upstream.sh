#!/usr/bin/env bash
#
# resync-upstream.sh — pull upstream graphify into this Claude-only fork.
#
# Strategy (see ../FORK.md): we deleted the non-Claude asset files but left
# upstream's shared code (_PLATFORM_CONFIG, install() body, pyproject globs)
# untouched. So the only conflicts a merge can produce are:
#   1. modify/delete on the deleted asset files  -> auto-resolved below
#   2. rare content conflicts in shared code     -> you resolve by hand
#
# Usage:  scripts/resync-upstream.sh
# Run from the repo root, on the branch you want to update (e.g. v8).

set -euo pipefail

git fetch upstream

# Merge upstream. If there are conflicts, the merge stops; the git rm below
# clears the modify/delete ones, then you finish any remaining content conflicts.
git merge --no-edit upstream/v8 || true

# --- Single source of truth: the non-Claude asset delete-list ---------------
# Re-assert deletions for anything upstream re-added or modified. Idempotent:
# --ignore-unmatch means already-absent paths are no-ops.
git rm -r --ignore-unmatch \
  graphify/skill-aider.md graphify/skill-amp.md graphify/skill-claw.md \
  graphify/skill-codex.md graphify/skill-copilot.md graphify/skill-devin.md \
  graphify/skill-droid.md graphify/skill-kilo.md graphify/skill-kiro.md \
  graphify/skill-opencode.md graphify/skill-pi.md graphify/skill-trae.md \
  graphify/skill-vscode.md graphify/skill-windows.md graphify/command-kilo.md \
  graphify/skills/amp graphify/skills/claw graphify/skills/codex \
  graphify/skills/copilot graphify/skills/droid graphify/skills/kilo \
  graphify/skills/kiro graphify/skills/opencode graphify/skills/pi \
  graphify/skills/trae graphify/skills/vscode graphify/skills/windows \
  graphify/always_on/agents-md.md graphify/always_on/antigravity-rules.md \
  graphify/always_on/gemini-md.md graphify/always_on/kiro-steering.md \
  graphify/always_on/vscode-instructions.md \
  >/dev/null 2>&1 || true

# Translations: keep only English (root README.md) and Polish. Glob-based so any
# new language upstream adds is pruned automatically on the next resync.
find docs/translations -name 'README.*.md' ! -name 'README.pl-PL.md' \
  -exec git rm -q --ignore-unmatch {} + >/dev/null 2>&1 || true

echo
echo "Resync: deletions re-applied."
echo "Next:"
echo "  1. git status            # resolve any remaining content conflicts"
echo "  2. uv run pytest         # triage test fallout"
echo "  3. git commit            # finish the merge"
