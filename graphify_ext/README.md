# graphify_ext — fork extension layer

This package holds **all code owned by this fork**
(`BiomedicalEvidencePlatform/graphify`). It is never present in upstream
(`safishamsi/graphify`), so it never causes merge conflicts when pulling upstream.

## What's here

- `policy.py` — the platform allowlist (`{"claude"}`). The single source of truth for
  "this is a Claude Code-only build."

## Where future features go

Build your extensions here so they survive upstream merges:

- **New CLI subcommands** — add a module here and dispatch to it from a thin hook.
- **Custom ingest / graph logic** — domain-specific node/edge extraction.
- **Custom exporters / reports** — consume the graph, emit your own outputs.

The rule: **add files under `graphify_ext/`; never edit upstream files unless
unavoidable.** Today the only upstream edits are (1) a 2-line gate at the top of
`install()` in `graphify/__main__.py` and (2) registering `graphify_ext` in
`pyproject.toml`'s `[tool.setuptools] packages`.

## Why there are "dead" references in upstream code

We deleted the non-Claude asset files (`skill-*.md`, `skills/*`, `always_on/*`,
`command-kilo.md`) but **deliberately left `_PLATFORM_CONFIG`, the body of
`install()`, and the `pyproject` package-data globs byte-identical to upstream.**
Those now point at deleted files — but `enforce()` rejects every non-Claude platform
*before* that code runs, and setuptools silently ignores package-data globs that match
nothing. Leaving the shared code untouched is what keeps upstream merges painless.

See `../FORK.md` for the full strategy and the one-command resync procedure.
