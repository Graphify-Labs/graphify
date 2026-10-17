---
title: Evaluate Jev decisions over Graphify and claude-mem evidence
---

## Initial User Prompt

> mas como vamos conseguir fazer isso no graphify? Podemos fazer no nosso projeto pessoal, tipo, num fork e sugerir um PR a eles? o que acha?
>
> desenhe o piloto e leve em conseideracao a metodologia sdd

## Status

Draft for human review. This document specifies a pilot; it authorizes no paid API call, memory export, or upstream PR.

The fork's `main` is older than the upstream default `v8` and lacks `reflect` and `query --seed`. This task branch starts at the current upstream `v8`; choose a current fork target branch before opening the pilot PR.

SDD sequence: discovery of existing behavior (done) → this draft SPEC (current) → human scope review → detailed task planning → phased implementation and evaluation. The plan below is a proposed decomposition, not a claim that implementation or evaluation has run.

## Problem and outcome

Graphify already extracts structural code relationships, accepts explicit `query --seed`, and has `save-result` → `reflect` → a learning sidecar displayed by `query`/MCP. It does not establish whether a claude-mem observation refers to a particular current code node. Nor can a typed decision model safely infer new code facts from a whole graph.

The pilot must answer: **For one repository, can a small set of source-backed claude-mem observations improve discovery of relevant Graphify nodes for a question, without changing the structural graph or presenting a model guess as a fact?**

## Scope and assumptions

- Start with the public Graphify repository at a pinned `v8` commit; its `graph.json` and code are the structural sources of truth.
- Read claude-mem observations through the supported memory bridge/gateway, not its database. Use only a deliberately selected, redacted, non-sensitive fixture for the first evaluation.
- Jev is an optional typed decision step for candidate relevance. The pilot does not use Jev to parse code, create `EXTRACTED` edges, write prose, or choose actions automatically.
- The default Graphify build and query paths remain local, deterministic, and usable without Jev or an API key.
- Any live Jev call or transmission of private code/memory is a separate, explicit cost and data decision.

## Evidence from the current code

- `graphify/cli.py`: `query --seed` and graph path selection. The upstream `v8` branch already supports externally chosen starting nodes.
- `graphify/serve.py`: `_score_query`/`_pick_seeds`, `_query_graph_text`, and display of the existing learning overlay. The pilot can use these for candidate inspection without changing them.
- `graphify/ingest.py`: `save_query_result` stores question, answer, source nodes, and outcome.
- `graphify/reflect.py`: aggregates those outcomes and writes `.graphify_learning.json`, with source fingerprints and stale detection.
- `graphify/export.py`: writes `graph.json` and its structural confidence fields.

## Pilot contract

### Input

1. An existing `graph.json` built at a known commit.
2. A user question.
3. At most 20 graph-node candidates from the existing local query scoring flow.
4. At most 5 selected observations with stable IDs, dates, project names, short redacted summaries, and their source references. Begin with synthetic/public examples; add real claude-mem observations only after privacy review.

Candidate generation and path/ID matching are deterministic. Ambiguous IDs and observations about a different repo are excluded before Jev.

### Decision

For each remaining observation–node pair, ask Jev one bounded relevance question: `relevant | unrelated | insufficient_evidence`. The model receives only the question, node label/type, a bounded source excerpt, and the redacted observation summary. A response may reorder candidates or mark a link for review; it cannot alter the code graph.

Treat Jev's probability as a ranking signal, not as proof or a calibrated accuracy guarantee. `insufficient_evidence`, errors, timeouts, and unavailable credentials retain the baseline order. No automatic retry of an uncertain paid request.

### Output

A local, versioned decision sidecar **separate from** `graph.json` and `.graphify_learning.json`, containing the query, graph commit/hash, candidate IDs, observation IDs, decision, model version, redaction version, and timestamp. The pilot passes selected node IDs to the existing `graphify query --seed` command. Its displayed answer cites the code location and observation ID separately and labels model-ranked links as suggestions. Rebuilds invalidate decisions tied to stale code fingerprints. The sidecar stores no raw private memory text or API key.

## Acceptance criteria

1. **Structural integrity:** for the same fixture, `graph.json` is byte-identical before and after the optional decision step; no `EXTRACTED` or `INFERRED` edge is added by Jev.
2. **Provenance:** every displayed memory suggestion links to one observation ID and one existing node ID; absent, ambiguous, cross-repo, or stale sources are omitted or visibly marked stale.
3. **Safe fallback:** no key, model error, `insufficient_evidence`, or malformed response yields the original baseline query result and a clear diagnostic, without corrupting sidecars.
4. **Usefulness:** a blinded, human-labeled set of at least 30 questions with relevant nodes and deliberately unrelated observations compares baseline with Jev-assisted precision@5, recall@5, and false-link rate. Claim benefit only if precision@5 improves and false-link rate does not rise; report actual latency and cost per question.
5. **Privacy/cost:** a dry-run shows the exact redacted request payload and estimated call count before any live call. No automatic opt-in, key lookup fallback, or transmission of raw claude-mem records.

## Implementation plan (after SPEC review)

1. **Fixture and baseline:** capture 30 representative questions, graph SHA, expected nodes, observation IDs, and negative examples; run current `query` unchanged and record metrics.
2. **Offline harness:** in the personal fork, build a small local runner around existing Graphify scoring and `query --seed`, plus a separate sidecar. Use fixture decisions to prove ordering, provenance, stale handling, and fallback without network calls or a Graphify core change.
3. **Jev adapter:** behind explicit opt-in, submit bounded redacted state and typed questions; enforce response validation, request limits, cost logging, and no uncertain-write retry. This phase requires separate approval before its first paid request.
4. **Paired evaluation:** run the same fixture with and without Jev, review false links, measure latency/cost, and decide whether the gain supports an upstream contribution.
5. **Contribution:** if the benefit is demonstrated and a reusable Graphify gap is identified, propose only that generic gap and tests upstream. Keep the Jev/claude-mem integration and any private observations in the personal fork. The personal pilot uses one task branch and one PR to the fork's target branch; the upstream contribution is a separate, reviewed task.

## Review gates

- **Specification:** confirm the first repository, which observations may be used, and that the relevance question is the right first use case.
- **Before live Jev:** approve paid API use and the exact redacted payload class.
- **Before upstream PR:** inspect comparative results and a generic diff free of personal memory data.

## Deliberately excluded

Whole-graph upload, direct claude-mem database access, automatic edge promotion, a new vector store, new Graphify core dependencies, and autonomous execution based on a Jev score.
