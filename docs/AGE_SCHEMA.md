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

## Agent contract (docs/AGE_PLAN.md Phase 5)

This section is the actual API review/quality agents build against, pinned
and tested in `tests/test_age_agent_queries_integration.py`.

### Review agent

- **Branch-diff seed selection**: the changed-id set for a push is never
  recomputed from the graph itself -- it's read directly off
  `graphify_branch_diff` (plain SQL, not Cypher), split by `kind`. See
  "Branch-diff seed selection" below. Node ids from `node_add`/`node_change`
  rows are looked up in the branch's *current* materialized graph (or the
  default graph, for a default-branch push); `node_del` rows carry their
  full last-known `payload` and have nothing left to look up.
- **Traversal direction**: every relation is directed `source → target`
  exactly as the extractor recorded it (`a --CALLS--> b` means "a calls
  b"), regardless of push_to_age()'s undirected `nx.Graph` internals --
  `MERGE (a)-[r:REL]->(b)` always uses `a = source_id`, `b = target_id`.
  A **reverse-dependency** query ("who calls/imports/uses X") therefore
  matches with `X` as the traversal target: `MATCH (caller)-[r:REL]->
  (target {id: X})`. A **forward** query ("what does X call/import/use")
  matches with `X` as the source: `MATCH (target {id: X})-[r:REL]->
  (dependency)`.
- **Required evidence fields** in any result a review agent surfaces:
  `id` (or `caller.id`/`target.id` for a traversal), `source_file`,
  `source_location` (from the node; omit if not applicable to the query
  shape), `relation` and `confidence` (from the edge, when the result
  crosses an edge), and the **branch/base commit** the result was
  evaluated against (`graphify_branches.head_commit_sha`/`base_commit_sha`
  for the branch queried, or `graphify_snapshots.commit_sha` for the
  default branch) -- a finding without a pinned commit is not reproducible.
- **Depth caps, result limits, statement timeouts**: always bound a
  traversal's hop count (`[*1..N]`, never unbounded `[*]`), always `LIMIT`
  the result set, and always set `statement_timeout` before querying an
  AGE graph you don't control the size of -- a materialized branch graph
  can be arbitrarily large. See "Depth-capped, limited, timed-out
  traversal" below for the pinned pattern.

### Quality agent

Structural properties (`degree`, `is_god_node`, `in_cycle`) live on nodes
because they're cheap, stable, and recomputed on every push. Rule-based
findings (an evolving, versioned rule set -- "this function is too long,"
"this import is unused") are never node properties: they go to
`graphify_quality_findings`, keyed by `(repository_id, commit_sha,
node_id, rule)`. This boundary exists so adding, changing, or retiring a
rule never requires a schema migration or a `push_to_age()` change --
findings are just rows. See "Quality findings joined with structural
properties" below for how the two are combined at query time.

## Parsing agtype vertex/edge/path values

A returned vertex, edge, or path is **not plain JSON** -- psycopg hands it
back as the agtype text form, which appends a type suffix after each
top-level object: `{"id": ..., "label": "Code", "properties": {...}}::vertex`,
`{...}::edge`, or a `path` whose whole array carries `::path`. `json.loads`
on the raw string fails on the `::vertex`/`::edge`/`::path` suffixes, and a
naive non-greedy regex (`\{.*?\}::`) breaks on the nested `"properties":
{...}` object inside each vertex/edge. Depth-aware splitting handles it:

```python
import json

def parse_agtype_objects(raw: str) -> list[tuple[dict, str | None]]:
    """[(parsed_object, 'vertex' | 'edge' | None), ...] in order."""
    results, depth, start = [], 0, None
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj = json.loads(raw[start:i + 1])
                j = i + 1
                kind = None
                if raw[j:j + 2] == "::":
                    k = j + 2
                    while k < n and raw[k].isalpha():
                        k += 1
                    kind = raw[j + 2:k]
                results.append((obj, kind))
                start = None
        i += 1
    return results
```

## Example pinned queries

Shortest path between two named entities, evidence included. **AGE 1.7.0
has no `shortestPath()` function** -- confirmed live (`syntax error at or
near "shortestPath"`), not a documentation guess -- so this orders
variable-length matches by `length(p)` instead. It also returns the whole
path `p` rather than projecting node ids via a list comprehension
(`[n IN nodes(p) | n.id]`): that projection form fails with `could not
find properties for n` on this version too. The client parses `p`'s JSON
directly -- AGE already embeds each vertex/edge's full `properties` object
in the path payload, e.g. `[{"id":...,"label":"Code","properties":
{"id":"n_transformer",...}}::vertex, {...}::edge, {...}::vertex]::path`:

```sql
SELECT * FROM cypher('graphify', $$
  MATCH p = (a {label: 'Transformer'})-[*..6]-(b {label: 'LayerNorm'})
  RETURN p
  ORDER BY length(p) ASC
  LIMIT 1
$$) AS (p agtype);
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

Cross-branch comparison (docs/AGE_PLAN.md Phase 4): a materialized
feature-branch graph (`<repo_graph>__<branch>`) and the default-branch
graph are ordinary, independently addressable AGE graphs, so a structural
comparison is just two `cypher()` calls joined in one SQL statement --
no cross-graph Cypher syntax needed. Example: node ids present in the
feature branch but not in the default branch (a cheap structural
approximation of "what's new in this PR" alongside the authoritative
`graphify_branch_diff` rows):

```sql
SELECT feature.id FROM
  cypher('graphify__feature', $$ MATCH (n) RETURN n.id $$) AS feature(id agtype)
  LEFT JOIN
  cypher('graphify', $$ MATCH (n) RETURN n.id $$) AS base(id agtype)
  ON feature.id = base.id
WHERE base.id IS NULL;
```

Branch-diff seed selection (docs/AGE_PLAN.md Phase 5): the changed-id set
for a review agent's seed comes straight from `graphify_branch_diff` --
plain SQL, no Cypher, no need to diff the graph yourself. `payload->>'id'`
covers `node_add`/`node_del`/`node_change` rows uniformly (a `node_change`
row's payload is `{"id": ..., "old": {...}, "new": {...}}`, so `id` is
still a top-level key):

```sql
SELECT kind, payload->>'id' AS node_id
FROM graphify_branch_diff
WHERE repository_id = %(repository_id)s
  AND branch = %(branch)s
  AND generation = %(generation)s  -- the branch's *active* generation
ORDER BY seq;
```

Depth-capped, limited, timed-out traversal (docs/AGE_PLAN.md Phase 5): the
pinned pattern for querying a graph of unknown size (any materialized
branch graph, not just the durable default-branch one) --  a bounded hop
count, an explicit result cap, and a statement timeout, all mandatory:

```sql
SET statement_timeout = '5s';
SELECT * FROM cypher('graphify', $$
  MATCH (caller)-[:CALLS*1..3]->(target {id: 'n_attention'})
  RETURN caller.id, caller.source_file
  LIMIT 50
$$) AS (caller_id agtype, source_file agtype);
```

Quality findings joined with structural properties (docs/AGE_PLAN.md
Phase 5): structural node properties come from AGE; rule-based findings
come from plain SQL. `n.id::text` on an agtype string returns a
double-quoted JSON string (`'"n_attention"'`), so match it against
`graphify_quality_findings.node_id` with the quotes stripped, not a bare
`=`:

```sql
SELECT n.id, n.source_file, n.degree, f.rule, f.severity
FROM cypher('graphify', $$
  MATCH (n) WHERE n.is_god_node = true
  RETURN n.id, n.source_file, n.degree
$$) AS n(id agtype, source_file agtype, degree agtype)
LEFT JOIN graphify_quality_findings f
  ON f.node_id = trim(both '"' from n.id::text)
  AND f.repository_id = %(repository_id)s
  AND f.commit_sha = %(commit_sha)s;
```

(`n.is_god_node` isn't re-selected -- the `WHERE` clause inside the Cypher
body already guarantees it's `true` for every row here. Add it to both the
`RETURN` clause and the `AS n(...)` column list if you need it back out.)
