# Case Study: Epochs of Empire (Unity / C# RTS prototype)

A graphify dry-run against **Epochs of Empire**, a single-developer real-time-strategy
prototype built in **Unity 6000.5.10f1** (C#, Built-in render pipeline). Captured here as a
worked example of running graphify on a small, cleanly-layered, single-language codebase —
and on a **Unity** project specifically, which is not represented elsewhere in `worked/`.

**Corpus:** `EpochsOfEmpire` @ commit `db26b341` (private repo — see note below)
**Date:** 2026-08-29
**Findings:** [`review.md`](./review.md)
**Raw artifacts:** [`GRAPH_REPORT.md`](./GRAPH_REPORT.md), [`graph.html`](./graph.html), [`graph.json`](./graph.json), [`manifest.json`](./manifest.json)

> **The source repo is private** and cannot be cloned to reproduce this run byte-for-byte.
> The committed artifacts and `review.md` stand on their own: `review.md` describes the
> codebase structure in enough detail to follow every finding, and each finding quotes
> `GRAPH_REPORT.md` verbatim. The corpus shape (20 C# files, ~5,500 LOC, namespace `EoE.*`,
> folders `Core/ AI/ Units/ Buildings/ Player/ World/ UI/ Data/ Editor/`, Spanish
> identifiers) is enough to judge the outputs against.

## The corpus in one paragraph

~20 tracked `.cs` files, ~5,500 LOC, one concern per top-level folder, no test suite,
identifiers and comments in Spanish. Design rule: *content is data, engine is code* — the
systems read multipliers/requirements and never branch on the current epoch. Two Unity
Package Manager files (`Packages/manifest.json`, `Packages/packages-lock.json`) are tracked,
as Unity recommends.

## How this run was done

No LLM API key was available in the environment, so this is an **AST-only, $0** run and
communities are left unlabelled (`Community N`).

```powershell
# 1. Install the CLI (PyPI package is `graphifyy` -- double-y; command is `graphify`)
uv tool install graphifyy
graphify --version

# 2. From the Unity project root
graphify extract . --code-only        # tree-sitter only, no API calls
graphify cluster-only . --no-label     # cluster + generate GRAPH_REPORT.md, skip LLM naming

# 3. Inspect
code   .\graphify-out\GRAPH_REPORT.md
start  .\graphify-out\graph.html
```

To reproduce on **any** Unity project, run the same two commands from the folder that
contains `Assets/` and `Packages/`.

## What to expect (this corpus)

- **869 nodes, 1,589 edges, 68 communities**, 97% EXTRACTED / 3% INFERRED, $0
- **God nodes are accurate**: `Unit`, `AIPlayer`, `PlayerController`, `Building`, `Faction`,
  `HudController`, `ResourceNode`, `ResourceCost`, `BuildingDefinition`, `ResourceType` --
  every one is a real core abstraction (no test-factory noise, because there is no test suite)
- **Unity package manifests dominate**: `Packages/packages-lock.json` +
  `Packages/manifest.json` produce **39% of all nodes**, **72% of communities**, and the
  single highest-betweenness node in the graph (`dependencies`, 0.119 -- above `Unit` at
  0.118). `--code-only` does not skip them.
- **Community detection does not recover the 8-folder structure** -- real-code communities
  score 0.05-0.16 cohesion
- **~40% of nodes reported "isolated"** -- inflated by enum members accessed as
  `ResourceType.Food` and by boolean properties
- `benchmark` reports ~6.3x token reduction, but the corpus is only ~58k tokens naive

See [`review.md`](./review.md) for the detailed assessment, with report quotes.

## What's in this directory

| File | What it is |
|---|---|
| `README.md` | This file -- corpus description + how the run was done |
| `review.md` | Findings against the headline outputs in `GRAPH_REPORT.md` |
| `GRAPH_REPORT.md` | Raw graphify report (god nodes, communities, surprising connections, suggested questions) |
| `graph.html` | Interactive force-directed visualization |
| `graph.json` | Underlying graph data used by `graphify query` / `god-nodes` / `explain` |
| `manifest.json` | Per-file extraction record |

The AST cache (`graphify-out/cache/`) is regenerable and not committed.

## Why this corpus

- **Unity / C# game project** -- a codebase type not covered by the existing worked examples
  (`httpx` Python, `rsl-siege-manager` Python+TS, `karpathy-repos`, `mixed-corpus`).
- **Small and cleanly layered** -- 20 files, one concern per folder, no tests. Gives a clear
  ground truth: the god-node list and the community structure can be checked against what
  the author would draw on a whiteboard.
- **Spanish identifiers throughout** -- exercises non-English / non-ASCII symbol extraction.
- **Tracked Unity Package Manager files** -- surfaces how `manifest.json` /
  `packages-lock.json` are treated, which affects every Unity user.

## Reference

- graphify repo: https://github.com/safishamsi/graphify
- graphify PyPI: https://pypi.org/project/graphifyy/
