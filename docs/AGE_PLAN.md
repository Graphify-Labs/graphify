# Apache AGE Support — Implementation Plan

Status: v15 (2026-09-06) — Phases 0-6 implemented and validated live
against `apache/age` (PostgreSQL 18.1, AGE 1.7.0): compatibility spike,
`push_to_age()` exporter, the repository identity/ownership registry,
logical base snapshots + incremental default-branch sync, non-default
branches (commit-anchored diff chains, lazy materialization, reaping),
the pinned agent query contract, and AGE-backed retrieval for
`graphify query`/`path`/`explain` (`serve.py`'s MCP/HTTP server is
explicitly deferred -- see Phase 6). A pre-existing edge-direction bug
affecting all three graph-DB exporters and `graph_diff()` was found and
fixed while validating Phase 5's queries (see Phase 5's checklist).
`bytes_used` remains an unpopulated reserved column (see Open questions);
`extraction_config_hash` is plumbed through, populated by the CLI
(`age_registry.extraction_config_hash()`), and enforced; its inputs
(`--full-props` + an optional caller fingerprint) are still coarser than a
full extraction-settings hash (see Open questions).

**Post-review corrections (v15)**: an external review of the branch was
not ready-to-merge, citing several correctness gaps. All were fixed:
a critical default-AGE-graph-name collision across repositories (every
repo pushed without `--graph-name` shared the literal graph `"graphify"`,
so a second repo's deletion-safe reconcile deleted the first repo's data
-- now derived from `repository_id` by default, and branch
materialize/reap resolve the registered name instead of re-defaulting);
incremental sync silently dropping every changed/new edge for a normal
lowercase relation (an AGE-sanitized `_safe_rel()` group key was compared
against the raw, un-sanitized diff relation string); a `file_type` change
losing that node's otherwise-unchanged edges (its `DETACH DELETE` removes
every incident edge, but they weren't being re-upserted); schema/config
compatibility now actually enforced (branch rows persist
`graphify_version`/`schema_version`/`extraction_config_hash`, snapshot
reconstruction and base-snapshot resolution filter by them, and a push
whose schema/config diverges from what its branch already has on record
is rejected rather than spliced in); a non-atomic rebase that could leave
`graphify_branches` claiming `materialized = true` for an AGE graph
already dropped (the drop and the generation-transition registry update
are now one transaction); concurrent branch pushes were unserialized
(`push_branch` now holds the same per-`(repository_id, branch)` advisory
lock `materialize_branch`/`reap_branch` already used); and a same-pair
edge that only reversed direction produced no diff at all (`graph_diff()`
excludes `_src`/`_tgt` from the properties it compares, so a pure
reversal looked like no change -- now reported as an explicit
remove-old-direction + add-new-direction pair, since `push_to_age`'s
`MERGE (a)-[r:REL]->(b)` is directional and would otherwise leave a stale
edge next to a newly created one). `reap_branch`'s idle-time semantics
were also called out as measuring push-recency, not query-inactivity --
correct as designed, so only the docs/CLI wording were made honest about
that rather than adding unimplemented access-tracking machinery.

