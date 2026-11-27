# Review: epochs-of-empire

**Corpus:** `victorsilvaolav-commits/EpochsOfEmpire` @ `db26b341` (private repo — see README)
**Date:** 2026-08-29
**Run:** `graphify extract . --code-only` → `graphify cluster-only . --no-label`
(no LLM API key available in the environment, so the doc/paper pass was skipped and
communities are left as `Community N` placeholders)
**Counts:** 869 nodes · 1589 edges · 68 communities · 97% EXTRACTED / 3% INFERRED (40 INFERRED edges, avg confidence 0.82)
**Cost:** $0 (tree-sitter only; `--code-only` skipped 12 markdown docs)
**Setup:** ~2 minutes of CLI time end-to-end

## About the corpus

Epochs of Empire is a single-developer RTS prototype in **Unity 6000.5.10f1** (C#, Built-in
render pipeline). It is deliberately small and cleanly organised:

- **20 tracked `.cs` files, ~5,500 LOC**, root namespace `EoE.*`
- One responsibility per top-level folder: `Core/`, `AI/`, `Units/`, `Buildings/`,
  `Player/`, `World/`, `UI/`, `Data/`, plus `Editor/`
- **Identifiers and comments are in Spanish** (`AIPlanEstado`, `ReservaBloqueante`,
  `SinRecursos`, `IsPointerOverUi`) — a useful non-ASCII / non-English test
- Design rule from the repo's own `CLAUDE.md`: *"content is data, the engine is code"* —
  systems read multipliers and requirements, they don't branch on which epoch is active
- Two Unity Package Manager files are tracked (as Unity recommends):
  `Packages/manifest.json` and `Packages/packages-lock.json`

Because the author knows every file, there is a clean ground truth to check the headline
outputs against: *would a developer familiar with this codebase nominate the same things
as core, surprising, or worth investigating?*

This review quotes `GRAPH_REPORT.md` directly so each finding is verifiable against the
committed artifacts.

---

## Finding 1 — God nodes are accurate on a small, single-language codebase

Top god nodes, verbatim from `GRAPH_REPORT.md` (lines 85–95):

```
1. `Unit` - 81 edges
2. `AIPlayer` - 65 edges
3. `PlayerController` - 42 edges
4. `Building` - 41 edges
5. `Faction` - 38 edges
6. `HudController` - 29 edges
7. `ResourceNode` - 27 edges
8. `ResourceCost` - 25 edges
9. `BuildingDefinition` - 22 edges
10. `ResourceType` - 21 edges
```

`graphify god-nodes --top 15` continues with `GameDatabase`, `IDamageable`, `MatchManager`,
`AIKnowledge`, `UnitDefinition`.

**This list is correct.** The repo's `CLAUDE.md` architecture section, written independently,
names almost the same set as the core modules: `MatchManager` (orchestrator), `Faction`
(per-player economy — "this is what makes the AI possible"), `Unit` (state machine),
`Building`, `ResourceNode`, `PlayerController`, `AIPlayer`, `HudController`,
`GameDatabase` + `Definitions` (the data catalog). Every god node is something the
developer would themselves nominate. Nothing in the top 15 is noise.

Degree does partly track file size — `AIPlayer` is the largest file (1,141 LOC) and lands
at #2 — but it is also genuinely central: it reads `Faction`, `GameDatabase`, `AIKnowledge`,
`InfluenceMap`, `AIQueueManager`, and issues orders to `Unit` and `Building`. Unlike the
`rsl-siege-manager` case study (where six of the top ten god nodes were test factories),
this corpus has no test suite, so degree centrality points straight at the domain model.

**Takeaway for users:** on a small, single-language, test-free codebase with a clean
module split, the god-node list is trustworthy as-is.

## Finding 2 — Unity package manifests dominate the graph

341 of 869 nodes (**39%**) are extracted from two files:

```
266  Packages/packages-lock.json
 75  Packages/manifest.json
```

That is more nodes than all 20 C# files combined (~430 C# symbol nodes). `--code-only`
did **not** skip these — the `json_config` extractor classifies `*.json` as code, so the
flag that is supposed to mean "no non-code files" still ingested the entire dependency
lockfile.

The downstream effects are visible throughout the report:

- **`dependencies` is the single highest-betweenness node in the graph.** From the
  Suggested Questions section (line 302):

  > "Why does `dependencies` connect `Community 25` to `Community 7`, `Community 13`,
  > `Community 15`, `Community 16`, `Community 18`, `Community 19`, `Community 21` …
  > [26 communities in total]?"
  > _High betweenness centrality (0.119) …_

  For comparison, `Unit` scores 0.118 and `AIPlayer` 0.090. The most structurally
  "important" node graphify finds is a JSON key from a lockfile.

- **49 of the 68 communities (72%) contain only package-manifest nodes** — communities
  7, 13, 15–19, 21, 23–25, 27, 29–67 (excluding the code ones). The report's
  "Community Hubs (Navigation)" list (lines 16–83) is mostly these.

