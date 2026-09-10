---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
created: 2026-08-08
title: Fix #2459 — update path must pass kind="ast" to detect_incremental
---

# Fix #2459 — update path must pass `kind="ast"` to `detect_incremental`

## Problem frame

`graphify update` / the skill `--update` flow reports far more changed files than were actually modified. On the reporter's monorepo, an update after ~25 PRs flagged 811 files as changed (including untouched docs, images, and migrations); forcing `kind="ast"` reduced that to exactly the 173 files actually modified.

Root cause (confirmed in code):

- `detect_incremental(root, manifest_path, *, kind: str = "semantic", ...)` defaults to `kind="semantic"` (`graphify/detect.py:1872`).
- In semantic mode, any stored entry whose `semantic_hash` is `""` is treated as changed: `hash_key = "semantic_hash" if kind == "semantic" else "ast_hash"`; `if not stored_hash: changed = True` (`graphify/detect.py:1945-1949`).
- Files that were only ever AST-extracted (or whose `semantic_hash` was cleared) carry `semantic_hash == ""`, so they are reported changed on **every** update.
- The skill `--update` flow invokes `detect_incremental(Path('INPUT_PATH'))` with **no `kind`** (all 14 `graphify/skills/*/references/update.md:15`, plus the inline copies in `skill-aider.md:767` and `skill-devin.md:906`), so it inherits the semantic default.
- The docstring (`graphify/detect.py:1883-1884`) prescribes `kind="ast"` for update flows — docstring and call sites disagree.

Impact: each falsely-flagged semantic-eligible file spawns a semantic-extraction subagent (real model/token cost); the reporter measured ~4× the necessary subagents on one run.

## Scope

**In scope**

1. Thread `kind="ast"` through every update-semantic `detect_incremental` call site (source fragments + regenerated shipped artifacts).
2. Make the extract path's reliance on the semantic default explicit (`kind="semantic"`) so no call site silently depends on the default (zero behavior change).
3. Lock the premise with tests: ast mode must NOT report unchanged files with empty `semantic_hash`; semantic mode must continue to.
4. Guard test ensuring every shipped update runbook passes `kind="ast"`.
5. CHANGELOG entry under 0.9.36 (unreleased).

**Out of scope**

- Changing the `detect_incremental` default (`kind="semantic"` stays: the extract path depends on it — missing `semantic_hash` must mean "extract hasn't run, always re-extract").
- Changing semantic-mode's empty-hash treatment (issue suggested fix #3) — alters extract semantics and has wider blast radius; not needed once call sites are correct.
- The `graphify update` CLI command itself (`watch.py::_rebuild_code`) — it uses full `detect()` + `save_manifest(kind="ast")`, never `detect_incremental`, and does not exhibit the bug.

## Implementation units

### Unit 1 — Thread `kind="ast"` through the update flow (skillgen source of truth)

Edit the three skillgen fragments so the change propagates to all generated artifacts:

- `tools/skillgen/fragments/references/shared/update.md:15` — `detect_incremental(Path('INPUT_PATH'))` → `detect_incremental(Path('INPUT_PATH'), kind="ast")`
- `tools/skillgen/fragments/core/aider.md:767` — same change
- `tools/skillgen/fragments/core/devin.md:906` — same change

Then regenerate shipped artifacts and lock expected renders:

- `python -m tools.skillgen` — rewrites all 14 `graphify/skills/*/references/update.md` plus `graphify/skill-aider.md`, `graphify/skill-devin.md` (run from repo root; requires the `tools` package importable).
- `python -m tools.skillgen --bless` — rewrites `tools/skillgen/expected/` from the current render so `--check` stays green.

**Test scenarios**

- S1: `python -m tools.skillgen --check` exits 0 (no drift) and byte-diffs clean after regen+bless.
- S2: `grep detect_incremental graphify/skills/*/references/update.md graphify/skill-aider.md graphify/skill-devin.md` shows `kind="ast"` at every update call site and nowhere else (no unintended call-site edits).
- S3: Diff of the regen is limited to the `detect_incremental(...)` line (plus the expected/ rewrite) — no other skill text changed.

### Unit 2 — Guard test: runbooks pass `kind="ast"`

