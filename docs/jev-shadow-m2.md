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

Offline references are independent of Jev: file anchors, old-side
patch-hunk-overlapping pre-change symbols where source ranges exist, and their
direct call/import/reference/inheritance/test relationships. Added symbols are
`not_prechange_referenceable`, not false negatives.

The repaired retained-M1 run had no T0 overflow at 8, 12, 20, or 40 nodes and
retained all resolved file anchors. Its snapshots lack source ranges, so
patch-touched-symbol recall is not referenceable. The result is
`M2_EVIDENCE_REJECTS_COMPACTION`: no compact strategy is promoted and no new
Jev calls are made. A future file/subsystem-first experiment may be warranted
if range-equipped evidence continues to show weak symbol-level recall.
