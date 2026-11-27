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

The bridge is pinned to `@deepseek-ai/dsh-hooks-claude-code@0.2.3-alpha.2`. The install checks each profile's installed copy, not just its `package.json`: a profile that only declares the bridge, or carries an older copy, is named and the install exits 2, because dsh cannot mount the overlay without a usable bridge. Run `graphify dsh doctor` to fix that. It adds the pinned bridge to every profile under `$DSH_HOME/profiles` through `dsh plugin --profile <p> add @deepseek-ai/dsh-hooks-claude-code@0.2.3-alpha.2`, writes any missing skill, hook config or overlay for the active scope (keeping your own hook entries and the existing `--strict` choice), then re-checks the result. It exits 0 only when exactly one scope mounts a complete, usable wiring; a double mount is reported rather than silently resolved, since which scope to keep is your call. Never use a bare `latest`, whose published tag predates the event contract these hooks rely on. If the running dsh is on a different line, install the bridge version that matches it: `dsh plugin add` refuses a bridge older than the runtime. A user-scope install (`graphify dsh install`, no `--project`) writes the skill and hook config under `$DSH_HOME` (default `~/.dsh`) and fences the same overlay row into `$DSH_HOME/cordis.patch.yml`, the layer every profile applies.

`graphify dsh doctor --check` is the read-only form: it prints each profile's bridge state, the project overlay and home fence, the hook groups and whether `graphify` is on PATH without writing anything, for CI or a post-upgrade audit.

A plain install is advisory: every qualifying read or grep gets one budgeted nudge. Add `--strict` to register the same one-shot deny a strict Claude Code install gets - the first indexed read or dedicated grep of a session is redirected to `graphify query` and every later call only advises. Anything the extraction manifest does not index - an unindexed file, a path outside the project, a file under the graph's own output directory - is never blocked.

```bash
graphify dsh doctor               # repair: bridge, wiring, then re-check
graphify dsh doctor --check       # read-only diagnosis
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