Add to `tests/test_skillgen.py`, modeled on `test_generated_runbooks_pass_root_to_save_manifest` (`tests/test_skillgen.py:664`): scan the same targets (`graphify/skill.md`, `graphify/skill-aider.md`, `graphify/skill-devin.md`, all `graphify/skills/*/references/update.md`) plus the three fragments; every line matching `detect_incremental(Path('INPUT_PATH')` must contain `kind="ast"`. Assert at least 3 matches are checked.

**Test scenarios**

- S4: test passes on the fixed tree; fails if any runbook loses `kind="ast"` (verified by reverting one call site mentally — the assertion is a plain substring check on the exact call).

### Unit 3 — Premise test: ast vs semantic empty-hash behavior

Add to `tests/test_detect.py` (model: `test_detect_incremental_propagates_follow_symlinks`, `tests/test_detect.py:475`): a corpus with one code file and one doc file; `save_manifest(..., kind="both")` on the initial scan; then write a manifest state where `semantic_hash` is `""` while content+mtime are unchanged (simulate the AST-only-extracted state by saving with `kind="ast"` then... actually simulate directly: run detect_incremental with `kind="semantic"` → both files reported changed (empty semantic_hash); with `kind="ast"` → `new_total == 0`.

Simplest faithful construction: initial `save_manifest(files, kind="both")`, then edit the on-disk manifest JSON to blank each entry's `semantic_hash` (keeps ast_hash + mtime), then:

- `detect_incremental(tmp_path, manifest_path)` (semantic default) → `new_total > 0` (doc + code both flagged).
- `detect_incremental(tmp_path, manifest_path, kind="ast")` → `new_total == 0`.

**Test scenarios**

- S5: semantic default flags empty-`semantic_hash` files (documents current behavior — the bug premise).
- S6: `kind="ast"` reports the same corpus unchanged (the fixed behavior).

### Unit 4 — Extract path: explicit `kind="semantic"`

`graphify/cli.py:2968` (`_detect_incremental(...)` in the extract command's incremental branch) — add `kind="semantic"` explicitly with a one-line comment citing #2459 (behavior unchanged; makes the docstring/call-site contract explicit and protects the extract path from future default drift).

**Test scenarios**

- S7: existing `tests/test_extract_cli.py` incremental tests pass unchanged (behavior preservation); full relevant suites green (below).

### Unit 5 — CHANGELOG

Add a `- Fix:` bullet under `## 0.9.36 (unreleased)` in `CHANGELOG.md` summarizing the fix, crediting issue #2459.

## Dependencies and sequencing

1 → 2 → 3 can proceed in any order; 1 must complete (regen + bless) before the full-suite run in verification, since `test_skillgen.py` drift checks assert the shipped tree matches expected/. Unit 5 is last. Verification runs the generator drift check plus the affected test files plus a smoke of the update flow.

## Verification

- `python -m tools.skillgen --check` — drift-free.
- `uv run pytest tests/test_skillgen.py tests/test_detect.py tests/test_extract_cli.py` — all green (suite uses `uv` per `pyproject.toml`, requires-python >= 3.10).
- Smoke: on a scratch corpus, run `detect_incremental` with and without `kind="ast"` and confirm the changed-set difference matches the issue's evidence shape (unchanged AST-only files drop out of the ast changed-set).
- `git diff` review: regen touched only the intended lines + expected/.

## Assumptions

- The reporter's evidence (kind="ast" → exact changed set) is representative; the ast mode's `if not stored_hash: changed = True` residual (files never ast-stamped are still flagged) is acceptable — after any full build or update run, `save_manifest` defaults to `kind="both"` and stamps `ast_hash`, so in practice every manifest row carries one.
- The 14 platform `update.md` copies are generated artifacts, not hand-edited (confirmed: `tools/skillgen/gen.py:126` maps `update` → `references/shared/update.md`); regen is the correct mechanism, hand-editing would fight `--check`.

## Risks

- **Low:** `--bless` rewrites all of `tools/skillgen/expected/`; if any pre-existing drift existed, bless would mask it. Mitigation: run `--check` BEFORE blessing to confirm the tree is clean pre-change, and diff the expected/ changes to confirm they are only the kind= line.
- **Low:** regen could surface unrelated drift if the working tree is not at HEAD. Mitigation: branch from current HEAD (`v8` @ 3d19463), verify `git status` clean before regenerating.
