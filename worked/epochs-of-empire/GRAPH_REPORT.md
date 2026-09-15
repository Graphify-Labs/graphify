# Graph Report - EpochsOfEmpire  (2026-08-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 869 nodes · 1589 edges · 68 communities (46 shown, 22 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 40 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `db26b341`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67

## God Nodes (most connected - your core abstractions)
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

## Surprising Connections (you probably didn't know these)
- `AIPlayer` --references--> `AIQueueManager`  [EXTRACTED]
  Assets/Scripts/AI/AIPlayer.cs → Assets/Scripts/AI/AIQueueManager.cs
- `AIPlan` --references--> `ResourceCost`  [EXTRACTED]
  Assets/Scripts/AI/AIPlan.cs → Assets/Scripts/Core/ResourceTypes.cs
- `BuildingDefinition` --references--> `ResourceCost`  [EXTRACTED]
  Assets/Scripts/Data/Definitions.cs → Assets/Scripts/Core/ResourceTypes.cs
- `UnitDefinition` --references--> `ResourceCost`  [EXTRACTED]
  Assets/Scripts/Data/Definitions.cs → Assets/Scripts/Core/ResourceTypes.cs
- `AIPlayer` --references--> `ResourceType`  [EXTRACTED]
  Assets/Scripts/AI/AIPlayer.cs → Assets/Scripts/Core/ResourceTypes.cs

## Import Cycles
- None detected.

## Communities (68 total, 22 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (38): Conditional, List, AIQueueManager, Color, IReadOnlyList, List, ResourceAmount, ResourceCost (+30 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (19): AIPlan, AIPlanEstado, Ejecutado, Pendiente, ReservaBloqueante, SinEjecutar, SinRecursos, Building (+11 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (22): Building, Collider, Color, Dictionary, Renderer, RuntimeInitializeOnLoadMethod, Transform, Vector3 (+14 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (17): Vector2, BuildingDefinition, Building, Camera, Collider, Faction, List, Rect (+9 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (22): Color, Faction, List, Renderer, RuntimeInitializeOnLoadMethod, Transform, Vector3, Building (+14 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (22): AIDifficulty, Dificil, Facil, Normal, UnitState, Attacking, Building, Gathering (+14 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (16): Building, Color, List, Unit, EpochAdvance, Progress, Faction, Epoch (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (29): com.unity.modules.physics, com.unity.modules.terrain, com.unity.modules.physics, com.unity.modules.terrain, dependencies, depth, source, version (+21 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (12): Building, Color, Faction, Rect, Texture2D, HudController, IsPointerOverUi, Me (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (21): Faction, List, Renderer, RuntimeInitializeOnLoadMethod, Transform, Unit, AssignedResource, AttackDamage (+13 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (14): Dictionary, IReadOnlyList, List, Vector3, AIKnowledge, Sightings, EnemySighting, Transform (+6 more)

