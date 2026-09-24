# graphify reference: commit hook and native CLAUDE.md integration

Load this when the user asked to install the post-commit hook or wire graphify into a project's CLAUDE.md.

## For git commit hook

Install a post-commit hook that auto-rebuilds the graph after every commit. No background process needed - triggers once per commit, works with any editor.

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

After every `git commit`, the hook detects which code files changed (via `git diff HEAD~1`), re-runs AST extraction on those files, and rebuilds `graph.json` and `GRAPH_REPORT.md`. Doc/image changes are ignored by the hook - run `/graphify --update` manually for those (which does produce a dated `{corpus-slug}-{date}-report.md`, unlike this hook).

Like `--watch`, this hook runs the installed `graphify` binary directly, so it still uses the fixed `GRAPH_REPORT.md`/`graph.html` names rather than a dated basename - see the Step 2.6 scope note in `skill.md`.

If a post-commit hook already exists, graphify appends to it rather than replacing it.

---

## For native CLAUDE.md integration

Run once per project to make graphify always-on in Claude Code sessions:

```bash
graphify claude install
```

This writes a `## graphify` section to the local `CLAUDE.md` that instructs Claude to check the graph before answering codebase questions and rebuild it after code changes. No manual `/graphify` needed in future sessions.

```bash
graphify claude uninstall  # remove the section
```