- **Every Unity module node is duplicated** — it appears once from `manifest.json` and
  once from `packages-lock.json`. `GRAPH_REPORT.md` line 208:

  ```
  ### Community 24 - "Community 24"
  Nodes (12): com.unity.modules.physics2d, com.unity.modules.physics2d, dependencies,
  depth, source, version, dependencies, depth …
  ```

  The dedup pass ("Deduplicated 18 node(s)") did not catch these because the two files
  give them different node ids.

This is not a niche corpus quirk: **every Unity project commits these two files**, and
`packages-lock.json` grows with every package added. Any Unity user running graphify will
hit this on the first run.

## Finding 3 — Community detection does not recover the folder architecture

This codebase has eight clean top-level folders, each a single concern. A developer asked
to describe the module structure would list those eight. Community detection produces 68
communities; the ones built from real code score between **0.05 and 0.16 cohesion**.
`GRAPH_REPORT.md` line 114:

```
### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (38): Conditional, List, AIQueueManager, Color, IReadOnlyList, List,
ResourceAmount, ResourceCost (+30 more)
```

Community 0 puts `AIQueueManager` (AI), `ResourceCost` / `ResourceAmount` (Core), plus
framework types `Color`, `List`, `Conditional` in one 38-node bucket at 0.05 cohesion —
the report's own "weakly interconnected" threshold. This is the same pattern the
`rsl-siege-manager` review recorded (its Finding 4), and it reproduces here on a codebase
that is an order of magnitude smaller and far more cleanly layered.

The one place community detection does well is **tiny enum-shaped clusters** — Community 42
is exactly `OrderKind: {Attack, Build, Gather, Move}` at 0.40 cohesion, Community 26 is
`{Vector2, Vector3, RTSCamera}` at 0.35. Anything larger than an enum dissolves.

**Takeaway for users:** on this corpus the cohesion scores are informative mainly as a
signal that the graph topology (dominated by fan-in to framework types and to the package
nodes from Finding 2) does not match the on-disk module structure. The "should Community N
be split?" prompts the report generates from low cohesion are not actionable here — the
communities were never coherent to begin with.

## Finding 4 — Isolated-node count is inflated by enum members and properties

The report flags **314 isolated nodes** (line 295); a direct recount of the committed
`graph.json` finds **375 nodes at degree exactly 1** (0 at degree 0). Either way, ~40% of
the graph is described as:

> "These have ≤1 connection - possible missing edges or undocumented components."

The leading examples are `Entries`, `IsFree`, `Food`, `Gold`, `Iron`. Two problems:

1. **Enum members referenced by qualified access are still isolated.** `ResourceType` is
   god node #10 (21 edges), and `ResourceType.Food` / `.Gold` / `.Iron` are used all over
   the codebase — but the members show as isolated. A `ResourceType.Food` expression is
   not creating a `uses` edge to the `Food` member node, so the members inherit only
   their single `case_of` / `contains` edge from the enum declaration.

2. **Boolean properties become standalone nodes.** `IsFree`, `IsDepleted`,
   `IsPointerOverUi` are C# expression-bodied properties. Each becomes a ≤1-edge node and
   is then labelled a "possible documentation gap."

Neither class is a documentation gap — they are live, heavily-exercised code. The label
should probably distinguish "declared but unreferenced" from "referenced only through an
expression shape the extractor doesn't bind."

## Finding 5 — `graphify query` misses conceptual questions on a small graph

Run against the committed graph:

```
graphify query "how does the AI decide what to build?"
```

```
Traversal: BFS depth=2 | Start: ['Build'] | 6 nodes found
NODE Build [src=Assets/Scripts/Units/Unit.cs loc=L157 community=Community 42]
NODE OrderKind [src=Assets/Scripts/Units/Unit.cs loc=L157 community=Community 42]
NODE Unit …
NODE Attack …  NODE Gather …  NODE Move …
EDGE OrderKind --case_of--> Build   (…and the other three OrderKind members)
```

The query keyword-matched `build` to the `OrderKind.Build` **unit-order enum member** and
returned six nodes describing that enum. The actual answer lives in `AIPlayer.cs` (decision
ticks), `AIPlan.cs`, `AIQueueManager.cs`, and `GameDatabase.cs` (what is buildable per
epoch) — none of which appear. With no semantic layer (no API key), keyword-seeded BFS has
no way to bridge "build" the concept to the AI planning code, and on a 20-file graph it
picks the wrong `Build`.

The `benchmark` command reports ~6.3x token reduction for this corpus, but the per-question
figures range 4.8x–12.1x and the corpus is only ~58k tokens naive — small enough that a
developer is often better served reading `AIPlayer.cs` directly than traversing from a
mis-seeded keyword.

## Finding 6 — `graphify explain` splits a type across its field occurrences

```
graphify explain "Faction"
```

