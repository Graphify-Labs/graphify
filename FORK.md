# Fork strategy — Claude Code-only graphify

This repo (`BiomedicalEvidencePlatform/graphify`) is a fork of
[`safishamsi/graphify`](https://github.com/safishamsi/graphify) (`upstream`). It is
trimmed to **Claude Code only** and adds a fork-owned extension layer, while staying
easy to update from upstream.

## The two goals in tension

1. **Claude-only product** — drop the other ~20 assistant integrations.
2. **Easy upstream updates** — `git merge upstream/v8` should rarely conflict.

Hard-deleting everything fights goal 2: every upstream edit to a file we removed becomes
a merge conflict. So we split the difference.

## The rule: gate, don't gut

- **Deleted** (clean tree): the bulky *standalone* asset files — all non-Claude
  `graphify/skill-*.md`, `graphify/skills/*`, `graphify/always_on/*`, and
  `graphify/command-kilo.md`. These are standalone, so re-merge conflicts are trivial
  modify/delete (auto-handled by `scripts/resync-upstream.sh`).
- **Docs:** translations are trimmed to English (`README.md`) and Polish
  (`docs/translations/README.pl-PL.md`); the resync script glob-prunes the rest. The
  language bar in both kept READMEs is hand-trimmed, so an upstream change to that bar
  is the one doc edit that can conflict on merge — resolve it by re-trimming to EN + PL.
- **Left byte-identical to upstream** (painless merges): `_PLATFORM_CONFIG`, the body of
  `install()` and its per-platform branches, `_platform_skill_destination`, and the
  `[tool.setuptools.package-data]` globs in `pyproject.toml`. These now reference deleted
  files — but that is harmless (see below).
- **Added** (fork-owned, never conflicts): everything under `graphify_ext/`.

### Why the dangling references are safe

- `graphify/__main__.py:install()` calls `graphify_ext.policy.enforce(platform)` at its
  top. Every non-Claude platform exits there, *before* any code reads `_PLATFORM_CONFIG`
  or tries to copy a deleted skill file. `install()` defaults to `platform="claude"`, so
  a bare `graphify install` works unchanged.
- setuptools silently ignores `package-data` entries that match no file, so `uv build`
  stays green despite the globs naming deleted files.

## The only upstream files we edit

Keep this list short — it is the entire merge-conflict surface:

1. `graphify/__main__.py` — a 2-line gate at the top of `install()`.
2. `pyproject.toml` — `graphify_ext` added to `[tool.setuptools] packages`.

Everything else we own lives under `graphify_ext/`.

## Versioning

Fork releases use a PEP 440 **local version**: `<upstream-version>+claude.N`. The base
(`0.8.40`) is the upstream version this fork is synced to; `+claude.N` is the fork
revision. So `0.8.40+claude.1` is the first fork release on top of upstream 0.8.40; after
a resync to upstream 0.8.45 the next fork release would be `0.8.45+claude.1`. This never
collides with upstream's own version line. The version lives only in `pyproject.toml`
(`__version__` is read from installed package metadata). Git tags mirror it: `v<version>`.

## Updating from upstream

```bash
scripts/resync-upstream.sh
```

It fetches upstream, merges `upstream/v8`, and re-applies the deletions (idempotent), so
any platform file upstream re-adds is pruned automatically. Then resolve any remaining
content conflicts (rare — only in the two edited files above), run `uv run pytest`, and
commit.

## Re-enabling a platform

Add its key to `ALLOWED_PLATFORMS` in `graphify_ext/policy.py` **and** restore its asset
files from upstream (they were deleted here). Also remove it from the delete-list in
`scripts/resync-upstream.sh`.
