# Jev memory pilot: evaluation record

## Current result

The offline harness is implemented. Synthetic tests prove bounded candidate selection, typed pair mapping, exact fallback to the unseeded Graphify query, and graph/learning-sidecar integrity. They do **not** establish that Jev improves retrieval on real memory.

No real claude-mem record or private source excerpt has been sent to Jev. No paid request has run. The real paired result and the upstream contribution decision remain pending the data and cost review described below.

## Frozen labeling rule for the real cohort

1. Select one repository with a graph pinned to its source commit. Select observations through the supported memory gateway, human-redact each summary, and keep all records and labels under a mode-0700 directory outside Git worktrees.
2. Before viewing Jev answers, label at least 30 questions: 10 calibration and at least 20 held-out. Include zero-relevant, ambiguous-label, stale-code, and unrelated-memory cases. Record gold graph node IDs and gold node–observation pairs. A node outside the ten-candidate pool remains gold; it lowers the candidate-recall ceiling.
3. Use the same ten deterministic candidates for baseline and assisted arms. Choose a relevance threshold only on calibration cases, requiring zero unsupported suggestions there. Freeze that threshold before scoring held-out cases.
4. Treat a suggestion as unsupported when its exact node–observation pair is absent from frozen gold. Compute precision@5 with denominator five; compute recall@5 only when gold is nonempty. Report zero-relevant cases separately, plus candidate recall, paired per-question differences, p50/p95 latency, actual request count, and `usage.cost`.
5. Claim a pilot gain only if held-out precision@5 rises with no unsupported suggestion displayed. These metrics concern candidate ranking; they do not prove better Graphify answer text or runtime causality.

## Synthetic metric check

The committed test fixture covers a missed gold node and a zero-relevant case. In its two-case metric example, candidate recall is 0.50, mean baseline P@5 is 0.00, mean assisted P@5 is 0.10, assisted R@5 on the nonempty case is 0.50, and one of two suggestions is unsupported. These numbers validate arithmetic only; they are not a product result.

## Live gate and contribution decision

Before a paid call, render each exact payload to mode-0600 storage, inspect every code excerpt and memory summary, show the current model price and total call/cost cap, and obtain explicit approval for that payload class and paid use. Stop on the first unexpected response; never retry an uncertain POST. Publish only aggregate held-out metrics and synthetic examples in the fork PR. An upstream PR is a separate task only if the real comparison reveals a reusable Graphify gap.
