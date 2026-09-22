# Jev shadow M4: hybrid and selective optimization

M4 is an opt-in, sidecar-only follow-up to valid M3B evidence.  It uses the
same retained historical graph snapshots and deterministic candidate machinery,
but freezes the M4 population at candidate budget 12 before contacting Jev.
It stores the target-present flag only for evaluation: every non-empty frozen
fold receives one candidate-bound Jev request during live collection, including
candidate-target-missing folds.

The request is M3 candidate-bound payload semantics: one explicit Noul question
per candidate; no Graphify baseline score, hidden target, PR metadata, diff, or
raw source.  Full `candidate_path -> Noul` vectors, payload and candidate
fingerprints, returned model, usage, and timestamp are retained only in local
state.

Offline analysis compares Graphify, Jev, and three predeclared rank fusions
(Graphify/Jev weights 0.75/0.25, 0.50/0.50, and 0.25/0.75).  Leave-one-PR-out
selects the fusion on training PRs by MRR, Top-3, then proximity to equal
weight; the held-out PR never influences its own choice.

Selective Jev uses only the pre-call normalized top-two Graphify score margin.
Its fixed threshold grid is 0.02, 0.05, 0.10, 0.20, and 0.30.  LOPO training
chooses the lowest call-rate threshold retaining at least 90% of full-Jev MRR
gain, or `ALWAYS_CALL` when none qualify.  Target-missing folds contribute to
call-rate/cost metrics but not ranking accuracy.

`python -m tools.jev_shadow_m4` is offline and reads a previously retained
collection. `--live` is explicit and requires `TYPESAFE_API_KEY`; it performs
one bounded request per non-empty frozen fold. M4 never changes Graphify's
production extraction, graph output, default behavior, or CI.

Reports are written outside the repository to
`~/.local/state/graphify/jev-eval/reports/m4.md`, `m4.json`,
`m4-population.json`, and the raw local `m4-collection.json`.
