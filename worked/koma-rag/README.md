# KoMA-RAG Corpus Benchmark

A real, non-synthetic research codebase: a multi-agent autonomous-driving system (`highway_env`, forked/extended) coordinated by an LLM driver layer with retrieval-augmented few-shot memory and a verification-enhanced retrieval module (KoMA-RAG). 45 Python files, 49,800 words.

Repo: [hasnain1241/KoMA-RAG](https://github.com/hasnain1241/KoMA-RAG/tree/KoMA-V2) (`KoMA-V2` branch)

## Corpus

```
LLMDriver/          — the actual research contribution: LLM agents, RAG memory, verification
  driverAgent.py     — per-vehicle LLM driving policy
  masterAgent.py      — multi-vehicle conflict coordination
  reflectionAgent.py / reflection_choose_agent.py — self-reflection loop
  vectorStore.py      — Chroma-backed few-shot memory (DrivingMemory)
  verification.py     — Verification-Enhanced Retrieval: V = V_semantic · V_factual · V_contextual
  llm_backend.py       — provider-agnostic chat model factory
highway_env/         — the underlying driving simulator (environments, vehicles, roads, rendering)
scenario/            — scenario description + DB bridge glue between highway_env and LLMDriver
main.py              — orchestrates all of the above
*.ipynb              — experiment notebooks (not extracted — see review)
```

## How to run

```bash
pip install graphifyy
graphify install   # or your platform's install command
```

Then, in your AI coding assistant, inside a clone of the repo:

```
/graphify .
```

Or headless (what was actually run for this benchmark, no LLM key needed since this is a code-only corpus):

```bash
graphify extract . --code-only
graphify cluster-only . --no-label   # or omit --no-label with an API key configured, for named communities
```

## What to expect

- 996 nodes, 2076 edges, 65 communities (from 45 `.py` files — the 3 `.ipynb` notebooks are skipped entirely, no notebook extractor exists yet)
- 95% EXTRACTED / 5% INFERRED edges
- Token reduction: **11.9x** on average query cost (per `graphify benchmark`), up to 48.9x for architecture-level questions
- God nodes are dominated by the inherited `highway_env` simulator (`Road`, `Vehicle`, `AbstractEnv`), not the actual research contribution — see review for why
- The five `LLMDriver/` agent classes land in five different communities, disconnected from each other in the graph

Full generated report: `GRAPH_REPORT.md`. Full eval: `review.md`.
