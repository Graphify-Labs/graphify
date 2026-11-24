# graphify reference: commit hook and DeepSeek Harness integration

Load this when the user asked to install the post-commit hook or wire graphify into a DeepSeek Harness (dsh) project.

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

## For native DeepSeek Harness integration

Run once per project to make graphify always-on in DeepSeek Harness sessions:

```bash
graphify dsh install --project
```

This writes three things:

- the skill and its `references/` sidecar to `.dsh/skills/graphify/`, the root dsh discovers;
- `.dsh/hooks.json` in the Claude Code shape - `bash|grep` runs `graphify hook-guard search`, `read|glob` runs `graphify hook-guard read`, and `startup|resume|clear|compact` runs `graphify hook-guard session` (matchers are lowercase because dsh's bridge compares pipe literals exactly and case-sensitively);
- `.dsh/graphify.cordis.yml`, the composition overlay whose `insert` row (`id: graphify-hooks`) mounts `@deepseek-ai/dsh-hooks-claude-code` with `configPath: ./.dsh/hooks.json`.

dsh reads no hook file on its own, so launch it with the overlay and restart dsh after installing:

```bash
dsh --patch .dsh/graphify.cordis.yml
```

The bridge is pinned to `@deepseek-ai/dsh-hooks-claude-code@0.2.3-alpha.2`. When the profile cannot resolve it, the install prints the exact command that adds it (`dsh plugin --profile <name> add ...@0.2.3-alpha.2`); never use a bare `latest`, whose published tag predates the event contract these hooks rely on. If the running dsh is on a different line, install the bridge version that matches it: `dsh plugin add` refuses a bridge older than the runtime. A user-scope install (`graphify dsh install`, no `--project`) writes the skill and hook config under `$DSH_HOME` (default `~/.dsh`) and fences the same overlay row into `$DSH_HOME/cordis.patch.yml`, the layer every profile applies.

A plain install is advisory: every qualifying read or grep gets one budgeted nudge. Add `--strict` to register the same one-shot deny a strict Claude Code install gets - the first indexed read or dedicated grep of a session is redirected to `graphify query` and every later call only advises. Anything the extraction manifest does not index - an unindexed file, a path outside the project, a file under the graph's own output directory - is never blocked.

```bash
graphify dsh uninstall            # remove the skill, graphify's hook entries and the overlay fence
graphify dsh uninstall --project  # project scope
```

## Source-read freshness

The source-read guard treats a file newer than `graph.json` as potentially stale,
but a checkout can refresh timestamps without changing content. For newer files,
the guard checks the exact project-relative path (or an exact legacy absolute
path) in the configured output directory's extraction manifest. Every populated
AST/semantic hash must match the current content; a matching tier cannot hide a
stale tier. Unchanged content retains the normal graph guidance and strict-mode
first-read deny.

Missing, unreadable, malformed or oversized manifests, unknown paths, and absent
or invalid hashes retain the conservative stale soft nudge. A `needs_update`
marker always softens the guard, even when content matches. Older-mtime files
are not hashed; this is a checkout-timestamp check, not a full freshness audit.
