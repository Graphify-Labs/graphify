# Central graph store + push/pull hooks

By default graphify writes `graphify-out/` in the current directory. For teams —
especially monorepos where graphs run 300MB–1GB per module — you can keep **all**
graph data in a central **store folder** instead: the repo never holds the bytes,
only a link. Sharing happens through **push/pull hooks committed in the repo**, so
graphify stays backend-agnostic (S3, MinIO, git-lfs, rsync, a network share,
anything) and a clone carries its own sync behaviour.

## One-command setup

```bash
graphify remote init                       # private S3/MinIO (default)
graphify remote init --backend s3-public   # authenticated push, URL-only pull — readers need NO creds
graphify remote init --backend git-lfs     # a git repo with git-lfs
graphify remote init --backend rsync       # rsync / SSH / a mounted network share
```

creates the repo's committed graphify home:

```
.graphify/
├── config.json     { "store": "~/graphify-store/<repo>" }  ← edit to any path
├── push.py         starter S3/MinIO hooks — swap for push.sh/.js/.ps1/.cmd
└── pull.py         (same name) or any script via config.json {"push": "<path>"}
```

Commit `.graphify/` and the team is onboarded: teammates clone and run
`graphify remote pull`. Existing files are never overwritten; a hook already present in
another language is respected.

## How the store works

Any graphify command first makes sure `./graphify-out` is a **link** into the
store:

```
~/graphify-store/myrepo/                         ← the store path you set (outside the repo)
├── graphify-out/                                ← repo-root graphs
└── services/api/graphify-out/                   ← that module's graphs

myrepo/                                          ← the git repo
├── .graphify/                                   ← committed (config + hooks)
├── graphify-out         → ~/graphify-store/myrepo/graphify-out
└── services/api/graphify-out → …/services/api/graphify-out
```

- POSIX: a symlink. Windows: a **directory junction** — no admin rights, but the
  store must be a local path there (the hooks do the network leg).
- Every write physically lands in the store; every literal `graphify-out/...`
  path — CLI defaults, the agent skill's code blocks, plain `cat` — keeps working
  through the link. **The skill needs no changes.**
- **The store path is the whole key** — no `<repo>`/`<branch>` segments. The repo
  points at the same store location on *every* branch (switch branches → no
  retarget, no rebuild; `graphify update` refreshes the graph), and each repo
  simply names its own store path in its config. `graphify remote init` defaults
  the path to `~/graphify-store/<folder>`; change it to anything you like.
- A monorepo gets one link per directory you build in, keyed by its repo-relative
  path. `graphify remote pull` additionally fans links out for **every** module already
  present in the store, so a fresh clone reads any module's graphs (e.g.
  `merge-graphs ./services/api/graphify-out/graph.json` from the root) after one
  pull.
- A pre-existing real `graphify-out/` folder is **migrated** into the store once
  (contents moved, folder replaced by the link).
- No `.graphify/config.json` (or no `store` key) → the classic local
  `./graphify-out`, nothing changes. An absolute `GRAPHIFY_OUT` env override also
  disables linking.

### git never sees the data

When graphify creates a link it also ensures the repo-root `.gitignore` contains a
bare `graphify-out` entry (creating the file if needed). Bare on purpose: the
common `graphify-out/` pattern matches only *directories*, and git treats a POSIX
symlink as a file — with the trailing slash the links themselves would appear in
`git status`. The bare entry matches the symlink, the junction, and a plain folder
alike, at any depth, so one line covers every module. Even unignored, a symlink
commits as a ~100-byte target path — git never follows it into content.

## Sync hooks

`graphify remote push` / `graphify remote pull` run a hook — any executable: Python, Node,
shell, PowerShell, `.cmd`/`.bat`, or a binary. The contract: mirror
`GRAPHIFY_STORE_DIR` (the `<store>` tree) to/from your backend and
exit non-zero on failure. If the store folder is already shared (NFS, Dropbox, …),
you never need push/pull. To leave the store later, `graphify remote delete` turns every link back into a real local folder (a copy — the store is untouched); then delete `.graphify/` and commit.

Resolution order:
1. an explicit path in `.graphify/config.json`:
   `{ "store": "...", "push": "./scripts/push.py", "pull": "./scripts/pull.py" }`
2. `.graphify/<push|pull>.{py,js,mjs,cjs,sh,ps1,cmd,bat}` committed in the repo

An executable hook runs directly (its shebang wins — e.g.
`#!/usr/bin/env -S uv run --with boto3 python3`); otherwise graphify picks the
interpreter by extension, so it also works on Windows where shebangs are ignored.

**Secrets stay out of the repo.** The committed hooks read credentials from the
environment (env vars, `~/.aws`, …) — the starter S3 hooks use `GRAPHIFY_BUCKET`
/ `GRAPHIFY_S3_ENDPOINT` plus boto3's standard credential chain, and skip
`cache/` (a local-only accelerator). With the **`s3-public`** backend only
*pushers* need creds — readers pull from the committed public `store_url` over plain
HTTP (a `_manifest.json` lists the keys, so no listing, no SDK, no keys). Extra non-secret keys you add to
`config.json` are yours to read — hooks get its path as `GRAPHIFY_CONFIG`.

### Hook environment

| Variable | Meaning |
|---|---|
| `GRAPHIFY_ACTION` | `push` or `pull` |
| `GRAPHIFY_STORE_DIR` | the configured `<store>` path — the tree to mirror |
| `GRAPHIFY_STORE` | the same store path, expanded |
| `GRAPHIFY_CONFIG` | path to `.graphify/config.json` (read your own extra keys) |
| `GRAPHIFY_REPO_ROOT` | repo top-level dir (context only — data is not here) |
| `GRAPHIFY_PREFIX` | the store folder's basename — a natural object-key prefix |

## Typical team flow

```bash
# publisher (once)
graphify remote init   # .graphify/ with config + hooks; edit, then commit it
graphify .             # writes through the link into the store (per module: cd m && graphify .)
graphify remote push   # hook uploads the <store> tree

# teammate
git clone … && cd …
graphify remote pull   # hook downloads the store tree AND recreates a graphify-out
                       # link for every module found in it — the whole working set
graphify query "how does auth work?"
```

Graphs never enter git; the repo carries only `.graphify/` and the auto-maintained
`.gitignore` entry. Note `graphify update .` / `watch` write through the link too —
keep the store on a local disk (hooks do the network leg) so incremental updates
stay fast.
