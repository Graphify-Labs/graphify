# Jev shadow M2 candidate selection

M2 is opt-in and shadow-only. Traversal-v1 remains the production-compatible
default; no M2 evaluation calls TypeSafe.

## M2A — invalid granularity

The first attempt made explicit seeds plus every graph node whose `source_file`
was changed mandatory. It overflowed 8/10 prepared cases at 40 nodes and 9/10
at 20 nodes. This is retained as `M2A_INVALID_GRANULARITY`, not evidence
against Jev: a changed path is file-level evidence, not evidence that every
symbol in that file is mandatory.

## M2B — file-level anchors

T0 contains explicit seed ids and at most one canonical Graphify file node per
base-present changed path. A file node is resolved by explicit file-node type
when available, otherwise by Graphify's canonical file-label structure. Missing
deterministic anchors are recorded as `ANCHOR_UNRESOLVED`; symbols are never
guessed into T0.

Changed-file symbols are T1 eligible and rank ahead of unrelated expansion
nodes. The remaining eligible set is the two-hop structural neighbourhood.
Selection has stable id tie-breaking and an inspectable candidate fingerprint.

Offline references are independent of Jev and are reported in separate tiers:
R0 file anchors, R1 old-side patch-hunk-overlapping pre-change symbols where
source ranges exist, and R2 direct call/import/reference/inheritance/test
relationships from R1 symbols or explicit task seeds. File membership is
descriptive only; `contains` and `defines` edges from file anchors are not
reference evidence. Added symbols are `NOT_REFERENCEABLE`, not false negatives.

Changed-file coverage separately records base-present files, graph-represented
files, resolved or ambiguous file anchors, and graph-unrepresented files.
Ambiguous file anchors are never guessed. Historical diff extraction uses the
Graphify repository root explicitly, so evaluation is independent of shell CWD.

The repaired retained-M1 run had no T0 overflow at 8, 12, 20, or 40 nodes and
retained all resolved file anchors. The offline result is
`M2_EVIDENCE_INCONCLUSIVE`: no compact strategy is promoted and no new Jev
calls are made. Omitted changed-file symbols, omitted membership edges, and
`NOT_REFERENCEABLE` patch symbols do not by themselves reject compaction.
