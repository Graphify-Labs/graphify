# Jev shadow M2 candidate selection

M2 evaluates an opt-in `ranked-v2` selector before Jev. It separates deterministic eligibility, ranking, and bounded selection: T0 consists of explicit seeds and nodes sourced from base-present changed files; the eligible pool is their two-hop structural neighbourhood; ranking uses distance, Graphify relation vocabulary, independent seed support, and a bounded degree penalty. T0 overflow is fail-closed as `SLICE_OVERFLOW`.

The production-compatible traversal selector remains the default. `tools/jev_shadow_m2.py` evaluates the `distance-v2` and `ranked-v2` variants at 8, 12, 20, and 40 nodes against retained M1 public merge-base graphs. It derives reference anchors from the PR patch categories and pre-change structural edges, never from Jev output, and never calls TypeSafe.
