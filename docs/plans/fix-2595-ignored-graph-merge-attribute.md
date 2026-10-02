---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: issue-2595
---

# Fix #2595: Do not add a `.gitattributes` merge rule for ignored graph output

## Problem

`graphify hook install` registers the local `merge.graphify.*` driver and adds a `graphify-out/graph.json merge=graphify` rule to `.gitattributes`. When the graph output is ignored by Git, the attribute cannot affect merges but still dirties the repository's tracked worktree.

## Scope

- Keep registering the local Git merge driver regardless of whether the graph is ignored.
- Skip only the `.gitattributes` mutation when the configured graph path is ignored by Git.
- Preserve current behavior for tracked/non-ignored graph output, existing attributes, custom relative `GRAPHIFY_OUT`, and idempotent installation.
- Do not change uninstall behavior beyond making it safe when no attribute was added.

## Implementation units

### U1. Guard `.gitattributes` mutation for ignored graph output

**Goal:** Avoid writing a merge attribute that Git will never use.

**Files:**
- `graphify/hooks.py`
- `tests/test_hooks.py`

**Approach:**
1. Derive the repository-relative graph path used by the existing merge-attribute line.
2. Ask Git whether that path is ignored using `git -C <root> check-ignore -q <path>`.
3. Treat a successful `check-ignore` result as ignored and return a clear status after the local merge driver has already been registered.
4. Treat missing `.gitignore`, non-ignored paths, and `check-ignore` failures as non-ignored so existing behavior remains intact.
5. Keep all filesystem writes and existing idempotence logic unchanged for non-ignored paths.

**Test scenarios:**
- ignored default `graphify-out/graph.json` registers Git config but does not create or modify `.gitattributes`;
- non-ignored output still creates the attribute;
- existing unrelated attributes remain preserved;
- repeated installation remains idempotent;
- a configured relative `GRAPHIFY_OUT` is checked using the same repository-relative path.

## Risks and mitigations

- Git may be unavailable or return an error: fail open to current behavior, because the guard is a worktree-cleanliness optimization and must not block hook installation.
- Attribute path must remain repository-relative: reuse `_merge_attr_line()`'s path calculation rather than duplicating `GRAPHIFY_OUT` normalization.
- The local merge driver must still be configured for ignored output: perform the Git config writes before the optional attribute guard.

## Verification

Run the focused hook tests, then the full test suite if practical. Inspect the final diff and verify that the new regression test fails against the pre-fix behavior and passes after the change.

## Contributor

Som Samantray
