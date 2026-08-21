# graphify reference: commit hook and native AGENTS.md integration

Load this when the user asked to install the post-commit hook or wire graphify into a project's AGENTS.md.

## For git commit hook

Install a post-commit hook that auto-rebuilds the graph after every commit. No background process needed - triggers once per commit, works with any editor.

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

After every `git commit`, the hook detects which code files changed (via `git diff HEAD~1`), re-runs AST extraction on those files, and rebuilds `graph.json` and `GRAPH_REPORT.md`. This default path uses no LLM and has no API cost.

For a project where docs, papers, or images must stay current without a manual step, add an explicit opt-in before installing the hook:

```ini
# .graphifyrc
semantic_update=on_commit
semantic_backend=kimi
semantic_env_file=.env.local
# semantic_model=kimi-k2.6  # optional
# semantic_google_workspace=true  # optional
```

The semantic worker is detached, coalesces overlapping commits, honors ignore rules, and leaves failed work queued for retry. The env file is never executed; Graphify only reads credential variables for the selected backend, preserves credentials already in the process environment, and ignores endpoint variables. Keep the env file untracked. Without this config, the hook remains AST-only.

If a post-commit hook already exists, graphify appends to it rather than replacing it.

---

## For native AGENTS.md integration (Trae)

Run once per project to make graphify always-on in Trae sessions:

```bash
graphify trae install       # or: graphify trae-cn install
```

This writes a `## graphify` section to the local `AGENTS.md` that instructs Trae to check the graph before answering codebase questions and rebuild it after code changes. No manual `/graphify` needed in future sessions.

> **Note:** Unlike Claude Code, Trae does NOT support PreToolUse hooks. The AGENTS.md rules are the always-on mechanism — there is no automatic graph rebuild on tool use. Run `/graphify --update` manually after code changes if the graph needs refreshing.

```bash
graphify trae uninstall     # or: graphify trae-cn uninstall   # remove the section
```
