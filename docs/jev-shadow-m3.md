# Jev shadow M3: held-out file relevance

M3 is an opt-in historical evaluation, not a production selector. It projects
retained M1 merge-base `graph.json` snapshots to normalized source-file entities
and aggregates only observed cross-file graph relations. Within-file edges are
excluded. The resulting projection fingerprint is deterministic.

Each historical PR with at least two represented, base-present changed files is
split into at most three deterministic leave-one-file-out folds. Stable SHA256
ordering of case identity plus path selects the held-out files. Added or absent
pre-change files are recorded as `NOT_PRECHANGE_REFERENCEABLE` and are not
ranking misses. The hidden target is never part of seed metadata or the Jev
payload.

The offline baseline generates candidates through structural one/two-hop
relations, shared parent paths, and shared communities. Its fixed, inspectable
ranking uses distance, direct relation strength/count, community/path overlap,
and a bounded degree penalty. Candidate-target-missing folds measure candidate
recall rather than Jev failure.

`python -m tools.jev_shadow_m3 --json` is offline and makes zero TypeSafe calls.
It reads only fingerprint-verified retained M1 graph records; it never
re-extracts historical graphs. `--live` is deliberately explicit, performs the
bounded preselected folds only, and requires `TYPESAFE_API_KEY`. Each candidate
gets exactly one candidate-bound Noul with an explicit `candidate_path` under
`jev-latest`; `baseline_score` is excluded from the outbound payload. Returned
model and token usage are recorded only in local state.

The payload includes an opaque fold ID, task objective, visible seed metadata,
candidate metadata, and cross-file structural evidence. It excludes PR number,
URL, head SHA, complete changed-file set, hidden target marker, diff hunks, raw
source, and post-change graph data. Jev output remains derived
`JEV_INFERRED`; it cannot mutate a Graphify graph or affect CI/default behavior.

Reports are written to `~/.local/state/graphify/jev-eval/reports/m3.md` (and
optional `m3.json` plus `m3-population.json`). They show candidate recall
separately from ranking, Graphify-versus-Jev Top-1/Top-3/MRR/median rank for
budgets 8, 12, and 20, per-PR/per-budget aggregation, population and payload
fingerprints, actual tokens, and one of the M3 evidence conclusions. The
earlier 36-call M3A collection is retained as
`SUPERSEDED_UNBOUND_CANDIDATE_QUESTIONS` and is excluded from the conclusion.
