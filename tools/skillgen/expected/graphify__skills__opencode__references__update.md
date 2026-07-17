# graphify reference: incremental update and cluster-only

## For --update (incremental re-extraction)

Run:

```bash
graphify update INPUT_PATH
```

The updater opens the active `graphify-out/graph.helix` generation, compares source hashes from native state, re-extracts changed files, removes deleted-source records, and stages a complete replacement generation. Extraction-cache changes, topology, communities, analysis, and hashes activate atomically. Concurrent readers keep their immutable snapshot; writers are excluded by the store lock.

If activation fails, the previous generation remains active. Existing obsolete-format files are ignored and never migrated or deleted.

Use `--force` only for an intentional full source rebuild; it clears cached extraction state before staging the new generation.

## For --cluster-only

Run:

```bash
graphify cluster-only INPUT_PATH
```

This reclusters the active native topology, refreshes analysis, and commits the result as a new generation while retaining the prior generation for rollback.
