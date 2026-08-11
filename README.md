# Graphify 0.9.40 long-path PR merge files

These are complete replacement files based on the supplied Graphify 0.9.40
snapshot. They preserve current upstream behavior while retaining the proposed
cross-platform filesystem I/O boundary.

## GitHub-reported conflict files

Replace these files to resolve the reported conflicts:

- `CHANGELOG.md`
- `graphify/build.py`
- `graphify/cache.py`
- `graphify/extract.py`
- `graphify/extractors/resolution.py`
- `graphify/paths.py`

## Additional compatibility files

Also replace these files. Upstream 0.9.33-0.9.40 added new filesystem calls in
these code paths without producing textual merge conflicts; leaving them as-is
would bypass the long-path adapter in parts of detection, incremental update,
watch reconciliation, dynamic-import resolution, and collision ranking.

- `graphify/cli.py`
- `graphify/dedup.py`
- `graphify/detect.py`
- `graphify/watch.py`

The files preserve repository-relative paths. Copy them into the same locations
in the PR branch; do not add them at the repository root.

## Validation performed

- Python compilation: passed
- `git diff --check`: passed
- Conflict-marker scan: passed
- Focused filesystem/path suite: 87 passed, 1 skipped
- Dependency-independent merge/regression suite: 480 passed, 1 skipped
- Sensitive-path scan: passed

The full dependency installation was unavailable in the analysis environment
because outbound package download/DNS failed. `graphify update .` was attempted
but could not run because tree-sitter was unavailable. Native Windows and the
repository's normal CI remain the authoritative final gates.

Source snapshot:

- Graphify version: 0.9.40 (unreleased)
- Supplied ZIP SHA-256: d8470c798610624ceb24bd45775a5046f8151b61d9f734c173a19a860851b342
- Supplied upstream tree: 2a912ac905b5cc8a7a7518b5a4f3c3879ac3ae10
- Proposed merged tree: 60e69faf6d955d74a314fda22712f218b88873e6