### Community 11 - "Community 11"
Cohesion: 0.16
Nodes (10): Vector3, InfluenceMap, Ally, Enemy, Threat, LayerType, Ally, Enemy (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (12): Building, Faction, IReadOnlyList, List, Vector3, MatchManager, Ai, Factions (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (21): com.unity.dt.app-ui, com.unity.modules.androidjni, com.unity.modules.screencapture, com.unity.modules.androidjni, com.unity.modules.screencapture, dependencies, depth, source (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (7): List, RuntimeInitializeOnLoadMethod, Vector3, ResourceNode, IsDepleted, MonoBehaviour, Object

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (18): com.unity.modules.subsystems, com.unity.modules.jsonserialize, com.unity.modules.jsonserialize, dependencies, depth, source, version, dependencies (+10 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (16): com.unity.modules.uielements, com.unity.modules.uielements, depth, source, version, dependencies, depth, source (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.14
Nodes (14): com.unity.modules.adaptiveperformance, com.unity.modules.ai, com.unity.modules.director, com.unity.modules.particlesystem, com.unity.modules.terrainphysics, dependencies, com.unity.modules.adaptiveperformance, com.unity.modules.ai (+6 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (15): dependencies, depth, source, version, dependencies, depth, source, version (+7 more)

### Community 19 - "Community 19"
Cohesion: 0.13
Nodes (15): dependencies, depth, source, version, dependencies, depth, source, version (+7 more)

### Community 20 - "Community 20"
Cohesion: 0.23
Nodes (4): Building, Order, Order, OrderKind

### Community 21 - "Community 21"
Cohesion: 0.14
Nodes (14): com.unity.ext.nunit, com.unity.modules.imgui, com.unity.modules.imgui, dependencies, depth, source, version, dependencies (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (12): com.unity.modules.hierarchycore, dependencies, depth, source, version, dependencies, depth, source (+4 more)

### Community 24 - "Community 24"
Cohesion: 0.17
Nodes (12): com.unity.modules.physics2d, com.unity.modules.physics2d, dependencies, depth, source, version, dependencies, depth (+4 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (11): dependencies, depth, source, version, dependencies, depth, source, version (+3 more)

### Community 26 - "Community 26"
Cohesion: 0.35
Nodes (3): Vector2, Vector3, RTSCamera

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (11): com.unity.collections, dependencies, depth, source, url, version, depth, source (+3 more)

### Community 29 - "Community 29"
Cohesion: 0.20
Nodes (10): dependencies, depth, source, version, dependencies, depth, source, version (+2 more)

### Community 30 - "Community 30"
Cohesion: 0.20
Nodes (10): dependencies, depth, source, version, dependencies, depth, source, version (+2 more)

### Community 31 - "Community 31"
Cohesion: 0.20
Nodes (10): dependencies, depth, source, version, dependencies, depth, source, version (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.25
Nodes (8): com.unity.nuget.mono-cecil, dependencies, dependencies, depth, source, url, version, com.unity.nuget.mono-cecil

### Community 33 - "Community 33"
Cohesion: 0.29
Nodes (7): com.unity.mathematics, dependencies, dependencies, depth, source, version, com.unity.mathematics

### Community 34 - "Community 34"
Cohesion: 0.29
Nodes (7): com.unity.nuget.newtonsoft-json, dependencies, depth, source, url, version, com.unity.nuget.newtonsoft-json

### Community 35 - "Community 35"
Cohesion: 0.29
Nodes (7): com.unity.modules.physicscore2d, com.unity.modules.physicscore2d, dependencies, depth, source, version, com.unity.modules.physicscore2d

### Community 36 - "Community 36"
Cohesion: 0.40
Nodes (3): BuildScript, EoE.EditorTools, MenuItem

### Community 37 - "Community 37"
Cohesion: 0.33
Nodes (6): com.unity.2d.sprite, dependencies, depth, source, version, com.unity.2d.sprite

### Community 38 - "Community 38"
Cohesion: 0.33
Nodes (6): com.unity.burst, depth, source, url, version, com.unity.burst

### Community 39 - "Community 39"
Cohesion: 0.33
Nodes (6): com.unity.test-framework, depth, dependencies, source, version, com.unity.test-framework

### Community 40 - "Community 40"
Cohesion: 0.33
Nodes (6): com.unity.test-framework.performance, depth, source, url, version, com.unity.test-framework.performance

### Community 41 - "Community 41"
Cohesion: 0.33
Nodes (6): dependencies, depth, source, url, version, com.unity.ai.assistant

### Community 42 - "Community 42"
Cohesion: 0.40
Nodes (5): OrderKind, Attack, Build, Gather, Move

### Community 43 - "Community 43"
Cohesion: 0.40
Nodes (5): dependencies, depth, source, version, com.unity.modules.accessibility

### Community 44 - "Community 44"
Cohesion: 0.40
Nodes (5): dependencies, depth, source, version, com.unity.modules.adaptiveperformance

### Community 45 - "Community 45"
Cohesion: 0.40
Nodes (5): dependencies, depth, source, version, com.unity.modules.particlesystem

### Community 46 - "Community 46"
Cohesion: 0.40
Nodes (5): dependencies, depth, source, version, com.unity.modules.wind

## Knowledge Gaps
- **314 isolated node(s):** `Entries`, `IsFree`, `Food`, `Gold`, `Iron` (+309 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `dependencies` connect `Community 25` to `Community 7`, `Community 13`, `Community 15`, `Community 16`, `Community 18`, `Community 19`, `Community 21`, `Community 23`, `Community 24`, `Community 27`, `Community 29`, `Community 30`, `Community 31`, `Community 32`, `Community 33`, `Community 34`, `Community 35`, `Community 37`, `Community 38`, `Community 39`, `Community 40`, `Community 41`, `Community 43`, `Community 44`, `Community 45`, `Community 46`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `Unit` connect `Community 9` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 10`, `Community 42`, `Community 12`, `Community 14`, `Community 20`, `Community 22`, `Community 28`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `AIPlayer` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 9`, `Community 10`, `Community 14`, `Community 20`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **What connects `Entries`, `IsFree`, `Food` to the rest of the system?**
  _314 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05182443151771549 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07627118644067797 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.10993657505285412 - nodes in this community are weakly interconnected._