**Second review pass (still v15)**: two more gaps, both in `graphify
export age`'s CLI plumbing rather than the underlying `age_branches`/
`age_snapshots` machinery: an unregistered repository's first push used
to unconditionally treat whatever branch was currently checked out as the
default branch, silently misclassifying a feature branch pushed first
(fixed with a new `--default-branch` flag plus `refs/remotes/origin/HEAD`
resolution -- `age_registry.resolve_default_branch_ref()`). The first fix
still fell back to a warn-and-assume when neither resolved, which a third
review pass correctly called out as preserving the exact original bug
(just with a warning printed first) for a decision that's persistent and
effectively impossible to undo cleanly once graphs/diff chains exist under
it -- this is now a hard error (exits nonzero, pushes nothing) instead:
unregistered + no `--default-branch` + no resolvable `origin/HEAD` refuses
outright, telling the caller to pass `--default-branch`, run
`git remote set-head origin -a`, or use `--no-register` to opt out of
registry/multi-branch sync entirely. This does mean a fresh, never-cloned
repo's very first `graphify export age --push` now requires
`--default-branch` (or a remote with `HEAD` set) even in the common single-
branch case -- an intentional, documented trade of a small one-time
friction cost against a footgun that corrupts a durable, hard-to-fix data
model decision; and `extraction_config_hash` was defined and enforced in
`age_branches`/
`age_snapshots` but the CLI never actually computed or passed one, so the
check it fed was always a no-op in practice (fixed with
`age_registry.extraction_config_hash()`, a deterministic hash of
`--full-props` plus an optional caller-supplied `--extraction-config` /
`GRAPHIFY_EXTRACTION_CONFIG_HASH` fingerprint, now threaded through every
CLI call to `push_branch`/`record_snapshot`/`latest_snapshot_graph`; the
`extraction_config_hash` filter was also added to `snapshot_graph_by_id`
and `record_snapshot`'s own internal reconstruction, which previously
filtered on `schema_version` alone). Two more bugs surfaced live while
testing the `--default-branch` fix through the real CLI path (previously
masked because every branch test pre-registered the repository and passed
an explicit `cwd`, sidestepping both): `age_branches._extract_graph_at_commit`
unconditionally did `cwd=str(cwd)` for its `git worktree` subprocess calls,
turning a `None` cwd (the CLI's default -- it never passes one) into the
literal string `"None"`; and the feature-branch push path never upserted
`graphify_repos` before writing rows that foreign-key onto it, so an
unregistered repo's first push -- if it happened to be a feature branch --
failed outright with `ForeignKeyViolation` instead of registering first,
the way a default-branch push already did. Registration now happens once,
before dispatching to either push path.
Scope: add Apache AGE as a graph-database sink, with cost-efficient sync,
multi-branch support, a multi-repo registry with ownership, and storage
optimization. Primary consumers are external agents (code review, code
quality) that write their own Cypher against the AGE instance.

## Background

graphify already has a graph-DB export pattern: `push_to_neo4j` and
`push_to_falkordb` in `graphify/exporters/graphdb.py`, wired to
`graphify export neo4j|falkordb --push URI` in `cli.py`. Both do a
full-graph upsert with one round trip per node/edge.

Relevant existing machinery:

- `graphify/global_graph.py` — local multi-repo merge into
  `~/.graphify/global-graph.json` with `repo_tag` node-id prefixing and a
  JSON manifest (no owner/branch tracking yet).
- `graphify/analyze.py::graph_diff(G_old, G_new)` — node/edge add/remove
  deltas (no property-change detection yet; must be extended, see below).
- `graphify/cache.py` — content-hash extraction caching (client-side
  incremental extraction is already solved).
- `graphify/pg_introspect.py` + the `postgres` extra — psycopg is already
  an established optional dependency.
- `graphify/serve.py`, `query/path/explain` — retrieval currently loads
  `graph.json` into NetworkX.

## Design decisions (settled)

1. **Materialized graphs, not delta overlays, at query time.** Agents write
   plain Cypher; no masking predicates (`branches`/`removed_in` properties)
   ever appear in the queryable graphs. Deltas are purely a transport and
   storage mechanism, invisible to consumers.
2. **AGE holds durable repository graphs plus a small ephemeral cache of
   actively queried branch graphs.** One durable AGE graph per repo (the
   default branch), named from the repo identity; one AGE graph per
   *materialized* branch, named `<graph_name>__<branch>` (sanitized, with a
   hashing fallback for Postgres's 63-byte identifier limit). Branch graphs
   are a **cache**: only active, queried branches become AGE graphs; all
   other branches remain diff rows.
3. **Lazy materialization via supported Cypher writes only.** A branch graph
   is materialized on first query by creating the graph and rehydrating it
   through batched Cypher writes from a logical base snapshot plus the
   branch diff. **Never** by copying AGE-owned label tables
   (`INSERT ... SELECT`): AGE reserves graph namespaces and does not
   support direct DML/DDL in them. graphify stays independent of AGE's
   internal schemas.
4. **Branch diffs are commit-anchored to an immutable base.** A diff is
   computed against, and records, a pinned `base_commit_sha` (the
   merge-base with the target branch) and `base_snapshot_id`. Materialization
   hydrates from that snapshot and applies the diff to `head_commit_sha`.
   Never diff against, or hydrate from, "the current default-branch graph"
   unless it is verified to be exactly that base commit — otherwise branch
   graphs silently rot as the default branch moves.
5. **PostgreSQL (plain SQL) is the authoritative store** for the registry,
   ownership metadata, commit snapshots, branch diffs, and quality
   findings. AGE graphs are derived, rebuildable artifacts.
6. **A shared central Postgres/AGE instance** is the meeting point for
   decentralized repos; each contributor pushes their own repo. Trusted
   direct PostgreSQL/AGE users and agents may query any graph; **ownership
   governs frontend discovery and retrieval**, not database access.
7. **Lean property set by default.** Push only what agents query on;
   presentation-only properties stay in `graph.json`.

## Cypher-facing schema contract

Because agents' queries are an API, the emitted schema is documented and
test-pinned, identical across the neo4j/falkordb/age exporters.

- **Node label**: sanitized `file_type` capitalized (fallback `Entity`).
- **Relation type**: sanitized upper-snake relation (fallback `RELATED_TO`).
- **Node properties** (default lean set): `id`, `label`, `source_file`
  (repo-relative), `source_location`, `community`, plus structural metrics
  below. `--full-props` pushes everything scalar.
- **Edge properties**: `relation`, `confidence`
  (`EXTRACTED|INFERRED|AMBIGUOUS`).
- **Structural metrics stamped at push time** (cheap, already computed or
  trivially derived): `degree`, `is_god_node` (from `analyze.god_nodes`),
  `in_cycle` (from `find_import_cycles`). Evolving quality *rules* do NOT
  become node properties — they go to `graphify_quality_findings` (below).
- Every registry row and snapshot records `graphify_version`,
  `schema_version`, and `extraction_config_hash`, so agents (and the
  materializer) can detect incompatible graphs.

Deliverable: `docs/AGE_SCHEMA.md` + a schema-pinning test. **Pinning
mechanism**: "identical across exporters" cannot be pinned by live output
(neo4j has no integration test at all), so the property/label/relation
selection logic is factored into one shared pure function in `graphdb.py`
used by all three pushers, and *that* function is pinned by a plain unit
test in the default CI suite. Each backend's live suite then only verifies
that the backend faithfully writes the shared shape.

## Registry and authoritative SQL schema

Repository identity is a stable `repository_id` (UUID) keyed off the
normalized remote URL — `repo_tag` is a display/prefix name, not a global
primary key (tags can collide or be renamed across a decentralized fleet).

```sql
graphify_repos(
  repository_id UUID PRIMARY KEY,
  remote_url TEXT UNIQUE,          -- normalized
  repo_tag TEXT,                   -- display name / node-id prefix
  owner_id TEXT,                   -- frontend scoping; see Ownership
  default_branch TEXT,
  age_graph_name TEXT,             -- durable default-branch graph
  created_at, updated_at TIMESTAMPTZ
)

graphify_snapshots(                -- logical base snapshots (see Phase 3)
  snapshot_id UUID PRIMARY KEY,
  repository_id UUID REFERENCES graphify_repos,
  commit_sha TEXT,
  kind TEXT,                       -- 'checkpoint' | 'delta'
  parent_snapshot_id UUID,         -- for deltas
  payload JSONB,                   -- or object-storage pointer
  graphify_version TEXT,
  schema_version TEXT,
  extraction_config_hash TEXT,
  created_at TIMESTAMPTZ
)

graphify_branches(
  repository_id UUID REFERENCES graphify_repos,
  branch TEXT,
  base_commit_sha TEXT,            -- merge-base with target branch
  head_commit_sha TEXT,
  base_snapshot_id UUID REFERENCES graphify_snapshots,
  age_graph_name TEXT,             -- NULL until materialized
  materialized BOOLEAN,
  last_push_hash TEXT,
  pushed_by TEXT,
  pushed_at TIMESTAMPTZ,
  bytes_used BIGINT,               -- sum of pg_total_relation_size over the
                                   -- relations in the graph's namespace
                                   -- (discovered via AGE metadata/pg catalogs;
                                   -- the function itself is per-relation)
  graphify_version TEXT,
  schema_version TEXT,
  extraction_config_hash TEXT,
  PRIMARY KEY (repository_id, branch)
)

graphify_branch_revisions(          -- one generation per diff chain
  repository_id UUID,
  branch TEXT,
  generation BIGINT,
  base_commit_sha TEXT,
  head_commit_sha TEXT,
  active BOOLEAN,                  -- rebase/force-push creates a new
  created_at TIMESTAMPTZ,          -- generation and marks the old one
  PRIMARY KEY (repository_id, branch, generation),   -- superseded
  FOREIGN KEY (repository_id, branch) REFERENCES graphify_branches
)
-- Exactly one active generation per branch, enforced in the database so a
-- concurrent or failed rebase can never leave materialization ambiguous:
-- CREATE UNIQUE INDEX graphify_one_active_branch_revision
--   ON graphify_branch_revisions (repository_id, branch) WHERE active;

graphify_branch_diff(
  repository_id UUID,
  branch TEXT,
  generation BIGINT,               -- which revision chain this belongs to
  seq BIGINT,                      -- ordered within the generation
  from_commit_sha TEXT,            -- the commit transition this diff row
  to_commit_sha TEXT,              -- belongs to (validates replay)
  kind TEXT,                       -- node_add|node_del|node_change|edge_add|edge_del|edge_change
  payload JSONB,                   -- REVERSIBLE: old AND new values; full payload on delete
  PRIMARY KEY (repository_id, branch, generation, seq),
  FOREIGN KEY (repository_id, branch, generation)
    REFERENCES graphify_branch_revisions
)

graphify_quality_findings(
  repository_id UUID,
  commit_sha TEXT,
  node_id TEXT,
  rule TEXT,
  severity TEXT,
  evidence JSONB,
  tool_version TEXT,
  created_at TIMESTAMPTZ
)
```

Diffs must be **reversible and complete**: property changes carry both old
and new values; deletions carry the full removed payload. "Current state +
diffs reconstruct any point in time" holds only under this rule, backed by
periodic checkpoints in `graphify_snapshots`.

**Snapshot uniqueness**: `graphify_snapshots` carries a unique constraint on
`(repository_id, commit_sha, kind, schema_version, extraction_config_hash,
graphify_version)` — `kind` is part of the key because a commit may first be
stored as a delta and later also gain a reconstructed checkpoint; both
records are immutable and coexist. `base_snapshot_id` resolution **prefers
the checkpoint** for a commit when one exists, falling back to
delta-chain reconstruction otherwise, and never selects across a mismatched
schema version or extraction config.

## Ownership

- Ownership governs **frontend discovery and retrieval** (repository
  listing, graph selection, result scoping by authenticated `owner_id`;
  global cross-repository graphs are owner-scoped or owner-filtered).
  Trusted direct PostgreSQL/AGE users and agents may query all graphs.
- **Owner resolution at push time**: explicit `--owner` flag → owner
  segment of the git remote URL (`github.com/<owner>/<repo>`) →
  `git config user.email`. `pushed_by` (who ran the sync) is recorded
  separately from `owner_id`.
- Ownership lives **only in `graphify_repos`** — it is not stamped into the
  graph. The graph schema defines no repository root node, and no implicit
  one may be relied on; agents needing owner context join through the
  registry.

## Phases (in implementation order)

### Phase 0 — AGE compatibility spike

Validate, against a live Dockerized AGE, before building on assumptions:

- target AGE + PostgreSQL versions; psycopg (v3) client- vs. server-side
  binding against `cypher()`;
- agtype parameter maps via **explicit `PREPARE`/`EXECUTE`** (AGE documents
  parameters as usable through prepared statements only; prepare once per
  pooled connection — prepared statements are session-scoped);
- `UNWIND $rows` + `MERGE` behavior and batch sizing;
- transactional write behavior; index options on AGE label tables that do
  not require touching AGE internals.

**Spike results (executed against `apache/age` PostgreSQL 18.1 / AGE 1.7.0,
pinned by digest `sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb`
in `tests/test_age_integration.py`)** — two findings that change Phase 1's
design from what was originally assumed:

1. **The graph name argument to `cypher()` must be a literal at parse
   time.** `cypher($1, ...)` fails with `psycopg.errors.SyntaxError: a name
   constant is expected` — AGE's parser hook resolves the graph name before
   normal bind-parameter substitution runs. It can never be passed as a
   bound parameter; `push_to_age()` must build each statement with the
   (already-sanitized) graph name embedded as a validated SQL literal
   (`psycopg.sql.Literal`), the same discipline already required for
   labels/relations via `_safe_label`/`_safe_rel`.
2. **`SET n += <map>` / `SET n = <map>` reject a map that arrives via a
   parameter or via `UNWIND`-bound data** —
   `psycopg.errors.FeatureNotSupported: SET clause expects a map` — even
   though dot-path access into the same parameter (`$props.label`) works
   fine. Only a literal map written directly in the query text satisfies
   SET's map-mode. **This invalidates the generic "`SET n += row.props`"
   batch-write shape originally assumed for Phase 1.** The validated
   workaround is explicit per-field assignment —
   `SET n.id = row.id, n.label = row.label, ...` — enumerating the fixed
   lean/full property schema by name in the query text, with only the
   *values* flowing through `row`. This fits the design anyway: the pushed
   property set is a bounded, known schema (the Cypher-facing schema
   contract above), not arbitrary keys, so there is nothing to generalize
   over. `push_to_age()`'s prepared statement shapes are therefore built
   per fixed label/relation with an explicit field list, not a single
   generic `SET n += $props` statement.
3. A third, psycopg-specific (not AGE-specific) finding: `EXECUTE
   stmt_name(%s)` with the agtype payload as a normal bind parameter fails
   with `psycopg.errors.IndeterminateDatatype: could not determine data
   type of parameter $1` — `EXECUTE`'s argument list isn't part of the
   extended query protocol's normal parameterizable surface, and an
   explicit `::agtype` cast on the placeholder does not fix it. The payload
   must be embedded via `psycopg.sql.Literal` instead — safe here because
   it is graphify-generated JSON, not raw external input.

Deliverable: a spike test file that becomes the seed of the **live
integration suite**, following the exact pattern already established by
`tests/test_falkordb_integration.py` — there is no docker-compose
precedent in this repo (only a single `Dockerfile` for the MCP server), and
no neo4j integration test even exists, so AGE should not introduce a new
fixture mechanism:

- a `docker run` one-liner documented in the test module's docstring, not
  a compose file or a shell script — with an **explicitly pinned
  `apache/age` image tag** (the version-targeting decision of this spike),
  so the suite doesn't drift with upstream releases;
- `pytest.importorskip("psycopg")`;
- a service-identifying connection probe (not just a port/ping check) so a
  stray Postgres without the AGE extension loaded fails closed into a
  skip, not a false test failure — e.g. attempt `LOAD 'age'` or query
  `ag_catalog.ag_graph` and skip on error;
- host/port/db/user/password overridable via env vars
  (`AGE_HOST`/`AGE_PORT`/... matching the `FALKORDB_HOST`/`FALKORDB_PORT`
  naming convention);
- a fixture that drops the test graph before and after, for a clean slate;
- **no CI involvement** — like the falkordb suite, this is a manual,
  opt-in test for a dev who started the container locally; the default
  `ci.yml` provisions no external services and stays untouched. Mocked
  unit tests remain for CLI wiring and sanitization only.

### Phase 1 — `push_to_age()` exporter (full, deletion-safe push)

- New function in `graphify/exporters/graphdb.py`, sibling of the neo4j /
  falkordb pushers; re-exported from `graphify/export.py`.
- Connect with psycopg. Session setup: `LOAD 'age'; SET search_path =
  ag_catalog, "$user", public;`. Create the graph via
  `SELECT create_graph(...)` if absent (check `ag_catalog.ag_graph`).
- Writes use **prepared fixed Cypher statement shapes** per connection,
  passing an agtype parameter map of batch rows, `UNWIND $rows` (~500
  rows/statement), grouped by fixed safe node label / edge relation type.
  Per the Phase 0 spike findings: the graph name is embedded as a
  `psycopg.sql.Literal`, never a bind parameter (AGE requires it at parse
  time); each statement's `SET` clause enumerates the fixed lean/full
  property fields explicitly by name (`SET n.id = row.id, n.label =
  row.label, ...`) rather than a generic `SET n += row.props`, which AGE
  rejects for non-literal maps; and the agtype payload passed to `EXECUTE`
  is embedded via `psycopg.sql.Literal` rather than a normal bind
  parameter (psycopg cannot infer its type there). Labels and relations
  are still derived only through the controlled sanitizer mappings
  (`_safe_label` / `_safe_rel`). Single transaction per push.
- **Deletion-safe sync** — reconcile in place: after upserts, delete
  nodes/edges absent from the incoming graph inside the same transaction.
  PostgreSQL transaction isolation ensures readers see either the prior
  consistent graph or the fully reconciled graph, never a partial sync.
  Handle label changes explicitly: a logical node whose `file_type` changed
  must not survive under two AGE labels, so delete it under the old label as
  part of reconciliation. Full rebuild is reserved for recovery or an
  incompatible schema migration.
- Lean property set by default; `--full-props` flag for everything scalar.
- CLI: `graphify export age --push postgresql://user:pass@host/db
  [--graph-name NAME] [--full-props]`; password via `AGE_PASSWORD` or
  standard `PGPASSWORD`.
- Packaging: `age = ["psycopg[binary]"]` extra; add to `all`.
- Docs: `AGE_SCHEMA.md`, README export section, `graphify export` help.

### Phase 2 — Repository identity, ownership metadata, registry

- Create the SQL schema above (`graphify_repos`, `graphify_branches`,
  `graphify_snapshots`, `graphify_branch_revisions`,
  `graphify_branch_diff`, `graphify_quality_findings`, including the
  one-active-revision partial unique index) with a versioned migration.
  Registry tests are **tier 2** (plain Postgres, no AGE required — see
  Testing strategy).
- Push path registers/updates the repo (normalized remote URL →
  `repository_id`), resolves owner, records versions and
  `extraction_config_hash`.
- Branch name from `git rev-parse --abbrev-ref HEAD`; commit SHAs from git
  at push time.
- Cross-repo edges (already computed locally by `cross_repo_calls.py`) go
  into a small `global` AGE graph referencing `repo_tag`-prefixed ids,
  owner-scoped for frontend retrieval.
- Agents discover which graph to query via the registry.

### Phase 3 — Durable default-branch graph + logical snapshots

- Each default-branch push also records a logical snapshot entry:
  periodic full checkpoints (graph.json-style payload, in Postgres JSONB or
  object storage) plus ordered, reversible deltas between them — enough to
  reconstruct the graph at any recorded commit. This is the immutable base
  the branch machinery pins against; it is **not** an AGE graph copy.
- Extend `graph_diff()` to report **property changes with old and new
  values** and to include full payloads for removals (reversibility).
- Incremental default-branch sync: diff against the last-pushed snapshot;
  emit only batched MERGEs / SETs / DETACH DELETEs. No prior snapshot →
  full deletion-safe push. Typical edit-cycle syncs become O(changed
  files).

### Phase 4 — Branches: commit-anchored diffs, lazy hydration, reaping

- **Initial push for a non-default branch**: client determines the
  merge-base (`base_commit_sha`), obtains/creates the matching
  `base_snapshot_id` (see below), computes
  `graph_diff(base_snapshot_graph, branch_graph)`, and uploads ordered diff
  rows. O(diff) over the wire; no AGE graph created yet.
- **Subsequent pushes are incremental**: each normal push appends
  `head_n → head_n+1` diff rows to the existing chain (never a repeated
  `base → latest_head` diff — that would duplicate operations and corrupt
  replay/materialization). On **force-push or rebase** (detected by
  `head_commit_sha` no longer being an ancestor of the new head, or a
  changed merge-base): recompute the merge-base, create a **new generation**
  in `graphify_branch_revisions`, mark the old one inactive (superseded, not
  overwritten — history stays auditable), and start the new chain from the
  new base snapshot. Each diff row records its `from_commit_sha` /
  `to_commit_sha`, so replay can validate every transition.
- **Obtaining a missing base snapshot** (`base_commit_sha` predates
  retained checkpoints or AGE adoption), in order:
  1. reconstruct it from the nearest retained checkpoint plus the ordered
     reversible deltas between it and `base_commit_sha`, and store it as a
     checkpoint; else
  2. create a temporary git worktree at `base_commit_sha`, run graphify
     extraction there (cache-assisted), and store the result as a
     checkpoint in `graphify_snapshots`.
- **Materialization on first query** (`graphify age materialize` verb or a
  server-side helper): create the AGE graph, **rehydrate via batched
  prepared Cypher writes** from the pinned base snapshot, then replay the
  ordered diff chain to `head_commit_sha`. Set `materialized` and
  `age_graph_name`. Refuse to materialize across mismatched
  `schema_version` / `extraction_config_hash`.
- **Serialization**: the materializer takes a PostgreSQL advisory lock keyed
  by `(repository_id, branch)`, re-reads registry state inside the
  transaction, and only then creates/hydrates the AGE graph — so two agents
  requesting the same unmaterialized branch concurrently do one hydration,
  not two. The reaper acquires the same lock, so it cannot drop a graph
  mid-hydration or race an in-flight materialization. The lock cannot
  protect arbitrary direct-agent Cypher queries from a reap, so branch
  graphs are reaped only after a **generous inactivity grace period**, and
  the consumer contract documents that clients must re-resolve the graph
  through the registry (and re-materialize if needed) when a query fails
  because the graph was reaped.
- **Subsequent pushes to a materialized branch** apply the incremental diff
  directly (batched MERGE / SET / DETACH DELETE) and update
  `head_commit_sha`. The AGE mutation, the new diff-chain rows, the branch
  head SHA, and materialization metadata all commit in **one PostgreSQL
  transaction** — the registry can never claim a head commit the AGE graph
  does not actually contain after a failed write.
- **Reaper**: drop branch graphs via `drop_graph` (returns the space) on
  merge, closure, or inactivity/size threshold; size-aware via
  `bytes_used`. The diff rows and snapshots remain — a reaped branch can
  always be rehydrated.
- **Branch-diff rows double as review-agent input**: the changeset vs. base
  is queryable in plain SQL, so "what changed structurally in this PR"
  comes for free. AGE also allows calling `cypher()` on two graphs in one
  SQL statement and joining the results, enabling cross-branch structural
  comparison queries directly.

### Phase 5 — Agent contract: pinned queries and fixtures

For the **review agent**, define, document, and test:

- branch-diff seed selection: changed files, symbols, deleted symbols, and
  changed edges;
- traversal direction per relation type; reverse-dependency traversal for
  callers and dependents;
- required evidence in results: path, source locations, relation types,
  confidence, and branch/base commit;
- traversal depth caps, result limits, and statement timeouts.

For the **quality agent**: structural properties (`degree`, `is_god_node`,
`in_cycle`) live on nodes; rule-based findings are written to
`graphify_quality_findings` so rules can evolve without turning node
properties into an unstable catch-all.

Deliverables: pinned example queries in `docs/AGE_SCHEMA.md` + integration
fixtures in the live suite that execute them against a seeded instance.
Seeding uses `tests/fixtures/extraction.json` (the same fixture the
falkordb suite builds from); if it proves too small to exercise depth
caps, result limits, or statement timeouts meaningfully, grow a dedicated
larger fixture rather than weakening those assertions.

### Phase 6 (optional) — AGE-backed retrieval inside graphify

Lower priority now that the primary consumers query AGE directly.

- Thin backend abstraction for `query/path/explain` and `serve.py`:
  file-backend (current) vs. AGE connection.
- Strategy: fetch the candidate subgraph from AGE, pull into NetworkX, and
  reuse the existing scoring/formatting — do not reimplement scoring in
  Cypher; behavior stays identical to the file backend.

## Storage optimization summary

1. **Graph count is the biggest lever**: lazy materialization + reaping
   means durable default-branch graphs are the only full AGE copies that
   always exist; most branches live only as diff rows.
2. **Row size**: lean default property set; repo-relative `source_file`;
   skip empty/derivable properties (each property rides in AGE's agtype
   column, so property count multiplies storage directly).
3. **Indexes**: only on what agents filter by (`id`, `source_file`), via
   supported mechanisms validated in the Phase 0 spike.
4. **Visibility**: `bytes_used` in the registry; retention can be
   size-based as well as time-based.
5. **History without AGE copies**: checkpoints + ordered reversible diffs
   in SQL reconstruct any recorded commit; never store old AGE graph
   copies.

## Consumer contract (review / quality agents)

Agents live outside graphify and need only:

- `psycopg` + the connection string,
- the registry tables for discovery (`graphify_repos`,
  `graphify_branches`, `graphify_branch_diff`,
  `graphify_quality_findings`),
- `docs/AGE_SCHEMA.md` for the node/edge schema and pinned queries,
- optionally `graphify age materialize` (or the server-side helper) before
  querying a not-yet-materialized branch.

Clients must treat branch graphs as a cache: on a query failing because the
graph was reaped, re-resolve `age_graph_name` through the registry and
trigger re-materialization rather than retrying blindly.

## Testing strategy

Three tiers, not two — and the design principle that follows from them:
because tier 3 never runs in CI, **maximize what tiers 1–2 can cover** by
structuring the code so that planning/diffing logic is pure and only thin
adapters touch AGE.

**Tier 1 — pure-Python tests, default blocking CI (no database).** This is
where the highest-risk *logic* is tested, and most of it needs no AGE:

- `graph_diff()` reversibility: apply a diff forward, apply its reverse,
  assert graph equality (property-based testing is cheap and appropriate
  here);
- diff-chain replay: replay ordered diff rows onto a NetworkX graph and
  compare against the expected head graph; validate
  `from_commit_sha`/`to_commit_sha` transition checking rejects
  out-of-order and cross-generation rows;
- merge-base / force-push / rebase detection against a throwaway git repo
  created in a tmpdir (git *is* available in CI);
- graph-name sanitization and the 63-byte hashing fallback;
- the shared property/label/relation selection function (the schema pin,
  above) and lean-vs-`--full-props` selection;
- CLI wiring and env-var credential resolution (mocked connection).

To make this possible, reconcile and materialization are implemented as
**pure planners** (graph/diff in → ordered statement batches out) with a
thin executor that sends batches to AGE. The planner is tier 1; only the
executor needs tier 3.

**Tier 2 — plain-Postgres tests (live service, but no AGE required).**
Registry migrations, the partial unique index on
`graphify_branch_revisions`, the snapshot-uniqueness constraint,
generation supersession, and owner/identity upserts are plain SQL. Their
probe checks for reachable Postgres only — not for the AGE extension — so
they also pass against the AGE container without exercising it, and their
skip condition is deliberately weaker than tier 3's.

**Tier 3 — live AGE integration suite (opt-in, manual, never in CI).**
Everything mocks genuinely cannot validate: agtype/prepared-statement
behavior, `UNWIND` batching, transactional rollback, label-table behavior,
`create_graph`/`drop_graph`, advisory-lock serialization, and the
executor's faithful application of tier-1-planned batches. Follows
`tests/test_falkordb_integration.py`'s pattern exactly (importorskip +
service-identifying probe + env-var overrides + clean-slate fixture), with
one addition: the `docker run` line in the docstring **pins an explicit
`apache/age` image tag** (chosen in Phase 0 as the targeted AGE/PostgreSQL
version) so results don't drift with upstream releases.

**Accepted risk and mitigation.** The deletion-safe reconcile executor,
transactional atomicity, replay-to-AGE, locking, and reaping are exercised
only by tier 3, which no automation runs — the same trade the falkordb
suite makes, but over far more machinery. Mitigation: any PR touching AGE
write paths must state in its description that the live suite was run
locally against the pinned image tag, and with what result. A non-blocking
scheduled CI workflow with an AGE service container is a possible later
addition (Open questions) but is explicitly not required by this plan.

**Concurrency tests (tier 3)** are designed around determinism, not
timing: one connection holds the advisory lock while a second asserts
`pg_try_advisory_lock` fails and that the materializer takes its
re-read-then-hydrate path; no sleep-based races.

## Delivery, CI, and git workflow

This repo's contribution conventions (README "Contributing" section,
`AGENTS.md`) apply to this work like any other change; the points below are
the ones specific to AGE that aren't automatically obvious from those docs.

