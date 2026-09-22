# Jev shadow historical evaluation

`python -m tools.jev_shadow_eval` evaluates the current Graphify extractor against exact public historical PR base snapshots. The historical checkout is created with `git archive` in task-owned cache storage; the active checkout is never switched.

Run `prepare` first. It validates the committed v1 case manifest against the exact merge-base-to-head `git diff --name-status --find-renames $(git merge-base <base_sha> <head_sha>) <head_sha>` result for every case, including the persisted GitHub changed-file count, paths, statuses, and merge-base SHA. A mismatch fails closed. It fetches missing public Git objects, runs code-only Graphify extraction, and writes metadata-only dry-run Jev payloads under `${XDG_STATE_HOME:-~/.local/state}/graphify/jev-eval`. It cannot call TypeSafe. `status` and `report` are likewise offline.

Prepared evidence is bound to the evaluator `HEAD`, manifest case identity, task fingerprint, graph fingerprint, payload fingerprint, and payload graph fingerprint. A mismatch is reported as `stale`; `collect --live` records the stale state and makes zero TypeSafe calls. Every replaced record, including same-identity reruns, is retained under the state `history/` path rather than silently overwritten. The invalid direct-base→head M1 collection is archived with `SUPERSEDED_INVALID_PR_DIFF` provenance.

`collect --live` is the only networked Jev operation. It requires `TYPESAFE_API_KEY`, rechecks graph and payload fingerprints, makes one request for each prepared case, and stores raw typed answers, returned model identity, and token usage outside the repository. No source text, diff hunk, document body, or credential is included in Jev state.

The generated report is descriptive evidence only. Jev remains a sidecar experiment: it never edits `graph.json`, never contributes structural edges, and never controls normal Graphify or CI behavior.
