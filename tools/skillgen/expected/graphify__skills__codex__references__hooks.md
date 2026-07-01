# graphify reference: commit hook and native AGENTS.md integration

Load this when the user asked to install the post-commit hook or wire graphify into a project's AGENTS.md.

## For git commit hook

Install a post-commit hook that auto-rebuilds the graph after every commit. No background process needed - triggers once per commit, works with any editor.

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

After every `git commit`, the hook detects which code files changed (via `git diff HEAD~1`), re-runs AST extraction on those files, and rebuilds `graph.json` and `GRAPH_REPORT.md`. Doc/image changes are ignored by the hook - run `/graphify --update` manually for those.

If a post-commit hook already exists, graphify appends to it rather than replacing it.

---

## For native AGENTS.md integration (Codex)

Run once per project to make graphify always-on in Codex sessions:

```bash
graphify codex install --project
```

This writes a `## graphify` section to the local `AGENTS.md` that instructs Codex to check the graph before answering codebase questions and rebuild it after code changes. No manual `/graphify` needed in future sessions.

This also writes `.codex/hooks.json` so Codex can trigger graphify's update hook from project-local configuration.

```bash
graphify codex uninstall --project  # remove the section
```