- **Fork/branch model**: `origin` is a fork (e.g. `e4c5/graphify`) of
  upstream `safishamsi/graphify`; `v8` is the active-development branch on
  both. Sync local `v8` to `origin/v8` (which tracks upstream) before
  cutting a branch.
- **One branch, one PR per feature — not one per phase.** The repo's own
  precedent settles this: the FalkorDB backend (`falkordb-backend`, PR
  #1176), the closest prior comparison in scope to this work, shipped as a
  single branch and a single PR containing four separate commits (`feat:
  add FalkorDB export backend`, `feat: add --falkordb/--falkordb-push
  skill shorthands`, `fix: correct cypher.txt guidance`, `refactor: rename
  shared push vars`) merged together. The README's own Contributing
  section only ever says "open a PR" (singular), never describes stacking.
  So AGE support is one branch (`apache-age-backend`, mirroring the
  `falkordb-backend` naming) carrying every phase as separate commits —
  "commit each milestone separately" means separate commits inside that
  one branch/PR, not separate PRs per phase. A phase boundary is a natural
  place to pause and get feedback before opening the PR, not a place to
  split it.
- **Commit style**: `feat: ...` / `fix: ...` / `docs: ...`, one commit per
  milestone within the single branch (e.g. `feat: add push_to_age()
  exporter`, `docs: add AGE_SCHEMA.md`), matching the granularity the
  `falkordb-backend` PR used.
- **Before opening any PR**: `uv run pytest tests/ -q` must pass. The
  live-AGE suite follows `tests/test_falkordb_integration.py` exactly:
  `pytest.importorskip` + a service-identifying connection probe that
  skips (not fails) when no live AGE instance is reachable, so it is a
  silent no-op in the existing `ci.yml`, which provisions no external
  services and needs no changes. No neo4j integration test or
  docker-compose fixture exists in this repo to mirror instead — AGE
  should not introduce either.
- **CI parity commands** (`uv sync --all-extras --frozen`, the blocking
  pytest run, the `tools.skillgen` checks, `graphify --help`/`install`
  smoke tests) must keep passing with the new `age` extra installed, on
  Python 3.10 and 3.12.
- **Packaging overlap**: `age = ["psycopg[binary]"]` duplicates the
  `psycopg[binary]` pin already in the `postgres` extra
  (`graphify/pg_introspect.py`). Decide explicitly whether `age` depends on
  `postgres` or repeats the pin independently (matching the existing
  `postgres` extra's inline comment style explaining the "why"), so
  `uv sync --all-extras` doesn't silently drift the two out of sync over
  time.
- **Docs**: update `ARCHITECTURE.md`'s module-responsibility table for
  every phase that adds a module or registry table (exporter in Phase 1,
  registry/migration in Phase 2, snapshot machinery in Phase 3, branch
  materializer/reaper in Phase 4), the same way any other module addition
  would be documented there.
- **No test-fixture obligation from the "new language extractor" rule**
  (`tests/fixtures/` + `tests/test_languages.py`) — AGE is an exporter, not
  an extractor — but the same spirit applies: Phase 0's spike must become a
  permanent, checked-in test, not a throwaway script.

## Implementation checklist

### Phase 0 — AGE compatibility spike ✅ done
- [x] `tests/test_age_integration.py` following
      `tests/test_falkordb_integration.py`'s exact pattern: a `docker run`
      one-liner in the module docstring (no compose file) with a **pinned
      `apache/age` image digest**, env-var host/port/credentials,
      `pytest.importorskip("psycopg")`, and a service-identifying
      connection probe (`LOAD 'age'`) that skips rather than fails when no
      live AGE instance answers.
- [x] Picked and recorded the target versions: PostgreSQL 18.1, AGE 1.7.0,
      pinned by digest
      `apache/age@sha256:4241e2d8bb86a6b2ea44e9ad06c73856e12b209de295124603a599dd7feb70eb`.
- [x] Spike/validate: psycopg (v3) binding against `cypher()` — confirmed
      working; discovered the graph name must be a literal, not a bind
      parameter (see spike results above).
- [x] Spike/validate: agtype parameter maps via explicit `PREPARE`/`EXECUTE`
      — confirmed working for scalar/dot-path access; discovered `SET n +=
      <param-map>` is rejected (see spike results above) and the workaround
      (explicit per-field `SET`).
- [x] Spike/validate: `UNWIND $rows` + `MERGE` behavior and batch sizing —
      confirmed working (validated at 50 rows) with the per-field `SET`
      workaround; idempotent re-run confirmed (`MERGE` updates in place,
      no duplication).
- [x] Spike/validate: transactional write behavior (partial-failure
      rollback) — confirmed: a malformed Cypher statement mid-transaction
      leaves prior committed state intact after `ROLLBACK`.
- [x] Spike/validate: index options on AGE label tables that don't touch
      AGE internals — confirmed: a `GIN` index on a label table's
      `properties` column works via plain `CREATE INDEX`.
- [x] Confirmed the suite is a silent no-op with no live service reachable
      (`6 skipped`) and does not affect the rest of the suite passing.
- [x] Spike test file lands as a permanent test module (seed of the live
      integration suite, including a `test_push_to_age_creates_expected_graph`
      end-to-end test that currently skips until Phase 1 lands
      `push_to_age()`).
- [x] Committed on `apache-age-backend` (single feature branch, off synced
      `v8` — see Delivery section for why this isn't split into per-phase
      branches). PR to upstream still pending.

### Phase 1 — `push_to_age()` exporter ✅ done
- [x] `push_to_age()` in `graphify/exporters/graphdb.py`, sibling of
      `push_to_neo4j`/`push_to_falkordb`; re-exported from
      `graphify/export.py`.
- [x] Session setup: `LOAD 'age'; SET search_path = ag_catalog, "$user",
      public;`; `create_graph()` if absent (check `ag_catalog.ag_graph`).
- [x] Prepared fixed Cypher statement shapes; agtype parameter map of batch
      rows; `UNWIND $rows` at ~500 rows/statement; grouped by sanitized
      label/relation; single transaction per push. Built per the Phase 0
      spike findings: graph name and `EXECUTE` payload as SQL literals,
      `SET` clauses enumerating fields explicitly by name.
- [x] Deletion-safe in-place reconcile: snapshot existing `(id, label)` /
      `(src, tgt, relation)` before upserting, delete what's absent from
      the incoming graph in the same transaction as the upserts; explicit
      old-label cleanup when `file_type` changes.
- [x] Lean property set by default; `--full-props` flag (dynamically
      computes the full scalar field union per push).
- [x] CLI: `graphify export age --push postgresql://... [--graph-name]
      [--full-props]`; `AGE_PASSWORD`/`PGPASSWORD` support (appended as a
      libpq URI query param when not already embedded).
- [x] `age` extra added to `pyproject.toml` (`psycopg[binary]`,
      independent of `postgres` — see the inline comment for the overlap
      decision) and to `all`; `uv lock` regenerated.
- [x] `docs/AGE_SCHEMA.md` written; README export section updated;
      `graphify export --help` updated; `ARCHITECTURE.md` module table
      updated (`test_architecture_doc.py` still passes).
- [x] Label/relation sanitization (`_safe_label`/`_safe_rel`) promoted to
      module level, deduplicated out of `push_to_neo4j`/`push_to_falkordb`,
      and pinned by a unit test — the "shared pure function" from the
      Testing strategy section. **Scope note**: full separation into a
      pure planner (graph in → statement batches out) + thin executor was
      not carried all the way through — row/field selection and batching
      (`_age_node_rows`, `_age_edge_rows`, `_age_node_field_names`,
      `_age_edge_field_names`, `_age_batches`) are pure and tier-1 tested,
      but the deletion-diff snapshot query and SQL statement construction
      remain inside `push_to_age()` itself, mixed with I/O. Tier-1
      coverage is still substantial (20 DB-free unit tests); a full
      planner/executor split is deferred rather than abandoned.
- [x] Tier-1 unit tests (`tests/test_age_exporter_unit.py`, 20 tests, no DB
      required): sanitization pinning, lean/full field selection, row
      grouping and structural-metric stamping, batching, the
      missing-psycopg `ImportError` guard.
- [x] Tier-3 live test matrix (`tests/test_age_integration.py`, validated
      against `apache/age` PostgreSQL 18.1 / AGE 1.7.0): fresh push;
      idempotent re-push (counts stable); node + edge deletion reconciled;
      property change updates in place; **label change** removes the node
      from its old label and creates it under the new one; a Python-level
      failure before the write transaction opens leaves the prior graph
      untouched (AGE's own mid-transaction rollback is covered separately
      by the Phase 0 spike's `test_transaction_rolls_back_on_failure`);
      `--full-props` includes extra scalar fields.
- [x] Full CLI path validated end-to-end against a live container
      (`graphify export age --push postgresql://...`), not just the Python
      function directly.
- [x] Committed on the same `apache-age-backend` branch as Phase 0 (Phase
      1's tests build directly on Phase 0's live-suite file). PR to
      upstream still pending. Full CI-parity command list green with
      `--all-extras` (5384 passed).

### Phase 2 — Repository identity, ownership, registry ✅ done (with one deferred item)
- [x] Versioned SQL migration (`graphify/age_registry.py`,
      `_MIGRATIONS` + `graphify_registry_migrations` tracking table) for
      `graphify_repos`, `graphify_branches`, `graphify_snapshots`,
      `graphify_branch_revisions`, `graphify_branch_diff`,
      `graphify_quality_findings`, including the partial unique index on
      `graphify_branch_revisions` and the snapshot-uniqueness constraint.
- [x] Tier-2 tests (`tests/test_age_registry_integration.py`, plain
      Postgres, no AGE extension needed): migration idempotency, partial
      unique index rejects a second active revision (a second *inactive*
      one is fine), snapshot-uniqueness allows delta+checkpoint to
      coexist but rejects a true duplicate, identity upserts, SSH/HTTPS
      remote dedup.
- [x] Tier-1 tests (`tests/test_age_registry_unit.py`, 16 tests, no DB):
      `normalize_remote_url` (SSH/HTTPS agreement, credential stripping,
      case folding), `repository_id_for` determinism, `resolve_owner`'s
      fallback order.
- [x] Push path (`graphify export age --push`, unless `--no-register`):
      normalizes the remote URL → `repository_id`; registers/updates
      `graphify_repos`; owner resolution order (`--owner` flag → git
      remote owner segment → `git config user.email`) via
      `age_registry.resolve_owner`. Fields COALESCE on conflict, so a
      push that doesn't know the owner never blanks out a previously
      registered one. New CLI flags: `--owner`, `--repo-tag`,
      `--remote-url` (override auto-detection), `--no-register`. A
      missing git remote warns and skips registration rather than
      failing the push; a registration failure after a successful push
      warns rather than losing the pushed graph.
- [x] Branch name from `git rev-parse --abbrev-ref HEAD`; commit SHA via
      the existing `graphify.watch._git_head` helper (already
      cwd-anchored per #2316) — reused rather than reimplemented.
- [x] **Closed by Phase 3 + the v15 review fixes** (was deferred here):
      `graphify_snapshots` rows now persist
      `graphify_version`/`schema_version`/`extraction_config_hash` on every
      write (`age_snapshots.record_snapshot`/`record_historical_checkpoint`),
      and `extraction_config_hash` is a real value —
      `age_registry.extraction_config_hash(full_props=..., extra=...)`, a
      deterministic hash of `--full-props` plus an optional
      `--extraction-config` / `GRAPHIFY_EXTRACTION_CONFIG_HASH` fingerprint,
      threaded through the CLI into `push_branch`/`record_snapshot`/
      `latest_snapshot_graph`/`snapshot_graph_by_id`. Reconstruction and
      base-snapshot resolution filter by all three fields.
- [x] **Global cross-repo AGE graph needs no new code**: it was already
      possible with the existing CLI. `graphify export age --graph
      ~/.graphify/global-graph.json --push ... --graph-name
      graphify_global` pushes the already-merged, `repo_tag`-prefixed,
      cross-repo-linked graph (`global_graph.py` +
      `cross_repo_calls.link_cross_repo_member_calls`) through the same
      `push_to_age()` path — validated live. Owner-scoping for frontend
      retrieval comes from each contributing repo already being
      registered in `graphify_repos`, not from new global-graph code.
- [x] Agent-facing registry discovery: `age_registry.resolve_age_graph_name(
      conninfo, remote_url, branch=None)` — returns the default-branch
      graph name, a registered branch's graph name, or `None` for an
      unregistered repo/branch (including when the registry schema
      doesn't exist at all yet — a read-only discovery call never creates
      tables as a side effect).
- [x] `ARCHITECTURE.md` updated for the `age_registry.py` module
      (`test_architecture_doc.py` still passes).
- [x] Full CLI path (push + auto-register) validated end-to-end against a
      live container, plus the `--no-register` and no-git-remote paths.
- [x] Committed on `apache-age-backend`; `pytest` green (5400 passed
      non-live, all live AGE + registry tests passed against
      PostgreSQL 18.1 / AGE 1.7.0).

### Phase 3 — Durable default-branch graph + logical snapshots ✅ done
- [x] `graph_diff()` extended to report property changes (old + new values,
      `changed_nodes`/`changed_edges`) and full payloads on removal/addition
      (`removed_nodes`/`new_nodes`/etc. now carry a `properties` dict).
      Purely additive to the existing return shape; all pre-existing callers
      (skill `update.md` docs, `tests/test_analyze.py`) unaffected.
- [x] Default-branch push records a logical snapshot in `graphify_snapshots`
      (`graphify/age_snapshots.py::record_snapshot`): periodic full
      checkpoints (JSONB payload) + ordered deltas (a stored `graph_diff()`
      dict) reconstructed via `apply_diff_to_payload`.
- [x] Incremental default-branch sync: `graphify export age --push`
      reconstructs the last snapshot (`latest_snapshot_graph`), diffs the
      new graph against it, and passes the diff into `push_to_age(...,
      diff=...)`, which then upserts only new/changed rows and deletes only
      what the diff reports removed/relabeled -- no read of live AGE state.
      Falls back to a full push (`diff=None`, unchanged Phase 1 behavior)
      when there's no prior snapshot, registration is disabled
      (`--no-register`), or no git remote is found.
- [x] Checkpoint cadence decided: every Nth push (`CHECKPOINT_CADENCE = 20`,
      overridable via `record_snapshot(..., cadence=...)`) is a full
      checkpoint; the rest are deltas against the reconstructed prior state.
      Simple and predictable over size-based triggers -- revisit only if
      checkpoint payloads dominate storage for very large graphs.
- [x] Snapshot uniqueness constraint enforced (already part of the Phase 2
      schema: `repository_id, commit_sha, kind, schema_version,
      extraction_config_hash, graphify_version`); checkpoint-preferred
      resolution implemented in `_reconstruct_payload_from_rows` (walks
      backward to the most recent checkpoint and only replays deltas after
      it, so a delta sharing a checkpoint's `commit_sha` is never
      replayed). `record_snapshot` is additionally idempotent **by
      commit_sha alone** (a repeat push of an already-recorded commit is a
      no-op, checked before the cadence/kind decision) -- the uniqueness
      constraint alone doesn't guarantee this, since which `kind` a re-push
      would compute depends on how many rows exist *now*, not on
      `commit_sha`; found live while testing (`
      test_record_snapshot_is_idempotent_for_same_commit`).
- [x] `ARCHITECTURE.md` updated for snapshot machinery (`age_snapshots.py`
      row).
- [x] Committed on `apache-age-backend`; `pytest` green (5439 passed
      non-live; live AGE + registry + snapshot suites all passed against
      PostgreSQL 18.1 / AGE 1.7.0, including an end-to-end CLI-path
      scenario: full push → checkpoint → incremental push that adds,
      removes, and relabels nodes → verified directly against AGE's live
      graph state).

### Phase 4 — Branches: commit-anchored diffs, lazy hydration, reaping ✅ done
- [x] Initial non-default-branch push (`age_branches.push_branch`):
      merge-base detection, base-snapshot resolution/creation, `graph_diff`
      against base, ordered diff-row upload; no AGE graph created yet.
- [x] Subsequent pushes append `head_n → head_n+1` diff rows to the active
      generation (`_append_branch_push`).
- [x] Force-push/rebase detection (`head_commit_sha` no longer an ancestor
      of the new head, via `detect_rebase`/`is_ancestor`) → new generation
      in `graphify_branch_revisions`, old one marked inactive (never
      deleted), new chain from a freshly resolved base snapshot. A
      previously materialized graph for the superseded generation is
      dropped (its content is now stale) and `materialized`/`age_graph_name`
      reset, so the next materialize starts clean.
- [x] Missing-base-snapshot fallback chain (`ensure_base_snapshot`):
      reconstruct from an existing `graphify_snapshots` row at that exact
      commit if one exists; else a temporary git worktree + real
      `extract()`/`build()`, persisted as a **backdated** historical
      checkpoint (`age_snapshots.record_historical_checkpoint` — its
      `created_at` is set *before* every existing row for the repo, not
      "now", since `_reconstruct_payload_from_rows` walks by `created_at`
      assuming that tracks git history order; a plain `now()` insert would
      make an old commit's state look like the *newest* one and silently
      corrupt every later default-branch reconstruction — caught and fixed
      before this shipped, not found live).
- [x] Materialization path (`age_branches.materialize_branch`, plus
      `graphify age materialize --push URI [--branch NAME]`): creates the
      AGE graph, rehydrates it via one `push_to_age()` full push from the
      replayed base-snapshot-plus-diff-chain graph, records
      `materialized`/`age_graph_name`. `graphify_branches` now persists
      `graphify_version`/`schema_version`/`extraction_config_hash` at push
      time; `push_branch` rejects (`ValueError`) a push whose
      `schema_version`/`extraction_config_hash` diverges from what's
      already on record for that branch instead of silently continuing its
      diff chain under a different config, and base-snapshot resolution
      (`ensure_base_snapshot`) plus snapshot reconstruction
      (`latest_snapshot_graph`/`snapshot_graph_by_id`) filter retained rows
      by the same fields so an incompatible checkpoint/delta can't get
      spliced into a replay (post-review fix, v15 — see Status).
- [x] Advisory lock (`pg_advisory_lock`, keyed by a SHA-256-derived bigint
      on `(repository_id, branch)`) around both the materializer and the
      reaper; both re-read branch/revision state after acquiring it.
- [x] Atomic branch-push transaction: for an already-materialized branch,
      `_append_branch_push` inserts the new diff rows, applies the same
      diff to the live AGE graph via `push_to_age(..., conn=<shared
      connection>)` (a new `conn=` parameter so `push_to_age()` can join a
      caller-managed transaction instead of always opening/committing its
      own), and updates the branch head SHA — one PostgreSQL transaction,
      so the registry can never claim a head commit the AGE graph doesn't
      actually contain.
- [x] Reaper (`age_branches.reap_branch`, `graphify age reap`):
      `drop_graph` after a generous default 7-day idle threshold
      (`min_idle_seconds`, overridable); diff rows and snapshots are never
      touched, so a reaped branch re-materializes cleanly on the next
      query (tested live). Size-threshold reaping is **not** implemented —
      `bytes_used` remains an unpopulated reserved column (an honest gap
      like `extraction_config_hash`; computing it needs a
      `pg_total_relation_size` sweep over the graph's namespace that
      nothing currently calls).
- [x] Reaper trigger mechanism decided: **explicit CLI invocation**
      (`graphify age reap`), not a cron job or automatic opportunistic
      check on every push — the latter would add unpredictable latency to
      every export for a benefit (freeing branch-graph storage) that isn't
      time-critical. A scheduled `graphify age reap` (external cron) is
      the recommended usage; graphify itself schedules nothing.
- [x] Cross-branch comparison query support: documented and live-tested in
      `docs/AGE_SCHEMA.md` — two independent `cypher()` calls (one per
      graph) joined in one SQL statement, no cross-graph Cypher syntax
      needed.
- [x] `ARCHITECTURE.md` updated for `age_branches.py`
      (`test_architecture_doc.py` still passes).
- [x] Materialization/replay implemented planner/executor style:
      `age_branches.replay_branch_diffs`/`diff_to_rows`/`rows_to_diff` are
      pure and tier-1-tested against fabricated rows and real NetworkX
      graphs (ordering, transition validation via `from`/`to` continuity,
      and cross-generation rejection all covered); only
      `materialize_branch`'s actual AGE write needs the live suite.
- [x] Deterministic tier-3 concurrency test: two connections, one holding
      `pg_advisory_lock`, the second asserting `pg_try_advisory_lock` fails
      and then succeeds once the first releases — no sleep-based races.
      This validates the underlying primitive `materialize_branch` and
      `reap_branch` both use; a live *concurrent-thread* call into
      `materialize_branch` itself (as opposed to two sequential calls,
      which `test_materialize_branch_is_idempotent` does cover) was not
      additionally exercised — the blocking `pg_advisory_lock` makes the
      "second caller waits, then sees `already_materialized=True`" behavior
      a direct consequence of the tested primitive plus the tested
      sequential-idempotency path, not a separate code path to verify.
- [x] Committed on `apache-age-backend`; `pytest` green (5475 passed
      non-live; live AGE + registry + snapshot + branch suites all passed
      against PostgreSQL 18.1 / AGE 1.7.0, including a full CLI-level
      smoke test: default-branch push → feature-branch push → `graphify
      age materialize` → `graphify age reap`), including rebase/force-push
      detection tests (tier 1, throwaway git repos in tmp_path).

### Phase 5 — Agent contract: pinned queries and fixtures ✅ done
- [x] Review-agent query set documented and pinned in `docs/AGE_SCHEMA.md`'s
      new "Agent contract" section: branch-diff seed selection, traversal
      direction per relation (`source → target` exactly as extracted,
      independent of `push_to_age()`'s undirected `nx.Graph` internals --
      see the direction-bug fix below), reverse-dependency vs. forward
      traversal, required evidence fields (id, source_file,
      source_location, relation, confidence, and the branch/base commit),
      depth caps/result limits/statement timeouts.
- [x] Quality-agent contract documented: structural properties
      (`degree`/`is_god_node`/`in_cycle`) vs. `graphify_quality_findings`
      -- the boundary exists so a rule can be added/changed/retired
      without a schema migration.
- [x] Pinned example queries added to `docs/AGE_SCHEMA.md`: branch-diff
      seed selection (plain SQL), depth-capped/limited/timed-out
      traversal, and quality-findings-joined-with-structural-properties,
      plus a "Parsing agtype vertex/edge/path values" helper (AGE returns
      `{...}::vertex`/`{...}::edge`/`[...]::path`, not plain JSON --
      `json.loads` and a naive regex both fail on the nested `properties`
      object; a depth-aware splitter is pinned instead).
- [x] **Two AGE 1.7.0 gaps found live while validating the *existing*
      shortest-path pinned query** (written in Phase 0/1 but never
      actually executed against a live instance until now):
      `shortestPath()` doesn't exist on this version at all (`syntax
      error at or near "shortestPath"`), and list-comprehension path
      projection (`[n IN nodes(p) | n.id]`) fails with `could not find
      properties for n`. Rewrote the pinned query to order variable-length
      matches by `length(p)` and return the whole path for client-side
      parsing instead -- documented as a version-specific limitation, not
      silently worked around.
- [x] Integration fixtures in the live suite
      (`tests/test_age_agent_queries_integration.py`) executing every
      pinned query verbatim against a seeded instance: `extraction.json`
      (correctness-oriented queries -- shortest path, reverse-dependency
      traversal, branch-diff seed selection, quality findings join) and a
      dedicated 200-node fan-out fixture (depth cap / `LIMIT` /
      `statement_timeout` -- `extraction.json`'s 4 nodes proved too small
      to exercise these meaningfully, so a larger fixture was added per
      the plan's own instruction rather than weakening the assertions).
      `statement_timeout` is proven to actually cancel a runaway query
      (`psycopg.errors.QueryCanceled`), not just documented as advice.
- [x] Commit on `apache-age-backend`; `pytest` green (5481 passed
      non-live; live AGE + registry + snapshot + branch + agent-query
      suites all passed against PostgreSQL 18.1 / AGE 1.7.0). Also fixed,
      as a prerequisite: a pre-existing edge-direction bug found while
      validating the reverse-dependency-traversal query (see the separate
      `fix:` commit) affecting all three graph-DB exporters and
      `graph_diff()`, not something introduced by this phase.

### Phase 6 (optional) — AGE-backed retrieval inside graphify ✅ done (CLI only; serve.py deferred)
- [x] Backend abstraction for `query`/`path`/`explain` (`cli.py`): a new
      `graphify/age_backend.py::fetch_graph_from_age(conninfo, graph_name)`
      fetches a whole AGE graph into an `nx.MultiGraph` shaped exactly like
      `build()`'s output (full property set as node attrs, `_src`/`_tgt`
      stamped on every edge). Each subcommand's existing graph-loading
      block gained an `if --age: ... else: <unchanged file-loading
      code>` branch; everything downstream (scoring, path-finding,
      formatting) is the literal same code either way.
- [x] AGE-fetch-then-NetworkX-score strategy implemented; scoring/formatting
      unchanged and **proven** behavior-identical to the file backend --
      not just argued: `tests/test_age_backend_integration.py` pushes one
      graph to both a local `graph.json` and a live AGE instance and
      asserts `graphify query`/`path`/`explain`'s printed output is
      byte-for-byte identical (`path`/`explain` exactly; `query` modulo
      the one "Graph: ..." header line that's supposed to differ).
- [x] **`serve.py` (the MCP/HTTP server) is explicitly deferred, not
      implemented.** Its `_load_graph`/multi-graph-context-LRU/hot-reload
      machinery is all keyed on `graph_path` as a filesystem path string
      threaded through `_build_server`, `serve`, and `serve_http` -
      retrofitting an AGE connection as an alternate "path" would mean
      either widening that key type through a large, already-complex,
      widely-used module (real regression risk to existing MCP clients
      for a nice-to-have), or a shallow bolt-on that silently breaks hot-
      reload/multi-context semantics for AGE-backed sessions. `cli.py`'s
      one-shot subcommands have no such state to reconcile, which is why
      they were in scope and `serve.py` isn't -- revisit only if a
      concrete need for AGE-backed *live-served* retrieval (not just
      ad-hoc CLI queries) shows up.
- [x] `ARCHITECTURE.md` updated (`age_backend.py` row).
- [x] Also promoted `parse_agtype_objects` (docs/AGE_SCHEMA.md's Phase 5
      pinned parser, previously duplicated as a copy in
      `tests/test_age_agent_queries_integration.py`) into
      `graphify.age_backend` as the canonical implementation, and updated
      that test file to import it instead of keeping a second copy that
      could drift from the doc.
- [x] Commit on `apache-age-backend`; `pytest` green (5487 passed
      non-live; live AGE + registry + snapshot + branch + agent-query +
      backend suites all passed against PostgreSQL 18.1 / AGE 1.7.0).

### Post-implementation dogfooding pass (graphify on its own repo)

Ran the full pipeline on this repo (code-only AST: 12,784 nodes / 26,727
edges), pushed to a live AGE instance, and diffed `graphify
query`/`path`/`explain` output between the `graph.json` and `--age`
backends across ~54 invocations. The tier-3 fixture
(`tests/fixtures/extraction.json`) is too small to exercise any of the
following; all three were only visible at real-repo scale, and all are
fixed:

1. **`age_backend.parse_agtype_objects` crashed the AGE backend on 9
   nodes.** The "depth-aware" agtype parser (also `docs/AGE_SCHEMA.md`'s
   pinned reference impl) tracked brace nesting but not string state, so a
   `label` property containing literal `{`/`}` (a docstring fragment, a JS
   `${...}` template literal) corrupted the parse and returned nothing ->
   `not enough values to unpack`. Now string-aware; regression test in
   `tests/test_age_backend_unit.py`.
2. **`graphify export {age,neo4j,falkordb}` pushed ~79% of edges
   reversed.** The CLI loaded `graph.json` (written `directed: false`,
   direction carried only in `source`/`target` arc order, no `_src`/`_tgt`
   markers) as an *undirected* graph, which canonicalizes endpoint order
   and flips every edge whose target node was inserted first -- so the
   pushed graph disagreed with `graphify path`/`explain`, which force a
   directed load. This is a **separate** bug from the earlier
   `_src`/`_tgt`-canonicalization edge-direction fix (Phase 5): that one
   was in `graph_diff()`/the exporters' arc handling; this one is the CLI
   loader never giving them a directed graph to begin with. Fixed by
   forcing `directed=True, multigraph=True` for the graph-DB sinks in
   `cli.py`; regression test in `tests/test_cli_export.py`
   (`test_export_graphdb_preserves_edge_direction_from_undirected_graph_json`).
3. **`query`/`path`/`explain` traversal was edge-insertion-order
   dependent.** `_bfs`/`_dfs`/`_subgraph_to_text` walked neighbours and
   rendered edges in insertion order, and `explain` broke degree-sort ties
   the same way -- so identical topology from `graph.json` (JSON link
   order) vs. AGE (DB row-scan order) produced different budget-truncated
   answers. Neighbour iteration and edge rendering are now sorted by node
   id, and `explain`'s connection sort has an `str(id)` tie-break;
   regression tests in `tests/test_serve.py`. After the fix, all
   query/path/explain output is backend-identical (modulo the intentional
   `Graph: ...` header line).

Note: byte-identical parity between the two backends still requires
`--full-props` on the push -- the lean property set omits `file_type` and
per-edge `source_file`/`source_location`, which `explain` renders.

4. **`push_to_age()` was ~6.6x slower than necessary.** Every
   `MATCH (a {id: ...})` / `MERGE (n:Label {id: ...})` compiles to a
   `properties @> '{"id": ...}'::agtype` filter; with no index on
   `properties` that is a sequential scan of the whole label table *per
   UNWIND row*, so a full push of the ~13k-node / ~27k-edge self-graph
   took **9m36s**. Fixes, no behaviour change:
   - `_ensure_age_property_indexes()` -- `create_vlabel` each incoming
     vertex label up front (so its table exists), then index its
     `properties` before any MATCH/MERGE. AGE indexes only its own
     internal `id`/`start_id`/`end_id` columns (so edge-traversal indexes
     are free); nothing on the user-facing agtype. **Three** index kinds
     per vertex label, because AGE compiles the idioms differently:
     * **GIN on `properties`** -- serves the `properties @> '{"id": ...}'`
       filter that `push_to_age`'s own `MATCH/MERGE (n {id: ...})`
       compiles to. This alone: 9m36s -> **2m47s**.
     * **btree on `agtype_access_operator(properties, '"id"')`** and one
       on `'"source_file"'` -- serve idiomatic agent Cypher (`WHERE n.id
       = ...` / `WHERE n.id IN [...]` / `WHERE n.source_file = ...`, and
       docs/AGE_SCHEMA.md's pinned queries), which compile to the
       access-operator form GIN does *not* serve. The plan always called
       for "indexes on what agents filter by (id, source_file)"; they
       were never actually created until now.
   - Edge upsert now sub-groups each relation's rows by the AGE labels of
     its endpoints and emits `MATCH (a:SrcLabel {id: ...}), (b:TgtLabel
     {id: ...})` -- a labelled match probes one label table's index
     instead of all of them. -> **~1m30s**.
   Larger UNWIND batches (>500 rows/statement) were measured and are
   *worse*, not better -- AGE re-plans per row, so the cost is superlinear
   in batch size; `batch_size=500` stays the default. Beyond this, AGE's
   Cypher write path is the floor (~250 elements/s); a materially faster
   load would need AGE's `COPY`-based bulk loader, which bypasses the
   Cypher-facing schema contract and is out of scope. A further ~4x on the
   edge phase is available by switching `push_to_age`'s own matches from
   the `{id: ...}` map form to `WHERE a.id = ...` (btree, not GIN) and
   dropping the GIN entirely -- deferred: it needs the MERGE-based node
   upsert reworked into explicit CREATE-vs-SET, a bigger change than this
   pass warranted. Covered by `tests/test_age_exporter_unit.py`
   (`_age_index_name`, `_AGE_INDEXED_NODE_PROPS`) and the live
   `tests/test_age_integration.py` matrix
   (`test_push_to_age_creates_property_indexes`).

### Cross-cutting / process
- [x] `v8` synced to `origin/v8` before cutting `apache-age-backend`
      (single branch for the whole feature — see Delivery section).
- [ ] The eventual PR uses `feat:`/`fix:`/`docs:` commit style per
      milestone (already true of the commits so far) and passes
      `uv run pytest tests/ -q` before opening.
- [x] `uv sync --all-extras --frozen` + full CI parity command list green
      on the branch as of Phase 1 (5384 passed); re-verify again before
      opening the PR once later phases land.
- [x] `postgres`/`age` extra overlap decision recorded once (Phase 1
      commit), not re-litigated per phase.
- [x] README "Contributing → Git workflow" now documents the fork → branch
      → PR-to-upstream flow and the one-branch/one-PR-per-feature rule.
- [ ] The PR description states that the tier-3 live suite was run locally
      against the pinned image tag, and the result (the accepted-risk
      mitigation in Testing strategy).

## Open questions

- ~~Sanitization/length rules for AGE graph names~~ **Resolved in Phase
  4**: `age_branches.sanitize_branch_graph_name` -- `<base>__<branch>`,
  hashing fallback (SHA-256, truncated) when that exceeds Postgres's
  63-byte identifier limit.
- ~~Reaper trigger mechanism~~ **Resolved in Phase 4**: explicit CLI
  invocation (`graphify age reap`), not cron or opportunistic-on-push.
  Merge/closure-aware reaping (rather than pure inactivity) is still open
  -- there's no signal today for "this branch's PR merged/closed," so
  `reap_branch` only ever reaps on idle time.
- Snapshot payload location: Postgres JSONB vs. object storage (size
  threshold?) -- Phase 3 uses JSONB unconditionally; revisit if payloads
  grow large enough to matter.
- `bytes_used` on `graphify_branches` is not populated. Computing it needs
  a `pg_total_relation_size` sweep over the AGE graph's namespace, which
  nothing currently calls -- reserved/nullable in practice, like
  `extraction_config_hash`. Would enable size-threshold reaping
  (`reap_branch` currently only supports idle-time-based reaping).
- ~~Checkpoint cadence for `graphify_snapshots`~~ **Resolved in Phase 3**:
  every Nth push (default 20, `age_snapshots.CHECKPOINT_CADENCE`) is a full
  checkpoint; the rest are deltas.
- Whether the frontend layer enforcing owner scoping is part of graphify
  (e.g. an authenticated MCP/HTTP mode of `serve.py`) or external.
- Whether to later add a non-blocking scheduled CI workflow with an AGE
  service container to run the tier-3 suite automatically (not required by
  this plan; would need upstream buy-in since CI config is upstream's).
- **`extraction_config_hash` is populated and enforced, but its inputs are
  still coarse.** As of the v15 review fixes the CLI computes and threads a
  real value (`age_registry.extraction_config_hash()`) into
  `push_branch`/`record_snapshot`/`latest_snapshot_graph`/
  `snapshot_graph_by_id`, and Phase 4 materialization / base-snapshot
  resolution / snapshot reconstruction all filter by it, so an incompatible
  checkpoint or delta can no longer be spliced into a replay. What it hashes
  today is `--full-props` plus an optional caller-supplied
  `--extraction-config` / `GRAPHIFY_EXTRACTION_CONFIG_HASH` fingerprint --
  it does **not** yet automatically fold in the actual extraction settings
  (LLM backend/model, confidence thresholds, extractor flags), because those
  aren't threaded from `graphify extract` down to `export age --push`.
  Open: make that fingerprint automatic rather than opt-in.