```
Ambiguous: 'Faction' matches 4 nodes in different files.
  Assets/Scripts/Core/Faction.cs        id: assets_scripts_core_faction_eoe_core_faction
  assets_scripts_ai_aiplayer_cs_faction id: assets_scripts_ai_aiplayer_cs_faction
  Assets/Scripts/Buildings/Building.cs  id: …_building_faction
  Assets/Scripts/Units/Unit.cs          id: …_unit_faction
```

There is one `Faction` class. The other three matches are the `Faction`-typed field on
`AIPlayer`, `Building`, and `Unit`. The extractor mints a separate node for the type where
it is used as a field rather than resolving the reference to the class node. Note that
`assets_scripts_ai_aiplayer_cs_faction` also has a different id shape — `_cs_` infix, no
`eoe_` namespace segment — suggesting the C# cross-file type resolver bound that one
differently from the other two.

This lines up with open issue **#3176 (symbol name ambiguity in explain command)**. On this
corpus it means `explain` on any core type asks the user to disambiguate between the type
and its own fields.

## Finding 7 — "Surprising Connections" are mundane and all EXTRACTED

Verbatim, `GRAPH_REPORT.md` lines 97–107:

```
- `AIPlayer` --references--> `AIQueueManager`  [EXTRACTED]
- `AIPlan` --references--> `ResourceCost`  [EXTRACTED]
- `BuildingDefinition` --references--> `ResourceCost`  [EXTRACTED]
- `UnitDefinition` --references--> `ResourceCost`  [EXTRACTED]
- `AIPlayer` --references--> `ResourceType`  [EXTRACTED]
```

`AIPlayer` using `AIQueueManager` is documented in the repo's own `CLAUDE.md`.
`BuildingDefinition` / `UnitDefinition` referencing `ResourceCost` is "things have build
costs." All five are `EXTRACTED` (explicit in source), so none is a surprising *inference* —
the section recovers facts the developer already knows rather than surfacing anything
cross-cutting. Same observation as the `rsl-siege-manager` review. With only 40 INFERRED
edges in the whole graph and no semantic pass, there is little raw material for this
section to work with.

---

## What worked well on this corpus

- **God nodes (Finding 1)** — accurate top 15, no manual filtering needed.
- **Spanish / non-ASCII identifiers** — `AIPlanEstado`, `ReservaBloqueante`, `SinRecursos`,
  `SinEjecutar`, `IsPointerOverUi`, `Me` all parse and appear correctly. tree-sitter C#
  handled the mixed-language source without issue.
- **Import cycles: "None detected"** — correct. The architecture is acyclic by design
  (`MatchManager` deliberately holds no economy state; `Faction` is per-player). graphify
  did not invent a cycle.
- **`inherits` / `implements` edges** — 12 `inherits`, 2 `implements`, all correct
  (`Unit`/`Building` → `MonoBehaviour`, the `IDamageable` implementations).
- **Cost and speed** — 869 nodes in ~2 minutes at $0.
- **`graph.html`** — renders and is navigable; the force layout does visually separate the
  C# cluster from the package-manifest cloud even though community detection does not.

The underlying C# extraction is solid. The findings above are about (a) a non-code file
type slipping past `--code-only` and swamping the graph, and (b) how the report and query
layers behave on a codebase small enough that the naive approach is competitive.

---

## Suggested follow-ups

Patterns from this review that may be worth tracking upstream:

1. **Unity / UPM ignore recipe.** `Packages/packages-lock.json` and `Packages/manifest.json`
   are committed by every Unity project and produced 39% of nodes, 72% of communities, and
   the top betweenness node here. Options: ship a default `.graphifyignore` snippet for
   Unity, have `json_config` skip `*-lock.json`, or treat a recognised package manifest as
   its own node type kept out of centrality/community math. A "first run on a Unity project"
   doc section (like the tests-included note suggested by the `rsl-siege-manager` review)
   would also help.

2. **`--code-only` and JSON config files.** The flag's stated purpose is "index code
   (local AST, no API key) and skip doc/paper/image files," but it still ingests JSON
   config/lockfiles. Either document that `json_config` counts as code, or add a stricter
   mode that limits extraction to source languages.

3. **Enum-member / qualified-access edges.** `EnumType.Member` (and `const` class members
   accessed the same way) should create a `uses` edge to the member node. Without it, every
   referenced enum value is reported as an isolated "possible documentation gap" (Finding 4).

4. **Type-as-field node identity (#3176).** A `Foo`-typed field should resolve to the `Foo`
   class node rather than spawning a per-owner `…_foo` node, so `explain "Foo"` on a core
   type is not ambiguous against its own fields.

5. **Small-graph guidance.** When `benchmark` shows a low token-reduction factor and the
   corpus fits a context window, the report (or `query` output) could note that direct file
   reading is competitive, and that `query` without a semantic layer is keyword-seeded BFS.

These are observations from one corpus, not change requests — other Unity or small
single-language projects may show the same patterns.
