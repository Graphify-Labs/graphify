# Graphify Evaluation: KoMA-RAG Corpus

**Date:** 2026-08-27
**Evaluator:** Claude (Sonnet 5), full local execution via bash tool. Nothing in this review is a simulated or inferred result; every claim was checked against the source tree and `graph.json`.
**Corpus:** [KoMA-RAG](https://github.com/hasnain1241/KoMA-RAG/tree/KoMA-V2), branch `KoMA-V2`. 45 Python files, ~49,800 words. A multi-agent LLM driving system built on a fork of `highway_env`.
**Pipeline:** `graphify extract . --code-only` followed by `graphify cluster-only . --no-label`. Local-only, no LLM key. Code extraction on this corpus did not require one.
**Verification method:** Findings were cross-checked with `grep` and direct file reads on the source, and with a Python script querying `graph.json`. Report text alone was never treated as evidence.

---

## TL;DR

Graphify produces an accurate, well-connected graph of the `highway_env` simulator fork, but it misses the research contribution that sits on top of it. The cause is a single gap: **calls made at module level (top-of-file script code, outside any function or method) produce no `calls` edges.** The orchestration in `main.py` that wires RAG memory to verification to multi-agent coordination is exactly this kind of code, so the graph presents the five core agent classes as five unrelated fragments.

**Overall: 5.8 / 10.** Fixing module-level call extraction would likely lift three of the six dimensions at once.

---

## Corpus and Output Statistics

| Metric | Value |
|---|---|
| Nodes | 996 |
| Edges | 2,076 |
| Communities | 65 (52 reported, 13 thin communities with fewer than 3 nodes omitted) |
| Edge provenance | 95% EXTRACTED, 5% INFERRED (109 edges), 0% AMBIGUOUS |
| Rationale/docstring nodes | 264 of 996 (26.5%) |
| Token reduction (`graphify benchmark`) | 11.9x average, up to 48.9x on architecture-level questions |
| Notebooks skipped | 3 (`KoMA_RAG.ipynb` 84K, `KoMA_RAG_New.ipynb` 372K, `kaggle_run_ablation.ipynb` 8K) |

---

## 1. Node and Edge Quality: 7 / 10

### What works

- **Complete file and symbol coverage.** All 45 files, every class, and every method are present and correctly scoped. Verified against `LLMDriver/`, `highway_env/vehicle/`, and `highway_env/road/`.
- **Cross-file inheritance resolves correctly.** The five-file, five-hop chain `AggressiveVehicle -> LinearVehicle -> IDMVehicle -> ControlledVehicle -> Vehicle -> RoadObject` is fully connected. The earlier `httpx` worked-example review found inheritance chains silently dropped; that regression appears fixed.
- **Intra-class call graphs are accurate.** In `verification.py`, `VerificationModule.verify_one()` correctly fans out to `semantic_score()`, `factual_score()`, and `contextual_score()`, and `factual_score()` correctly branches to `factual_score_llm()` and `factual_score_deterministic()`. This matches the verification formula documented in the module's own docstring.

### What is missing

- **Module-level code produces zero `calls` edges.** `main.py` lines 186 to 189 contain the most important wiring in the repository:

  ```python
  scored = agentMemory.retrieveMemoryWithScores(...)
  fewshot_results = verifier.filter_memories(scored, ...)
  ```

  This is the RAG retrieval to verification handoff that the codebase exists to implement. It yields no edges beyond same-file `imports` edges from `main` to each class. Confirmed directly against `graph.json`: zero `calls` edges originate from any `main.py` node. The call-graph pass appears scoped to function and method bodies only. In Python research code, a large share of entry-point logic lives at the top level, so this is a systematic blind spot rather than a corner case.

- **Rationale node density is very high.** 26.5% of all nodes are docstring text promoted to first-class nodes. `ARCHITECTURE.md` indicates this is intentional, but at this density it distorts structural metrics. Each rationale node contributes exactly one edge back to its parent and no connectivity otherwise. Excluding them from god-node degree and community statistics by default would be a reasonable change.

---

## 2. Edge Accuracy: 7 / 10

- The 95/5 EXTRACTED/INFERRED split is healthy and an improvement over the httpx corpus's 100/0. Genuine cross-file inference is happening. Example: `DriverAgent --uses--> EnvScenario` [INFERRED] correctly identifies that `driverAgent.py` consumes `scenario/envScenario.py` even where no explicit local import appears in every code path.
- All five INFERRED "surprising connections" in `GRAPH_REPORT.md` were checked against the source. All are directionally correct. No false positives were found.
- No incorrect edges were identified anywhere in the graph. The deduction is entirely for the absent category of module-level `calls` edges described in Section 1. This is a recall problem, not a precision problem.

---

## 3. Community Quality: 4 / 10

This is the weakest dimension and a direct downstream effect of the missing `main.py` call edges.

The five classes that constitute KoMA-RAG's actual contribution land in five separate communities with no direct graph link between any of them:

| Class | Role | Community | Degree |
|---|---|---|---|
| `DrivingMemory` | RAG memory | 28 | 10 |
| `VerificationModule` | Verification-enhanced retrieval | 10 | 14 |
| `DriverAgent` | Per-vehicle policy | 16 | 5 |
| `MasterAgent` | Multi-vehicle coordination | 15 | 11 |
| `ReflectionAgent` / `Reflection_Choose_Agent` | Reflection | 37 | 4 |

Together these are the paper-level architecture. The graph shows them as scattered fragments because the only place they are wired together is module-level code in `main.py`, which the extractor does not see.

The contrast with intra-file clustering is instructive. Community 10 (cohesion 0.16) correctly groups all of `VerificationModule`'s methods together. Leiden clusters well when it has edges to work with; the problem is purely the absence of edges across the orchestration boundary.

Fragmentation is also high in general: 65 communities from 45 files, with 13 thin communities omitted and several reported ones (Communities 48, 51, 55, each at 3 nodes) reading as clustering noise rather than meaningful subsystems.

---

## 4. Surprising Connections: 6 / 10

The five reported connections are all real and correctly directed:

- `DriverAgent --uses--> EnvScenario`
- `DrivingMemory --uses--> EnvScenario`
- `EnvScenario --uses--> AbstractEnv` (two instances)
- `EnvScenario --uses--> StraightLane`

These are useful. They correctly surface `scenario/envScenario.py` as the glue layer between the LLM agent code and the simulator, which is architecturally accurate.

The most important connection in the codebase, `DrivingMemory` retrieval output feeding `VerificationModule` filtering, never appears. It cannot be surfaced as surprising because it is not in the graph at all.

---

## 5. God Nodes: 5 / 10

Top 10 by degree: `Road` (58), `Vehicle` (56), `AbstractEnv` (52), `RoadNetwork` (51), `IDMVehicle` (50), `AbstractLane` (39), `MDPVehicle` (38), `StraightLane` (34), `ControlledVehicle` (33), `EnvScenario` (30).

Every entry comes from the inherited `highway_env` simulator. The five agent classes have degrees of 4 to 14, roughly an order of magnitude lower. A developer opening this report cold would conclude the repository is a traffic simulator with an LLM attached, when the reverse is true: `highway_env` is scaffolding and the RAG/verification/multi-agent layer is the point.

This is not strictly an extraction error. The simulator genuinely has more raw connectivity. It is a usability finding: for repositories that fork or wrap a larger upstream library, which is common, god-node ranking needs some way to weight or filter toward the repository's own top-level modules versus vendored or forked dependencies.

---

## 6. Overall Usefulness: 6 / 10

### Where it helps

- Understanding the `highway_env` fork's class hierarchy (vehicles, lanes, actions, observations). Inheritance, method ownership, and cross-file references all check out.
- Understanding the internal structure of any single `LLMDriver/` module. The verification call graph and the vectorStore method inventory are precise and faster than reading the file.
- Token reduction of 11.9x to 48.9x is a real, verified measurement, not a report artifact.

### Where it falls short

- The research narrative (RAG memory, then verification, then multi-agent coordination) is invisible for the reasons above.
- The three Jupyter notebooks are skipped with only a one-line CLI log message. For a research repository, a meaningful fraction of experiment and ablation logic likely lives there. `GRAPH_REPORT.md` does not mention the omission, so a reader of the report alone would not know 464K of notebook content was excluded.

---

## Recommendations, in priority order

1. **Extract calls from module-level script code, not only from function and method bodies.** This is the single highest-leverage fix. It would add real structural signal linking the five agent classes and would plausibly raise Community Quality, Surprising Connections, and God Nodes together, since all three are symptoms of the same missing signal.
2. **Report skipped notebooks in `GRAPH_REPORT.md` itself.** A line such as "3 notebooks skipped, estimated N words" is enough. Better still, a notebook extractor that treats code cells as module-level script code (which would then benefit from fix 1).
3. **Distinguish first-party modules from vendored or forked dependencies in god-node ranking.** A heuristic based on directory depth, a user-supplied include pattern, or git history would all work.
4. **Exclude rationale nodes from structural metrics by default.** Keep them in the graph, but do not count them toward degree or community size unless explicitly requested.

---

## Scores Summary

| Dimension | Score | Key finding |
|---|---|---|
| Node and edge quality | 7 / 10 | Inheritance and intra-class call graphs accurate; module-level calls invisible |
| Edge accuracy | 7 / 10 | Healthy 95/5 split, no false positives; recall gap only |
| Community quality | 4 / 10 | Five core research classes land in five disconnected communities |
| Surprising connections | 6 / 10 | All five reported are real; the most important one is absent from the graph |
| God nodes | 5 / 10 | Ranking dominated by vendored `highway_env` |
| Overall usefulness | 6 / 10 | Excellent for the simulator fork; misses the research architecture |
| **Overall** | **5.8 / 10** | One root cause underlies every weak dimension |

---

## Reproducibility

```bash
git clone -b KoMA-V2 https://github.com/hasnain1241/KoMA-RAG
cd KoMA-RAG
graphify extract . --code-only
graphify cluster-only . --no-label
graphify benchmark
```

To confirm the central finding, query `graph.json` for edges of type `calls` whose source node belongs to `main.py`. The expected count is zero.
