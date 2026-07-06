# graphify Benchmarks

How graphify performs as conversational long-term memory and as a
code-intelligence layer, measured on an open harness with competing systems run
under identical conditions (same model, same budgets, same grader).

Last updated: 2026-07-05.

## Summary

graphify's deterministic graph plus hybrid retrieval has the best retrieval
recall on LOCOMO of any system tested, the best LOCOMO QA accuracy per dollar,
ties for the best LongMemEval score, and builds its index with zero LLM credits.
Every system was run on the same harness with one shared model (Kimi K2.6),
identical budgets, and a judge blind-validated against a second independent judge
(90.6% agreement, Cohen's kappa 0.81).

Highlights:
- LOCOMO retrieval recall@10 of 0.497, about 10x mem0 (0.048) and above BM25 (0.362).
- LOCOMO QA accuracy of 45.3%: +18 points over mem0, +14 over BM25, and within
  4.4 points of supermemory at about a tenth of supermemory's ingest cost.
- LongMemEval-S of 76%, tied for best with dense RAG.
- Zero LLM credits to build the graph, and about 11x cheaper memory ingest than
  supermemory ($1.40 vs $15.67).

## Results at a glance

| Suite | Dataset (n) | Metric | graphify | Field |
|---|---|---|---|---|
| Memory | LOCOMO (300) | QA accuracy | 45.3% | supermemory 49.7% (11x ingest cost), bm25 31.3%, mem0 27.3% |
| Memory | LOCOMO (300) | recall@10 | 0.497 | bm25 0.362, mem0 0.048 |
| Memory | LongMemEval-S (50) | QA accuracy | 76% | dense RAG 76%, hybrid 74%, mem0 70% |
| Cost | LOCOMO ingest | USD | ~$1.40 | supermemory $15.67, mem0 $3.48 |
| Cost | graph build | LLM credits | $0 | n/a |

## Harness

graphify's own harness. Competing systems (mem0, supermemory) are run as
adapters inside it, so every system sees the same model, token budget, and
grader.

```
ingest  ->  index  ->  search  ->  answer  ->  grade
(build)     (store)    (retrieve)  (Kimi K2.6) (key-fact coverage)
```

- Memory suite (`memory/`): graphify's graph retrieval vs dedicated memory
  systems (mem0, supermemory) and classic baselines (BM25, dense RAG,
  hybrid RRF). mem0 and supermemory run self-hosted as adapters, wired through
  a proxy so their LLM calls also use Kimi K2.6.
- Code suite (`crosstool/`): a fixed coding agent (Claude Opus 4.8, at most 14
  turns, a grep/read/list floor plus one code-intelligence tool) answers graded
  questions on ERPNext, a roughly 1M-LOC production repo
  ([frappe/erpnext](https://github.com/frappe/erpnext)), with a temporal
  sub-suite of 689 weekly AST checkpoints from 2011 to 2026.

## Datasets

- LOCOMO (`locomo10.json`, n=300): multi-session conversational QA.
- LongMemEval-S (n=50, English subset): long-horizon conversational memory.
- ERPNext: a large real-world Python codebase for code intelligence.

LOCOMO and LongMemEval are the same academic datasets other memory systems
report on, so results are cross-referenceable. Datasets are not redistributed;
the harness documents the expected local layout.

## Judge and grading

Answers are graded by Kimi K2.6 against a gold set of atomic key facts a correct
answer must contain:

```
coverage = (covered + 0.5 * partial) / total
```

Every verdict cites a verbatim quote from the answer, so grades are auditable
rather than one opaque score.

Judge validation: the judge was blind-validated against a second, independent
judge on a sampled set at 90.6% agreement, Cohen's kappa 0.81 (substantial
agreement). Most published memory benchmarks disclose no judge validation at
all; we publish ours so the grading itself can be audited.

## Fairness rules

- One model for every LLM role: Kimi K2.6 via Moonshot.
- One shared local embedder where the system allows it: BGE-m3 (1024-d,
  multilingual).
- Identical token budgets. Every run writes a spend ledger and respects
  `--max-spend`.
- Graphs build AST-only with no LLM (an unset API key produces zero credits);
  embeddings use a local deterministic model.

## Results: conversational memory

### LOCOMO (n=300)

Sorted by recall@10.

| System | QA accuracy | recall@10 | Ingest cost |
|---|---|---|---|
| **graphify** (graph-expand) | **45.3%** | **0.497** | ~$1.40 |
| hybrid RRF | 43.3% | 0.493 | $0 (shared index) |
| graphify (SurrealDB engine) | 43.3% | 0.485 | $0 (shared index) |
| dense RAG | 41.3% | 0.439 | $0 (shared index) |
| BM25 | 31.3% | 0.362 | $0 (shared index) |
| supermemory | 49.7% | 0.149* | $15.67 |
| mem0 | 27.3% | 0.048 | $3.48 |

Bold marks graphify's primary configuration, not the column maximum. Baselines
retrieve from the same harness-built index, so they incur no separate ingest
cost.

`*` Retrieval-recall is embedder-confounded: supermemory's self-host locks in
its own 768-d English-only embedder rather than the shared BGE-m3. The
QA-accuracy axis (a shared Kimi reader and judge over each system's hits) is the
clean comparison.

Reading: supermemory scores a few points higher on raw QA, but at about 11x the
ingest cost ($15.67 vs $1.40) and with about 3x worse retrieval recall. graphify
has the best retrieval recall on LOCOMO of any system tested, the best QA of the
systems on the shared embedder, and does it for about a tenth of supermemory's
cost. It retrieves the right memory about 10x more often than mem0 and answers
+18 points more accurately. A seed-only ablation (no graph expansion) still
scores 42.7% at $1.40 ingest, so most of the accuracy holds at the cheapest
setting.

### LongMemEval-S (n=50)

| System | QA accuracy | recall@10 |
|---|---|---|
| **graphify** (graph-expand) | **76%** | **0.844** |
| dense RAG | 76% | 0.848 |
| graphify (SurrealDB engine) | 74% | 0.833 |
| hybrid RRF | 74% | 0.822 |
| BM25 | 70% | 0.710 |
| mem0 | 70% | 0.344 |

graphify ties dense RAG for the best QA accuracy (76%); dense RAG edges it on
recall (0.848 vs 0.844). Both retrieve far more than mem0 (recall 0.344).

## Results: code intelligence

On ERPNext (a roughly 1M-LOC production repo), giving a fixed coding agent one
graphify tool lifts key-fact coverage across the graded question set (n=6) from
70.8% (a grep and read baseline) to 82.0%, at about 140K tokens per query.
graphify pays for itself in accuracy against searching raw files, and avoids the
context-stuffing anti-pattern of packing the whole repo into every turn (which
costs roughly 20x the tokens for lower coverage).

## Results: temporal (15 years of ERPNext)

689 weekly AST checkpoints, 2011 to 2026, built deterministically with no LLM.

| Checkpoint | Nodes | Edges | Files |
|---|---|---|---|
| 2011-06-08 | 3,069 | 2,900 | 1,032 |
| 2026-06-24 | 22,620 | 48,710 | 3,758 |

The graph grows about 7x in nodes and 17x in edges across the span. As the
codebase grows, plain lexical retrieval finds less of the answer while graph and
semantic retrieval scale with it, and the AST extraction itself stays stable.

## Cost and token economics

- Graph construction costs zero LLM credits. graphify extracts with tree-sitter
  (deterministic, about 40 languages) and a local embedder, so building the
  index uses no API tokens. Most memory and semantic-retrieval systems pay a
  per-document LLM ingest cost.
- Memory ingest is about 11x cheaper: graphify's LOCOMO ingest runs around
  $1.40 against supermemory's $15.67.
- Every number here is backed by a per-run spend ledger in the harness output.

## Reproducing

Set `MOONSHOT_API_KEY`. Datasets are fetched to the local layout documented in
the harness. Each run respects `--max-spend` and writes a spend ledger.

```bash
# Memory (LOCOMO). This invokes the SurrealDB-engine row (43.3%); the
# graph-expand headline (45.3%) is a separate adapter in the same harness.
python memory/runner.py --phase 3 --split locomo --n 300 \
  --adapters graphify_v1_surreal --cn natural --workers 6 --max-spend 15

# Code cross-tool (ERPNext)
python crosstool/run.py --repo erpnext --max-spend <budget>
```
