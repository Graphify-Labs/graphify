# graphify reference: commit hook and native AGENTS.md integration

Load this when the user asked to install the post-commit hook or wire graphify into a project's AGENTS.md.

## For git commit hook

Install a post-commit hook that auto-rebuilds the graph after every commit. No background process needed - triggers once per commit, works with any editor.

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

After every `git commit`, the hook detects changed code, stages a native update, and atomically activates `graphify-out/graph.helix` with its report. Doc/image changes require an explicit `graphify update .`.

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
