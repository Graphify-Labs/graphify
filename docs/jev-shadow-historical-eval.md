# Jev shadow historical evaluation

`python -m tools.jev_shadow_eval` evaluates the current Graphify extractor against exact public historical PR base snapshots. The historical checkout is created with `git archive` in task-owned cache storage; the active checkout is never switched.

Run `prepare` first. It validates the committed v1 case manifest, fetches missing public Git objects, runs code-only Graphify extraction, and writes metadata-only dry-run Jev payloads under `${XDG_STATE_HOME:-~/.local/state}/graphify/jev-eval`. It cannot call TypeSafe. `status` and `report` are likewise offline.

`collect --live` is the only networked Jev operation. It requires `TYPESAFE_API_KEY`, rechecks graph and payload fingerprints, makes one request for each prepared case, and stores raw typed answers, returned model identity, and token usage outside the repository. No source text, diff hunk, document body, or credential is included in Jev state.

The generated report is descriptive evidence only. Jev remains a sidecar experiment: it never edits `graph.json`, never contributes structural edges, and never controls normal Graphify or CI behavior.
