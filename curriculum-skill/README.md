# Graphify curriculum skill overlay

This directory is the maintained source for the validated Codex Graphify
curriculum skill. It is installed over the user-level Graphify skill produced by
the `graphifyy` package so package installs and upgrades cannot become the only
copy of the curriculum workflow.

Install or refresh the active skill with:

```bash
./scripts/install-curriculum-skill
```

The installer copies the complete tracked skill tree into
`${CODEX_HOME:-$HOME/.codex}/skills/graphify` and verifies SHA-256 hashes after
installation. Run it again after `uv tool upgrade graphifyy` and
`graphify install --platform codex`.
