# Apache AGE Cypher Schema

This is the pinned, agent-facing schema `push_to_age()` emits. Treat it as
an API contract: review agents and quality agents query this shape
directly with plain Cypher (see docs/AGE_PLAN.md, "Consumer contract").
The label/relation sanitization and lean-vs-full property selection are
tested in `tests/test_age_exporter_unit.py`; end-to-end behavior against a
live instance is tested in `tests/test_age_integration.py`.

The identical label/relation sanitization is shared by `push_to_neo4j`,
`push_to_falkordb`, and `push_to_age` (`graphify/exporters/graphdb.py`), so
the schema below is not AGE-specific except where noted.

## Target version

Validated against **PostgreSQL 18.1 / Apache AGE 1.7.0**
(`apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb`)
during the Phase 0 compatibility spike. Bump this deliberately if the
pinned image in `tests/test_age_integration.py` changes.

## Node labels

Each node's AGE label is `file_type` capitalized and sanitized:
non-alphanumeric characters stripped, falling back to `Entity` if that
leaves nothing (`graphdb._safe_label`). E.g. `"code"` → `Code`,
`"document"` → `Document`.

## Relationship types

Each edge's AGE relationship type is `relation` upper-snake-cased and
sanitized: spaces and hyphens become `_`, remaining non-alphanumeric
characters become `_`, falling back to `RELATED_TO` if that leaves nothing
(`graphdb._safe_rel`). E.g. `"calls"` → `CALLS`, `"imports-from"` →
`IMPORTS_FROM`.

## Node properties

**Lean set (default)** — always these eight fields, in this order:

| Field             | Type    | Source                                             |
|-------------------|---------|-----------------------------------------------------|
| `id`              | string  | the graphify node id                                |
| `label`           | string  | the node's display label (falls back to `id`)       |
| `source_file`     | string  | repo-relative source path                           |
| `source_location` | string  | line/section reference within `source_file`         |
| `community`       | int     | cluster id, if community detection ran (else `null`)|
| `degree`          | int     | `G.degree(node_id)` at push time                    |
| `is_god_node`     | bool    | in `analyze.god_nodes(G, top_n=N)` at push time      |
| `in_cycle`        | bool    | `source_file` appears in `analyze.find_import_cycles(G)` |

**Full set** (`--full-props`) — the lean fields above, plus every other
scalar (`str`/`int`/`float`/`bool`) attribute present on any node in the
graph, excluding keys starting with `_`. The full field list is computed
per push (the union of keys actually present), not fixed in advance.

Evolving quality *rules* are never node properties — they go to the
`graphify_quality_findings` registry table (docs/AGE_PLAN.md) so rules can
change without the node schema becoming an unstable catch-all.

## Edge properties

**Lean set (default)**: `relation` (the original, unsanitized relation
string), `confidence` (`EXTRACTED | INFERRED | AMBIGUOUS`).

**Full set** (`--full-props`): the lean fields above, plus every other
scalar edge attribute present anywhere in the graph, excluding
`_`-prefixed keys.

## AGE-specific implementation notes (Phase 0 spike findings)

These constraints only affect how `push_to_age()` is implemented, not the
resulting schema — but they explain why AGE's write pattern differs from
the neo4j/falkordb exporters, and matter to anyone hand-writing Cypher
against this graph:

- **The graph name is always a SQL literal**, never a bind parameter —
  `cypher($1, ...)` is a syntax error in AGE. If you're issuing raw SQL
  yourself (not just Cypher through an agent client that already knows
  the graph name), keep this in mind.
- **`SET n += <param-map>` does not work** — AGE rejects a map arriving
  via a parameter or `UNWIND`-bound data ("SET clause expects a map").
  This is why every property `push_to_age()` sets is enumerated by name
  (`SET n.id = row.id, n.label = row.label, ...`) rather than spread from
  a map. Dot-path access into a parameter (`$props.label`) works fine —
  only the *map-as-a-whole* assignment is restricted.
- **`UNWIND $ids AS row` yields the scalar itself as `row`**, not a
  single-key map — `row`, not `row.id`, when `$ids` is a plain list.

## Example pinned queries

Shortest path between two named entities, evidence included:

```sql
SELECT * FROM cypher('graphify', $$
  MATCH p = shortestPath((a {label: 'Transformer'})-[*..6]-(b {label: 'LayerNorm'}))
  RETURN [n IN nodes(p) | n.id],
         [r IN relationships(p) | {relation: r.relation, confidence: r.confidence}]
$$) AS (nodes agtype, edges agtype);
```

Callers of a given symbol (reverse-dependency traversal):

```sql
SELECT * FROM cypher('graphify', $$
  MATCH (caller)-[r:CALLS]->(target {id: 'n_attention'})
  RETURN caller.id, caller.source_file, r.confidence
$$) AS (caller_id agtype, source_file agtype, confidence agtype);
```

Structural review-agent seed: god nodes touched by a branch diff (see
`graphify_branch_diff` in docs/AGE_PLAN.md for how the changed-id set is
obtained):

```sql
SELECT * FROM cypher('graphify', $$
  MATCH (n)
  WHERE n.id IN $changed_ids AND n.is_god_node = true
  RETURN n.id, n.source_file, n.degree
$$, $1) AS (id agtype, source_file agtype, degree agtype);
```
