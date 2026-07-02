# bundled_skills/

This directory holds skills bundled inside the `graphify` Python package so the
offline Windows installer ships a working skill set without network access.
Skills here are copied into `~/.claude/skills/` at install time.

## What's here

| Subdirectory  | Source                          | License | Author                  | Contents                                |
|---------------|---------------------------------|---------|-------------------------|-----------------------------------------|
| `superpowers/`| upstream `superpowers-dev` repo | MIT     | Jesse Vincent (and contributors) | 14 SKILL.md files (bundled subset)     |
| `llm-wiki/`   | project-local                   | MIT     | graphify contributors    | 1 skill + templates, scripts, platforms |

## The `gf-` rename convention

When bundled superpowers skills are copied into `~/.claude/skills/`, they are
prefixed with `gf-` to avoid colliding with the user's own superpowers plugin
installation.

Real examples from the 14 bundled superpowers skills:

- `brainstorming`                -> `gf-brainstorming`
- `subagent-driven-development`  -> `gf-subagent-driven-development`

The rename applies to:

1. The directory name (`brainstorming/` -> `gf-brainstorming/`).
2. The `name:` field in the SKILL.md frontmatter, so the slash-command becomes
   `/gf-brainstorming` rather than `/brainstorming`.

Why the prefix:

- **No collision** with a user's already-installed superpowers plugin
  (which would also drop a `brainstorming/` skill).
- **Always-overwrite safe**: the installer can overwrite `gf-*` directories on
  every run without touching any skill the user installed themselves.
- **Provenance marker**: a `gf-` prefix on a slash-command signals "shipped by
  graphify" to anyone reading the conversation transcript.

## Adding a new bundled skill

1. Create a directory under the right provider (`superpowers/` or `llm-wiki/`).
2. Drop in a `SKILL.md` whose frontmatter sets `name: gf-<your-skill>`.
3. Add the new directory to the `_BUNDLED` registry in
   `graphify/_bundled_skills.py` so the installer copies it.
4. Add a test case to `tests/test_bundled_skills.py` covering install +
   uninstall + overwrite behavior.
5. Update `LICENSE` and `NOTICE` if the skill originates from a third party.

## Syncing from upstream superpowers

There is no automation. To refresh from `superpowers-dev`, run a manual copy
loop for each skill you want to bundle, then apply the `gf-` rename and update
`name:` frontmatter:

```bash
# Placeholder list — replace with the actual skills to bundle this round.
SKILLS=(
  brainstorming
  subagent-driven-development
  # ...
)

for s in "${SKILLS[@]}"; do
  cp -r "upstream/$s/SKILL.md" "graphify/bundled_skills/superpowers/gf-$s/SKILL.md"
  # Rewrite `name: $s` -> `name: gf-$s` in the frontmatter.
  sed -i '' "s/^name: $s\$/name: gf-$s/" "graphify/bundled_skills/superpowers/gf-$s/SKILL.md"
done
```

After the loop, update `_BUNDLED` and re-run the test suite.

## Uninstall behavior

`graphify-installer.exe uninstall` does **not** remove `gf-*` skills from
`~/.claude/skills/`. Once a bundled skill lands on the user's machine it
belongs to them; removing it on uninstall would surprise users who customized
the files. The installer also does not touch any non-`gf-` skill directories.